import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "unified-re"
VAR = ROOT / "var"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class GateError(Exception):
    def __init__(self, status, reason, **details):
        super().__init__(reason)
        self.status, self.reason, self.details = status, reason, details

    def as_dict(self):
        return {"status": self.status, "reason": self.reason, **self.details}


def public_error(error):
    if isinstance(error, GateError):
        return error.as_dict()
    return {"status": "backend_failure", "reason": type(error).__name__}
