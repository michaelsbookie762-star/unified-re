"""Fetch only public, pinned model files; never inspect ambient credentials."""
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
REV = "2c4055b12046f11709e9df2c122e59ffbdc2f900"
FILES = ["config.json", "tokenizer.json", "tokenizer_config.json", "onnx/model_quantized.onnx", "README.md"]
EXPECTED = {
    "config.json": (673, "git-sha1", "ce7fe159b2eee53ef2b9704a72a4efa6c22248b4"),
    "tokenizer_config.json": (496, "git-sha1", "9f3bfd538ec86d360dc988dac25e3cfb0c4c14d5"),
    "README.md": (1151, "git-sha1", "f074e78ef81f17421c8c0db31c1f4d22ca9bf28a"),
    "tokenizer.json": (17082913, "sha256", "b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441"),
    "onnx/model_quantized.onnx": (118308126, "sha256", "66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc"),
}


def verify(path, name):
    size, kind, expected = EXPECTED[name]
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest() if kind == "sha256" else hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if len(data) != size or actual != expected:
        raise RuntimeError("Public model integrity mismatch: " + name)


def download(path, name):
    size = EXPECTED[name][0]
    url = f"https://huggingface.co/{REPO}/resolve/{REV}/{name}?download=true"
    partial = path.with_suffix(path.suffix + ".partial")
    start = partial.stat().st_size if partial.exists() else 0
    chunks = [(i, min(i + 4 * 1024 * 1024, size)) for i in range(start, size, 4 * 1024 * 1024)]
    cache = path.parent / (path.name + ".chunks")
    cache.mkdir(exist_ok=True)

    def fetch(bounds):
        first, end = bounds
        fragment = cache / f"{first}-{end}.bin"
        if not fragment.exists() or fragment.stat().st_size != end - first:
            subprocess.run(["curl.exe", "-q", "--fail", "--location", "--silent", "--show-error", "--retry", "3", "--retry-all-errors", "--connect-timeout", "15", "--max-time", "120", "--range", f"{first}-{end - 1}", "--output", str(fragment), url + f"&part={first}"], check=True)
        if fragment.stat().st_size != end - first:
            raise RuntimeError("Range response length mismatch")
        print(name, f"range {first}-{end} verified-length", flush=True)
        return fragment

    with ThreadPoolExecutor(max_workers=3) as pool:
        fragments = list(pool.map(fetch, chunks))
    with partial.open("ab") as out:
        for fragment in fragments:
            with fragment.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    out.write(chunk)
    verify(partial, name)
    partial.replace(path)


def main():
    directory = ROOT / "models" / "multilingual-minilm"
    entries = []
    for name in FILES:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            download(path, name)
        verify(path, name)
        entries.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
        print(name, path.stat().st_size, flush=True)
    manifest = {"repository": REPO, "revision": REV, "pooling": "attention-mask-mean", "normalization": "l2", "dimension": 384, "license": "Apache-2.0 (upstream sentence-transformers model)", "files": entries}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
