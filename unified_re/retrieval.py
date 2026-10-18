"""Local quantized multilingual vectors + BM25; fusion uses ranks, not raw scores."""
import math
import re
import sqlite3
from collections import Counter

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from .common import GateError, ROOT, SKILL, VAR, digest, now, read_json, write_json


def tokens(text):
    text = text.lower()
    words = re.findall(r"[a-z0-9_]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return words


class Embedder:
    def __init__(self, path=None):
        self.path = path or ROOT / "models/multilingual-minilm"
        manifest = read_json(self.path / "manifest.json")
        for entry in manifest["files"]:
            if digest((self.path / entry["path"]).read_bytes()) != entry["sha256"]:
                raise GateError("integrity_error", "Model file digest mismatch", file=entry["path"])
        self.pipeline = {"version": 1, "chunk_tokens": 256, "chunk_stride": 32, "pooling": "attention-mask-mean", "normalization": "l2", "onnxruntime": ort.__version__, "vector_dtype": "float32"}
        self.version = digest({"model": manifest, "pipeline": self.pipeline})
        self.manifest = manifest
        self.tokenizer = Tokenizer.from_file(str(self.path / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256, stride=32)
        self.tokenizer.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        self.model = ort.InferenceSession(str(self.path / "onnx/model_quantized.onnx"), sess_options=opts, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.model.get_inputs()}

    def encode(self, texts, batch_size=12):
        result = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer.encode_batch(texts[start:start + batch_size])
            inputs = {"input_ids": np.array([v.ids for v in encoded], dtype=np.int64), "attention_mask": np.array([v.attention_mask for v in encoded], dtype=np.int64), "token_type_ids": np.array([v.type_ids for v in encoded], dtype=np.int64)}
            hidden = self.model.run(None, {k: v for k, v in inputs.items() if k in self.input_names})[0]
            mask = inputs["attention_mask"][:, :, None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            pooled = pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
            result.extend(pooled.astype(np.float32))
        return np.array(result, dtype=np.float32)

    def chunks(self, text):
        encoded = self.tokenizer.encode(text)
        result = []
        for part in [encoded, *encoded.overflowing]:
            offsets = [(a, b) for a, b in part.offsets if b > a]
            if offsets:
                result.append(text[min(a for a, _ in offsets):max(b for _, b in offsets)])
        return result or [text]


class Index:
    def __init__(self, catalog=None, db=None, embedder=None):
        self.catalog = catalog or read_json(SKILL / "catalog.json")
        VAR.mkdir(parents=True, exist_ok=True)
        self.db_path = db or VAR / "index.sqlite"
        self.manifest_path = self.db_path.with_suffix(".manifest.json") if db else VAR / "index-manifest.json"
        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, kind TEXT, source TEXT, metadata TEXT, text TEXT, content_hash TEXT, model TEXT, vector BLOB)")
        self.embedder = embedder or Embedder()

    def inputs(self):
        import json
        for skill in self.catalog["skills"]:
            path = (SKILL / skill["procedure"]).resolve()
            if not path.is_relative_to(SKILL.resolve()) or path.suffix != ".md":
                raise GateError("policy_conflict", "Non-allowlisted skill path")
            body = path.read_text(encoding="utf-8")
            references = []
            for reference in skill.get("reference_paths", []):
                ref = (ROOT / reference).resolve()
                if not ref.is_relative_to((ROOT / "resources").resolve()) or ref.suffix != ".md":
                    raise GateError("policy_conflict", "Non-allowlisted methodology reference")
                references.append(ref.read_text(encoding="utf-8"))
            # Description, trigger/type, workflow headings and deliverables are
            # indexed; original resources remain separately traceable.
            text = "\n".join([skill["purpose"], skill.get("trigger_description", ""), " ".join(skill["target_types"] + skill["capabilities"] + skill["stages"]), body, *references])
            yield skill["id"], "skill", skill["source"], skill, text
        for tool in self.catalog["tools"]:
            definition = tool["definition"]
            def outline(schema):
                return json.dumps({"type": schema.get("type"), "required": schema.get("required", []), "parameters": {key: {k: value[k] for k in ("type", "description", "enum", "$ref") if k in value} for key, value in schema.get("properties", {}).items()}, "definitions": sorted(schema.get("$defs", {}))}, ensure_ascii=False)
            text = "\n".join([tool["name"], definition.get("description", ""), "INPUT " + outline(definition.get("inputSchema", {})), "OUTPUT " + outline(definition.get("outputSchema", {})), " ".join(tool["capabilities"] + tool["target_types"] + [tool["stage"], tool["target_mode"]])])
            yield tool["id"], "tool", tool["source"], tool, text

    def update(self):
        import json
        changed, unchanged, expected = [], 0, set()
        for key, kind, source, metadata, text in self.inputs():
            expected.add(key)
            content_hash = digest({"metadata": metadata, "text": text, "representation": "standalone-purpose-and-token-passages-v2"})
            existing = self.db.execute("SELECT content_hash,model FROM documents WHERE id=?", (key,)).fetchone()
            if existing and existing["content_hash"] == content_hash and existing["model"] == self.embedder.version:
                unchanged += 1
            else:
                changed.append((key, kind, source, json.dumps(metadata, ensure_ascii=False), text, content_hash))
        if changed:
            chunks = []
            for row in changed:
                metadata = json.loads(row[3])
                # Preserve the routing purpose as an independent vector. Adding
                # a long reference must not erase a previously meaningful short
                # description by mixing it into a full token window.
                summary = metadata.get("purpose") or metadata.get("definition", {}).get("description")
                chunks.append(([summary] if summary else []) + self.embedder.chunks(row[4]))
            vectors = self.embedder.encode([text for parts in chunks for text in parts])
            offset = 0
            for row, parts in zip(changed, chunks):
                vector = vectors[offset:offset + len(parts)]
                offset += len(parts)
                self.db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?)", (*row, self.embedder.version, vector.tobytes()))
        removed = 0
        for row in self.db.execute("SELECT id FROM documents").fetchall():
            if row["id"] not in expected:
                self.db.execute("DELETE FROM documents WHERE id=?", (row["id"],))
                removed += 1
        self.db.commit()
        manifest = {"catalog_version": self.catalog["version"], "representation": "standalone-purpose-and-token-passages-v2", "model": self.embedder.manifest, "pipeline": self.embedder.pipeline, "model_fingerprint": self.embedder.version, "documents": len(expected), "changed": len(changed), "unchanged": unchanged, "removed": removed, "updated_at": now(), "algorithm": "normalized quantized multilingual MiniLM vectors; BM25 k1=1.5 b=0.75; RRF k=60", "semantic_floor": 0.36, "warning": "heuristic relevance floor; not a calibrated confidence or universal precision claim"}
        write_json(self.manifest_path, manifest)
        return manifest

    def search(self, query, limit=12, kind=None):
        import json
        if not query.strip() or len(query) > 4000 or not 1 <= limit <= 50:
            raise GateError("invalid_arguments", "Expected a nonempty query <=4000 characters and limit 1..50")
        manifest_path = self.manifest_path
        if manifest_path.exists() and read_json(manifest_path)["catalog_version"] != self.catalog["version"]:
            raise GateError("stale_index", "Catalog version differs from the persisted index; update explicitly")
        rows = self.db.execute("SELECT * FROM documents").fetchall()
        if any(r["model"] != self.embedder.version for r in rows):
            raise GateError("stale_index", "Index model version differs; rebuild explicitly")
        if not rows:
            raise GateError("missing_dependency", "Index not built")
        query_vector = self.embedder.encode([query])[0]
        semantic = np.array([float((np.frombuffer(r["vector"], dtype=np.float32).reshape(-1, 384) @ query_vector).max()) for r in rows])
        documents = [Counter(tokens(r["text"])) for r in rows]
        lengths = np.array([sum(d.values()) for d in documents], dtype=float)
        average = max(1, float(lengths.mean()))
        lexical = np.zeros(len(rows))
        query_tokens = set(tokens(query))
        for word in query_tokens:
            frequency = np.array([d.get(word, 0) for d in documents])
            df = int((frequency > 0).sum())
            idf = math.log(1 + (len(rows) - df + .5) / (df + .5))
            lexical += idf * frequency * 2.5 / (frequency + 1.5 * (1 - .75 + .75 * lengths / average))
        # Independent retrievers ranked in their own scale before RRF.
        sem_rank = {int(i): rank + 1 for rank, i in enumerate(np.argsort(-semantic))}
        lex_rank = {int(i): rank + 1 for rank, i in enumerate(np.argsort(-lexical)) if lexical[i] > 0}
        results = []
        for i, row in enumerate(rows):
            if kind and row["kind"] != kind:
                continue
            # A lexical name hit alone cannot create semantic scope. Specialized
            # adjudication still applies after this retrieval relevance gate.
            if float(semantic[i]) < .36:
                continue
            score = 1 / (60 + sem_rank[i]) + (1 / (60 + lex_rank[i]) if i in lex_rank else 0)
            metadata = json.loads(row["metadata"])
            results.append({"id": row["id"], "kind": row["kind"], "source": row["source"], "capabilities": metadata["capabilities"], "target_types": metadata["target_types"], "rank_score": score, "semantic_similarity": float(semantic[i]), "bm25": float(lexical[i]), "semantic_rank": sem_rank[i], "bm25_rank": lex_rank.get(i), "version": metadata["version"]})
        results.sort(key=lambda r: (-r["rank_score"], r["id"]))
        return {"status": "candidates" if results else "no_match", "query": query, "candidates": results[:limit], "catalog_version": self.catalog["version"], "model_fingerprint": self.embedder.version, "index_representation": "standalone-purpose-and-token-passages-v2", "scores_are_confidence": False}
