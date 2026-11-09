"""SideStack VS-27 — the start-on-click launcher page (sidestack/scripts/voice_studio_launcher.py).

The server runs on an ephemeral port with the Host header set to the real one.
Nothing is started: app_up and run_start are replaced.
"""
from __future__ import annotations

import http.client
import http.server
import importlib.util
import json
import os
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "sidestack", "scripts", "voice_studio_launcher.py")
HOST = "localhost:3901"
ORIGIN = "http://localhost:3901"


@pytest.fixture
def launcher(monkeypatch):
    spec = importlib.util.spec_from_file_location("vs_launcher_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = {"up": False, "starts": []}
    monkeypatch.setattr(mod, "app_up", lambda timeout=2.0: state["up"])
    monkeypatch.setattr(mod, "run_start", lambda cmd: state["starts"].append(cmd))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(method, path, host=HOST, token=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        headers = {"Host": host}
        if token:
            headers["X-Launch-Token"] = token
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, headers=headers)
        r = conn.getresponse()
        body = r.read().decode("utf-8")
        conn.close()
        return r.status, dict(r.getheaders()), body

    yield mod, state, call
    server.shutdown()


def test_l1_health_is_open(launcher):
    _, _, call = launcher
    assert call("GET", "/health", host="host.docker.internal:3901")[0] == 200


def test_l2_other_hosts_are_refused(launcher):
    mod, state, call = launcher
    evil = "evil.example:3901"
    assert call("GET", "/", host=evil)[0] == 403
    assert call("GET", "/api/status", host=evil, token=mod.TOKEN)[0] == 403
    assert call("POST", "/api/start", host=evil, token=mod.TOKEN, origin=ORIGIN)[0] == 403
    assert state["starts"] == []


def test_l3_forwards_when_voice_studio_is_up(launcher):
    _, state, call = launcher
    state["up"] = True
    status, headers, _ = call("GET", "/")
    assert status == 302 and headers["Location"] == "http://localhost:3900/"


def test_l4_page_when_down(launcher):
    mod, _, call = launcher
    status, headers, body = call("GET", "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert mod.TOKEN in body and "Starting Voice Studio" in body
    assert headers["X-Frame-Options"] == "DENY"


def test_l5_start_needs_token_and_origin_and_is_rate_limited(launcher):
    mod, state, call = launcher
    assert call("POST", "/api/start", origin=ORIGIN)[0] == 403
    assert call("POST", "/api/start", token=mod.TOKEN, origin="https://evil.example")[0] == 403
    assert call("POST", "/api/start", token=mod.TOKEN)[0] == 403
    assert state["starts"] == []
    status, _, body = call("POST", "/api/start", token=mod.TOKEN, origin=ORIGIN)
    assert status == 200 and json.loads(body)["state"] == "started"
    assert len(state["starts"]) == 1
    cmd = state["starts"][0]
    assert cmd[-3:] == [mod.START_SCRIPT.__str__(), "-TimeoutSec", "180"]
    assert json.loads(call("POST", "/api/start", token=mod.TOKEN, origin=ORIGIN)[2])["state"] == "starting"
    assert len(state["starts"]) == 1
    state["up"] = True
    assert json.loads(call("POST", "/api/start", token=mod.TOKEN, origin=ORIGIN)[2])["state"] == "running"
    assert len(state["starts"]) == 1


def test_l6_status_needs_the_token(launcher):
    mod, state, call = launcher
    assert call("GET", "/api/status")[0] == 403
    status, _, body = call("GET", "/api/status", token=mod.TOKEN)
    assert status == 200 and json.loads(body) == {"up": False, "url": "http://localhost:3900/"}


def test_l7_start_script_is_the_neighbour_launcher(launcher):
    mod, _, _ = launcher
    assert mod.START_SCRIPT.name == "Start-VoiceStudio-ODS.ps1"
    assert mod.START_SCRIPT.parent == mod.HERE and mod.START_SCRIPT.exists()


def test_l8_unknown_paths(launcher):
    mod, _, call = launcher
    assert call("GET", "/nope")[0] == 404
    assert call("POST", "/api/launch", token=mod.TOKEN, origin=ORIGIN)[0] == 404
