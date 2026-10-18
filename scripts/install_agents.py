"""Add global Codex and existing Pi bridge entries, preserving other settings."""
import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def backup(path):
    if path.exists():
        copy = path.with_name(path.name + ".unified-re-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
        copy.write_bytes(path.read_bytes())
        return str(copy)


def main():
    if os.name != "nt":
        raise SystemExit("This installer targets Windows Codex and the installed Pi MCP bridge.")
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    pi_home = Path(os.environ.get("PI_CODING_AGENT_DIR", home / ".pi/agent"))
    python = ROOT / ".venv/Scripts/python.exe"
    bridge = pi_home / "extensions/pi-mcp-bridge/mcp-servers.json"
    codex = codex_home / "config.toml"
    skill = home / ".agents/skills/unified-re"
    target = ROOT / ".agents/skills/unified-re"
    if not python.is_file() or not bridge.is_file():
        raise SystemExit("Run setup.ps1 first; Pi must already have pi-mcp-bridge installed.")
    entry = {"command": str(python), "args": ["-X", "utf8", str(ROOT / "scripts/serve.py")], "cwd": str(ROOT)}
    raw = codex.read_text(encoding="utf-8-sig") if codex.exists() else ""
    config = tomllib.loads(raw)
    previous = config.get("mcp_servers", {}).get("unified-re")
    if previous and any(previous.get(k) != v for k, v in entry.items()):
        raise SystemExit("A different Codex unified-re registration exists; no configuration changed.")
    pi_config = json.loads(bridge.read_text(encoding="utf-8-sig"))
    pi_previous = pi_config["mcpServers"].get("unified-re")
    if pi_previous and any(pi_previous.get(k) != v for k, v in entry.items()):
        raise SystemExit("A different Pi unified-re registration exists; no configuration changed.")
    if skill.exists() and skill.resolve() != target.resolve():
        raise SystemExit("A different global unified-re Skill exists; no configuration changed.")
    if (skill.is_symlink() or skill.is_junction()) and not skill.exists():
        raise SystemExit("A broken global Skill link exists; preserve and inspect it first.")
    backups = []
    if not skill.exists():
        skill.parent.mkdir(parents=True, exist_ok=True)
        # A junction needs no developer-mode symlink privilege on Windows.
        skill_arg, target_arg = (str(p).replace("'", "''") for p in (skill, target))
        command = f"New-Item -ItemType Junction -Path '{skill_arg}' -Target '{target_arg}' | Out-Null"
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], check=True, capture_output=True)
    if not previous:
        backups.append(backup(codex))
        codex.parent.mkdir(parents=True, exist_ok=True)
        block = "\n\n[mcp_servers.unified-re]\n"
        block += "\n".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in entry.items())
        block += "\nstartup_timeout_sec = 40\ntool_timeout_sec = 180\nenabled = true\n"
        codex.write_text(raw + block, encoding="utf-8")
        tomllib.loads(codex.read_text(encoding="utf-8"))
    if not pi_previous:
        backups.append(backup(bridge))
        pi_config["mcpServers"]["unified-re"] = {**entry, "type": "stdio", "startupTimeoutSec": 40, "toolTimeoutSec": 180}
        bridge.write_text(json.dumps(pi_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"skill": str(skill), "codex_config": str(codex), "pi_config": str(bridge),
                      "backups": [p for p in backups if p], "restart_clients": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
