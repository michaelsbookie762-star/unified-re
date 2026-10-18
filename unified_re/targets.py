"""Explicit local targets only; secrets and ambient directories are never targets."""
import hashlib
from pathlib import Path

from .common import GateError, digest

SECRET_NAMES = {"cookies", "cookies.sqlite", "login data", "keychain", "auth.json", "credentials", "credentials.json", "config.toml", "local state", "web data"}
SOURCE_EXTENSIONS = {".js", ".cjs", ".mjs", ".json", ".html", ".css", ".map", ".ts", ".tsx", ".jsx"}


def denied(path):
    return any(part.lower() in SECRET_NAMES or part.lower().startswith(".env") or part.lower() in (".git", ".ssh", ".aws", ".azure", "node_modules") for part in path.parts)


def identify(path, expected_type=None):
    if not path:
        raise GateError("needs_context", "An explicit local target path is required")
    supplied = Path(path)
    if not supplied.is_absolute():
        raise GateError("needs_context", "Target path must be absolute")
    resolved = supplied.resolve()
    if denied(supplied) or denied(resolved) or supplied.is_symlink() or supplied.is_junction():
        raise GateError("policy_conflict", "Secret, ambient configuration or linked target is excluded")
    if not resolved.exists():
        raise GateError("not_found", "Target does not exist")
    files = []
    if resolved.is_dir():
        # No recursive general crawl: reject nested credentials/links rather than
        # let a downstream analyzer traverse a tree we only partially identified.
        for entry in resolved.rglob("*"):
            relative = entry.relative_to(resolved)
            if denied(relative) or entry.is_symlink() or entry.is_junction():
                raise GateError("policy_conflict", "Target tree includes excluded or linked entries; provide a sanitized explicit copy", excluded=str(relative))
            if entry.is_file():
                if entry.suffix.lower() not in SOURCE_EXTENSIONS:
                    raise GateError("unsupported", "Static JavaScript target tree contains an unreviewed file type", suffix=entry.suffix)
                files.append(entry)
                if len(files) > 2000:
                    raise GateError("unsupported", "Explicit target exceeds local bounded inventory (2000 files)")
        if len(files) > 2000:
            raise GateError("unsupported", "Explicit target exceeds local bounded inventory (2000 files)")
        detected = "javascript" if any(p.suffix.lower() in (".js", ".mjs", ".cjs") for p in files) else "artifact"
    elif resolved.is_file():
        files = [resolved]
        extension = resolved.suffix.lower()
        with resolved.open("rb") as stream:
            header = stream.read(512)
        if extension in (".js", ".mjs", ".cjs", ".asar"):
            detected = "javascript"
        elif extension in (".apk",):
            detected = "apk"
        elif extension in (".zip", ".ipa", ".msix", ".appx"):
            detected = "artifact"
        elif extension in (".har", ".pcap", ".pcapng", ".saz"):
            detected = "capture"
        elif header[:16] == b"SQLite format 3\x00":
            detected = "database"
        elif header.startswith((b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")):
            detected = "native"
        else:
            detected = "unknown"
    else:
        raise GateError("unsupported", "Target must be an ordinary file or bounded directory")
    if expected_type and expected_type != detected:
        # PE alone cannot reliably identify managed code. Require a declared
        # managed classification; REA validates the actual managed format.
        if expected_type == "managed" and detected == "native":
            detected = "managed"
        else:
            raise GateError("needs_context", "Declared type conflicts with read-only target identification", declared=expected_type, detected=detected)
    total, records = 0, []
    for file in sorted(files):
        size = file.stat().st_size
        total += size
        if total > 64 * 1024 * 1024:
            raise GateError("unsupported", "Local verification policy limits target input to 64 MiB")
        hasher = hashlib.sha256()
        with file.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        records.append({"path": file.relative_to(resolved).as_posix() if resolved.is_dir() else file.name, "size": size, "sha256": hasher.hexdigest()})
    return {"path": str(resolved), "type": detected, "sha256": digest(records) if resolved.is_dir() else records[0]["sha256"], "files": records, "bytes": total, "identity_kind": "bounded-directory-inventory" if resolved.is_dir() else "file-sha256"}
