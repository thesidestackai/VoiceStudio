"""SideStack fork (VS-27): start-on-click launcher for Voice Studio.

ODS links its "SideStack Voice Studio" entry here (http://localhost:3901/).
When Voice Studio already answers on 127.0.0.1:3900 the page forwards to it.
Otherwise the page starts it with Start-VoiceStudio-ODS.ps1 (the launcher's own
folder) and forwards once /health answers.

Safety:
- Binds 127.0.0.1 only.
- The page and API answer only for Host localhost/127.0.0.1 on this port
  (blocks DNS rebinding). /health is open so ODS can health-check it.
- Starting is POST-only and needs the per-process token embedded in the page
  plus a same-origin Origin header, so another website cannot trigger it.
- It runs one fixed command with no input from the request. Starts are
  rate-limited. Stdlib only; logs nothing.
Run with: python -I voice_studio_launcher.py
"""
from __future__ import annotations

import http.server
import json
import pathlib
import secrets
import shutil
import subprocess
import threading
import time
import urllib.request

PORT = 3901
APP = "http://127.0.0.1:3900"
APP_PUBLIC = "http://localhost:3900/"
HERE = pathlib.Path(__file__).resolve().parent
START_SCRIPT = HERE / "Start-VoiceStudio-ODS.ps1"
TOKEN = secrets.token_urlsafe(32)
ALLOWED_HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}
MIN_START_INTERVAL = 200.0  # longer than the start script's 180 s timeout
_state = {"last_start": None}
_lock = threading.Lock()


def app_up(timeout: float = 2.0) -> bool:
    """Voice Studio's backend answers its public liveness route."""
    try:
        with urllib.request.urlopen(f"{APP}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001 — any failure means "not up yet"
        return False


def start_command() -> list[str]:
    pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
    return [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_SCRIPT), "-TimeoutSec", "180"]


def run_start(cmd: list[str]) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(cmd, cwd=str(HERE), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start() -> str:
    """Start Voice Studio unless it is up or a start ran within the last minute."""
    if app_up():
        return "running"
    with _lock:
        now = time.monotonic()
        last = _state["last_start"]
        if last is not None and now - last < MIN_START_INTERVAL:
            return "starting"
        _state["last_start"] = now
    run_start(start_command())
    return "started"


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SideStack Voice Studio</title>
<style>
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#9a9993;--bad:#ef7a70}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:560px;margin:0 auto;padding:64px 16px;text-align:center}
h1{font-size:22px;margin:0 0 8px}#msg{color:var(--muted)}.bad{color:var(--bad)}
</style></head><body><main>
<h1>SideStack Voice Studio</h1>
<p id="msg">Starting Voice Studio&hellip; this takes up to a minute.</p>
</main>
<script>
const TOKEN = "__TOKEN__";
const msg = document.getElementById("msg");
const call = (path, method) => fetch(path, {method, headers: {"X-Launch-Token": TOKEN}}).then(r => r.json());
async function poll(tries) {
  const s = await call("/api/status", "GET").catch(() => ({}));
  if (s.up) { location.replace(s.url); return; }
  if (tries <= 0) { msg.className = "bad"; msg.textContent = "Voice Studio did not start. Check the log folder, then reload this page."; return; }
  setTimeout(() => poll(tries - 1), 2000);
}
call("/api/start", "POST").then(() => poll(120)).catch(() => {
  msg.className = "bad"; msg.textContent = "The launcher could not start Voice Studio.";
});
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # logs nothing
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _host_ok(self):
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self._json(200, {"ok": True})
        if not self._host_ok():
            return self._json(403, {"error": "forbidden"})
        if path == "/":
            if app_up():
                return self._send(302, b"", "text/plain", {"Location": APP_PUBLIC})
            return self._send(200, PAGE.replace("__TOKEN__", TOKEN).encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/status":
            if self.headers.get("X-Launch-Token") != TOKEN:
                return self._json(403, {"error": "forbidden"})
            return self._json(200, {"up": app_up(), "url": APP_PUBLIC})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/start":
            return self._json(404, {"error": "not found"})
        if (not self._host_ok() or self.headers.get("X-Launch-Token") != TOKEN
                or self.headers.get("Origin") not in ALLOWED_ORIGINS):
            return self._json(403, {"error": "forbidden"})
        self._json(200, {"state": start()})


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
