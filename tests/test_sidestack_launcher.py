"""VS-07: the Start-VoiceStudio-ODS.ps1 launcher.

L1-L7 and L10-L12 run the script under Windows PowerShell (skipped off-Windows);
L8-L9 check the profile and ODS translation resolution on any OS.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "sidestack" / "scripts" / "Start-VoiceStudio-ODS.ps1"
PROFILE = REPO_ROOT / "sidestack" / "config" / "ods.env.example"

win_only = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="Windows launcher",
)


def _run(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    # -ExecutionPolicy Bypass is a native command; force Continue so the script's
    # own $ErrorActionPreference and exit codes stay in control.
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60, env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _env(**changes: object) -> dict[str, str]:
    env = dict(os.environ)
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _profile_text() -> str:
    return PROFILE.read_text(encoding="utf-8")


# ── L1: -DryRun -Json with the default profile ──────────────────────────────────────
@win_only
def test_l1_dryrun_json_default_profile():
    code, out = _run(["-DryRun", "-Json"], _env())
    assert code == 0, out
    plan = json.loads(out)
    assert plan["url"] == "http://127.0.0.1:3900/"
    assert plan["env"]["LLM_DEFAULT_PROVIDER"] == "ods"
    assert plan["env"]["TRANSLATE_PROVIDER"] == "openai"
    assert plan["env"]["SIDESTACK_VRAM_ADMISSION"] == "1"
    assert "OMNIVOICE_SERVER_MODE" not in plan["env"]
    assert plan["python"].endswith("\\Scripts\\python.exe")


# ── L2: the relay key is never printed ──────────────────────────────────────────────
@win_only
def test_l2_relay_key_never_printed():
    marker = "test-relay-key-7f3a9c"
    code_json, out_json = _run(["-DryRun", "-Json"], _env(ODS_LOCAL_MODEL_RELAY_KEY=marker))
    assert code_json == 0
    assert json.loads(out_json)["relay_key"] == "present"
    code_plain, out_plain = _run(["-DryRun"], _env(ODS_LOCAL_MODEL_RELAY_KEY=marker))
    assert code_plain == 0
    leaked = marker in out_json or marker in out_plain
    assert not leaked, "relay key printed"


# ── L3: -NoUserEnv with the key removed reports missing ─────────────────────────────
@win_only
def test_l3_no_user_env_missing():
    code, out = _run(["-DryRun", "-Json", "-NoUserEnv"], _env(ODS_LOCAL_MODEL_RELAY_KEY=None))
    assert code == 0, out
    plan = json.loads(out)
    assert plan["relay_key"] == "missing"
    assert any("ODS_LOCAL_MODEL_RELAY_KEY" in w for w in plan["warnings"])


# ── L4: a non KEY=VALUE line fails parsing ──────────────────────────────────────────
@win_only
def test_l4_bad_profile_line(tmp_path):
    profile = tmp_path / "bad.env"
    profile.write_text("OMNIVOICE_BIND_HOST=127.0.0.1\nNOT A KV LINE\n", encoding="utf-8")
    code, out = _run(["-DryRun", "-ProfilePath", str(profile)], _env())
    assert code == 2, out
    assert "line" in out.lower()


# ── L5: a non-loopback bind host fails validation ───────────────────────────────────
@win_only
def test_l5_bind_host_rejected(tmp_path):
    profile = tmp_path / "bad-host.env"
    profile.write_text(
        _profile_text().replace("OMNIVOICE_BIND_HOST=127.0.0.1", "OMNIVOICE_BIND_HOST=0.0.0.0"),
        encoding="utf-8",
    )
    code, out = _run(["-DryRun", "-ProfilePath", str(profile)], _env())
    assert code == 2, out


# ── L6: OMNIVOICE_SERVER_MODE=1 fails validation ────────────────────────────────────
@win_only
def test_l6_server_mode_rejected(tmp_path):
    profile = tmp_path / "server-mode.env"
    profile.write_text(_profile_text() + "\nOMNIVOICE_SERVER_MODE=1\n", encoding="utf-8")
    code, out = _run(["-DryRun", "-ProfilePath", str(profile)], _env())
    assert code == 2, out


# ── L7: a secret-named key with a value fails, and the value is not echoed ───────────
@win_only
def test_l7_secret_value_rejected(tmp_path):
    secret = "zz-secret-41"
    profile = tmp_path / "secret.env"
    profile.write_text(_profile_text() + f"\nTRANSLATE_API_KEY={secret}\n", encoding="utf-8")
    code, out = _run(["-DryRun", "-ProfilePath", str(profile)], _env())
    assert code == 2, out
    leaked = secret in out
    assert not leaked, "secret value printed"


# ── L8: the example profile parses to the expected SideStack values (any OS) ─────────
def test_l8_profile_content():
    profile: dict[str, str] = {}
    for line in PROFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        profile[key.strip()] = value.strip()
    assert profile["LLM_DEFAULT_PROVIDER"] == "ods"
    assert profile["TRANSLATE_PROVIDER"] == "openai"
    assert "OMNIVOICE_SERVER_MODE" not in profile
    assert profile["OMNIVOICE_ENV_FILE"].startswith(profile["OMNIVOICE_DATA_DIR"])
    # VS-30: room for a cold ODS Whisper model reload (about 103 s measured in VS-29).
    assert float(profile["OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S"]) >= 300


# ── L9: dub translation resolves to ODS (any OS) ─────────────────────────────────────
def test_l9_translation_engine_resolves_to_ods(monkeypatch, clean_llm_env):
    from services import settings_store as ss
    from services import llm_providers as _lp

    text: dict[str, str] = {}
    secrets: dict[str, str] = {}
    monkeypatch.setattr(ss, "get_text", lambda k, default=None: text.get(k, default))
    monkeypatch.setattr(ss, "set_text", lambda k, v: text.__setitem__(k, v))
    monkeypatch.setattr(ss, "get_secret", lambda n: secrets.get(n))
    monkeypatch.setattr(ss, "set_secret", lambda n, v: secrets.__setitem__(n, v) if v else secrets.pop(n, None))
    monkeypatch.setattr(ss, "list_secret_names", lambda: list(secrets))
    _lp._text, _lp._secrets = text, secrets

    profile: dict[str, str] = {}
    for line in PROFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        profile[key.strip()] = value.strip()

    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", profile["LLM_DEFAULT_PROVIDER"])
    monkeypatch.setenv("TRANSLATE_PROVIDER", profile["TRANSLATE_PROVIDER"])
    monkeypatch.setenv("TRANSLATE_BASE_URL", profile["TRANSLATE_BASE_URL"])
    monkeypatch.setenv("TRANSLATE_MODEL", profile["TRANSLATE_MODEL"])
    monkeypatch.setenv("ODS_LOCAL_MODEL_RELAY_KEY", "dummy")

    from services import translation_engines as engines
    assert engines._configured({"id": "openai"}) == (True, "ODS (SideStack local)")


# ── L10-L12: -Stop against stand-in servers (Windows only) ──────────────────────────
STANDIN = """
import http.server
import socketserver
import sys

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass

port = int(sys.argv[1])
socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", port), Handler) as server:
    server.serve_forever()
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _stop_case(tmp_path: Path, script_name: str, port: int) -> tuple[int, str, subprocess.Popen]:
    """Start a stand-in on `port` (or do nothing if port is None), run -Stop."""
    standin = tmp_path / script_name
    standin.write_text(STANDIN, encoding="utf-8")
    text = _profile_text().replace("OMNIVOICE_PORT=3900", f"OMNIVOICE_PORT={port}")
    profile = tmp_path / "stop.env"
    profile.write_text(text, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(standin), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port), f"stand-in {script_name} did not open port {port}"
        code, out = _run(["-Stop", "-ProfilePath", str(profile)], _env())
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        raise
    return code, out, proc


# ── L10: -Stop stops the Voice Studio stand-in (main.py) ────────────────────────────
@win_only
def test_l10_stop_main_py(tmp_path):
    port = _free_port()
    code, out, proc = _stop_case(tmp_path, "main.py", port)
    try:
        assert code == 0, out
        assert "stopped pid" in out, out
        # The venv python launcher exits a moment after its child; wait, don't poll.
        proc.wait(timeout=10)  # TimeoutExpired here means the stand-in survived -Stop
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


# ── L11: -Stop refuses to stop a non-Voice Studio owner ─────────────────────────────
@win_only
def test_l11_stop_other_program(tmp_path):
    port = _free_port()
    code, out, proc = _stop_case(tmp_path, "server.py", port)
    try:
        assert code == 3, out
        assert "another program" in out, out
        time.sleep(1)
        assert proc.poll() is None, "-Stop touched a program that is not Voice Studio"
    finally:
        proc.kill()
        proc.wait(timeout=10)


# ── L12: -Stop on a free port prints 'not running' ──────────────────────────────────
@win_only
def test_l12_stop_free_port(tmp_path):
    port = _free_port()
    text = _profile_text().replace("OMNIVOICE_PORT=3900", f"OMNIVOICE_PORT={port}")
    profile = tmp_path / "stop.env"
    profile.write_text(text, encoding="utf-8")
    code, out = _run(["-Stop", "-ProfilePath", str(profile)], _env())
    assert code == 0, out
    assert "not running" in out, out

def test_l13_no_start_process_redirection():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "-RedirectStandardOutput" not in src
    assert "-RedirectStandardError" not in src
    assert "$env:ComSpec" in src


# ── L14: commercial-only mode and -AllowNonCommercial (VS-18) ───────────────────────
@win_only
def test_l14_commercial_only_switch():
    code, out = _run(["-DryRun", "-Json"], _env())
    assert code == 0, out
    plan = json.loads(out)
    assert plan["env"]["SIDESTACK_COMMERCIAL_ONLY"] == "1"
    assert plan["licence_mode"] == "commercial-only"

    code, out = _run(["-DryRun", "-Json", "-AllowNonCommercial"], _env())
    assert code == 0, out
    plan = json.loads(out)
    assert plan["env"]["SIDESTACK_COMMERCIAL_ONLY"] == "0"
    assert plan["licence_mode"] == "non-commercial allowed"
