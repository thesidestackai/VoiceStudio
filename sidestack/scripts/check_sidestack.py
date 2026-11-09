#!/usr/bin/env python3
"""Validate the SideStack folder of the VoiceStudio fork (stdlib only, no network).

Checks:
  1. required files exist
  2. every lane spec (lanes/VS-*.md) has the metadata lines and sections from LANE-TEMPLATE.md
  3. every lane linked from lanes/README.md exists, and every lane file is in the tracker
  4. relative Markdown links inside sidestack/ resolve
  5. ods/manifest.yaml has the fields ODS needs, and its port matches config/ods.env.example
  6. config/ods.env.example is KEY=VALUE only (no inline comments) and carries no secret values
  7. no secret-looking strings in any file under sidestack/ (work/ is skipped: gitignored)

Usage:  python sidestack/scripts/check_sidestack.py      → prints OK, exit 0; else lists problems, exit 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # sidestack/

REQUIRED_FILES = [
    "README.md",
    "PLAN.md",
    "ARCHITECTURE.md",
    "AGENTS-SIDESTACK.md",
    ".gitignore",
    "config/ods.env.example",
    "harness/README.md",
    "harness/KICKOFF-PROMPT.md",
    "harness/LANE-TEMPLATE.md",
    "lanes/README.md",
    "ods/manifest.yaml",
    "ods/APPLY.md",
    "scripts/Test-VoiceStudioOds.ps1",
    "scripts/check_sidestack.py",
]

LANE_META = ("**Phase:**", "**Run by:**", "**Gate:**", "**Status:**")
LANE_SECTIONS = ("## Goal", "## Files", "## Preflight", "## Steps", "## Acceptance",
                 "## Out of scope", "## Reviewer notes")

MANIFEST_FIELDS = {
    "schema_version": r"^schema_version:\s*ods\.services\.v1\s*$",
    "service.id": r"^\s+id:\s*sidestack-voice-studio\s*$",
    "service.port": r"^\s+port:\s*(\d+)\s*$",
    "service.health": r"^\s+health:\s*/\S*\s*$",
    "service.type": r"^\s+type:\s*windows-host\s*$",
    "service.default_host": r"^\s+default_host:\s*host\.docker\.internal\s*$",
}

SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "long hex secret": re.compile(r"\b[0-9a-f]{40,}\b"),
    "Bearer literal": re.compile(r"Bearer\s+(?!\$)[A-Za-z0-9._~+/-]{24,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
SECRET_ENV_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$")
TEXT_SUFFIXES = {".md", ".py", ".ps1", ".yaml", ".yml", ".example", ".txt", ".json", ""}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def check_required(problems: list[str]) -> None:
    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            problems.append(f"missing required file: sidestack/{name}")


def lane_files() -> list[Path]:
    return sorted((ROOT / "lanes").glob("VS-*.md"))


def check_lanes(problems: list[str]) -> None:
    for path in lane_files():
        text = path.read_text(encoding="utf-8")
        head = text.splitlines()[0] if text else ""
        lane_id = path.name.split("-", 2)[0] + "-" + path.name.split("-", 2)[1]
        if not head.startswith(f"# {lane_id} "):
            problems.append(f"{rel(path)}: first line must start with '# {lane_id} '")
        for meta in LANE_META:
            if meta not in text:
                problems.append(f"{rel(path)}: missing metadata line {meta}")
        positions = []
        for section in LANE_SECTIONS:
            m = re.search(rf"^{re.escape(section)}\b", text, re.MULTILINE)
            if not m:
                problems.append(f"{rel(path)}: missing section '{section}'")
            else:
                positions.append(m.start())
        if positions != sorted(positions):
            problems.append(f"{rel(path)}: sections out of template order")

    tracker = (ROOT / "lanes" / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\((VS-[^)]+\.md)\)", tracker))
    for name in linked:
        if not (ROOT / "lanes" / name).is_file():
            problems.append(f"lanes/README.md links missing lane file {name}")
    for path in lane_files():
        if path.name not in linked:
            problems.append(f"lanes/README.md does not link {path.name}")


def check_links(problems: list[str]) -> None:
    for path in ROOT.rglob("*.md"):
        if "work" in path.relative_to(ROOT).parts:
            continue
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                problems.append(f"{rel(path)}: broken link -> {target}")


def manifest_port(problems: list[str]) -> int | None:
    text = (ROOT / "ods" / "manifest.yaml").read_text(encoding="utf-8")
    port = None
    for field, pattern in MANIFEST_FIELDS.items():
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            problems.append(f"ods/manifest.yaml: missing or wrong {field}")
        elif field == "service.port":
            port = int(m.group(1))
    if "\t" in text:
        problems.append("ods/manifest.yaml: tab characters are not valid YAML indentation")
    return port


def check_env(problems: list[str], port: int | None) -> None:
    path = ROOT / "config" / "ods.env.example"
    values: dict[str, str] = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            problems.append(f"config/ods.env.example:{n}: not KEY=VALUE")
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            problems.append(f"config/ods.env.example:{n}: bad key {key!r}")
        if " #" in value or "\t#" in value:
            problems.append(f"config/ods.env.example:{n}: inline comment after value")
        if SECRET_ENV_NAME.search(key) and value:
            problems.append(f"config/ods.env.example:{n}: {key} must not have a value in the template")
        values[key] = value
    for required in ("TRANSLATE_BASE_URL", "OMNIVOICE_ASR_BACKEND", "ASR_OPENAI_COMPAT_BASE_URL",
                     "OMNIVOICE_PORT", "OMNIVOICE_BIND_HOST", "OMNIVOICE_DATA_DIR"):
        if required not in values:
            problems.append(f"config/ods.env.example: missing {required}")
    for url_key in ("TRANSLATE_BASE_URL", "ASR_OPENAI_COMPAT_BASE_URL"):
        url = values.get(url_key, "")
        if url.startswith("http://") and not re.match(r"http://(127\.0\.0\.1|localhost)[:/]", url):
            problems.append(f"config/ods.env.example: {url_key} is plain HTTP off loopback")
    if values.get("OMNIVOICE_BIND_HOST") not in (None, "127.0.0.1"):
        problems.append("config/ods.env.example: OMNIVOICE_BIND_HOST must stay 127.0.0.1")
    if port is not None and values.get("OMNIVOICE_PORT") != str(port):
        problems.append(f"port mismatch: manifest {port} vs OMNIVOICE_PORT {values.get('OMNIVOICE_PORT')}")


def check_secrets(problems: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or "work" in path.relative_to(ROOT).parts:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS.items():
            if path.name == "check_sidestack.py":
                break  # this file defines the patterns
            if pattern.search(text):
                problems.append(f"{rel(path)}: looks like it contains a {label}")


def main() -> int:
    problems: list[str] = []
    check_required(problems)
    if not problems:
        check_lanes(problems)
        check_links(problems)
        check_env(problems, manifest_port(problems))
        check_secrets(problems)
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: {len(REQUIRED_FILES)} required files, {len(lane_files())} lane specs, links, "
          f"manifest, env profile, secret scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
