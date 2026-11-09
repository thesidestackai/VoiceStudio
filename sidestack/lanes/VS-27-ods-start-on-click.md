# VS-27 — Start-on-click launcher page for the ODS link

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (ODS manifest update, logon task, live check).
- **Gate:** none for Part A. Part B needs ODS change approval (given 2026-11-08: "Start-on-click launcher").
- **Depends on:** VS-07 (launcher script), VS-08 (ODS Applications entry)
- **Status:** verified (Part A; Part B PASS, 2026-11-08)

## Goal

ODS → Applications → **SideStack Voice Studio** works whether or not Voice Studio is running.

**Why:** the VS-08 entry links `http://localhost:3900/`. When Voice Studio is stopped, the link is dead, and ODS never starts Windows-host apps.

**Fix:** a small stdlib page on `127.0.0.1:3901` (`sidestack/scripts/voice_studio_launcher.py`), the same pattern as the working Claude Code (ODS) launcher page:
- `GET /`: if Voice Studio's `/health` answers, a 302 to `http://localhost:3900/`. Otherwise a page that POSTs `/api/start`, polls `/api/status` every 2 s and forwards once Voice Studio is up.
- `POST /api/start`: runs one fixed command, `Start-VoiceStudio-ODS.ps1 -TimeoutSec 180` from the page's own folder (default, commercial-only profile), with no window. It answers `running`, `starting` (a start ran within the last 200 s) or `started`.
- **Safety:**
  - binds `127.0.0.1` only;
  - the page and API answer only for `Host: localhost:3901` or `127.0.0.1:3901` (blocks DNS rebinding);
  - `/api/start` is POST-only and needs the per-process token embedded in the page plus a same-origin `Origin`;
  - `/api/status` needs the token;
  - `/health` is open, for ODS's health check from its container;
  - the page sets CSP, `X-Frame-Options: DENY` and `no-store`, and logs nothing.
- The ODS manifest points at port 3901. `check_sidestack.py` now checks manifest port = launcher page port, and launcher target port = `OMNIVOICE_PORT`.

## Files

| Path | Change |
|---|---|
| `sidestack/scripts/voice_studio_launcher.py` | new |
| `tests/test_sidestack_vs_launcher.py` | new: L1–L8 |
| `sidestack/ods/manifest.yaml` | edit: 1 replacement (port 3900 → 3901) |
| `sidestack/scripts/check_sidestack.py` | edit: 3 replacements |
| `sidestack/ARCHITECTURE.md` | edit: 1 replacement |
| `sidestack/ods/APPLY.md` | append: the VS-27 section |
| `sidestack/lanes/VS-27-ods-start-on-click.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Run from the worktree root.

```powershell
git status --short     # expect exactly: M sidestack/UPSTREAM-SYNC.md, M sidestack/lanes/README.md, M sidestack/lanes/VS-18-commercial-only-mode.md, M sidestack/lanes/VS-26-engine-setup-sidestack.md, ?? sidestack/lanes/VS-27-ods-start-on-click.md
Select-String sidestack\ods\manifest.yaml -Pattern '^  port: 3900$'   # expect: 1 match
Test-Path sidestack\scripts\voice_studio_launcher.py   # expect: False
Test-Path tests\test_sidestack_vs_launcher.py   # expect: False
```

The four modified files are reviewer results from earlier lanes. Leave them as they are.

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep each file's line endings. Do not run `git checkout`, `git stash`, `git reset`, `git clean` or `git restore`.

1. In `sidestack/ods/manifest.yaml`, make 1 replacement.
   - Replace:
     ```yaml
       # The ODS dashboard container reaches Windows loopback through host.docker.internal.
       # Voice Studio uses ODS through the local model relay (:4007) and ODS Whisper (:9000).
       default_host: host.docker.internal
       port: 3900
       # Public, unauthenticated liveness route of the VoiceStudio backend.
       health: /health
       external_port_default: 3900
     ```
     with:
     ```yaml
       # ODS links the start-on-click launcher page (voice_studio_launcher.py, lane VS-27) on
       # 127.0.0.1:3901: it forwards to Voice Studio when it is up, or starts it, then forwards.
       # The ODS dashboard container reaches Windows loopback through host.docker.internal.
       # Voice Studio uses ODS through the local model relay (:4007) and ODS Whisper (:9000).
       default_host: host.docker.internal
       port: 3901
       # The launcher page's open liveness route. The page and its API answer only for
       # Host localhost/127.0.0.1:3901.
       health: /health
       external_port_default: 3901
     ```
2. In `sidestack/scripts/check_sidestack.py`, make 3 replacements.
   - In the module docstring, replace:
     ```python
       5. ods/manifest.yaml has the fields ODS needs, and its port matches config/ods.env.example
     ```
     with:
     ```python
       5. ods/manifest.yaml has the fields ODS needs; its port is the launcher page's (VS-27), and the
          launcher forwards to OMNIVOICE_PORT from config/ods.env.example
     ```
   - In `REQUIRED_FILES`, replace:
     ```python
         "scripts/check_sidestack.py",
     ]
     ```
     with:
     ```python
         "scripts/check_sidestack.py",
         "scripts/voice_studio_launcher.py",
     ]
     ```
   - At the end of `check_env`, replace:
     ```python
         if port is not None and values.get("OMNIVOICE_PORT") != str(port):
             problems.append(f"port mismatch: manifest {port} vs OMNIVOICE_PORT {values.get('OMNIVOICE_PORT')}")
     ```
     with:
     ```python
         # SideStack VS-27: ODS links the launcher page, which forwards to Voice Studio.
         launcher = (ROOT / "scripts" / "voice_studio_launcher.py").read_text(encoding="utf-8")
         page = re.search(r"^PORT = (\d+)$", launcher, re.MULTILINE)
         app = re.search(r'^APP = "http://127\.0\.0\.1:(\d+)"$', launcher, re.MULTILINE)
         if port is not None and (page is None or int(page.group(1)) != port):
             problems.append(f"port mismatch: manifest {port} vs launcher page {page and page.group(1)}")
         if app is None or app.group(1) != values.get("OMNIVOICE_PORT"):
             problems.append(f"port mismatch: launcher APP {app and app.group(1)} vs OMNIVOICE_PORT {values.get('OMNIVOICE_PORT')}")
     ```
3. In `sidestack/ARCHITECTURE.md`, make 1 replacement.
   - Replace:
     ```markdown
     | ODS dashboard | ODS (Docker) | ODS UI | Lists Voice Studio under Applications. Health-checks it from the container via `host.docker.internal:3900`. |
     ```
     with:
     ```markdown
     | Launcher page | Windows host (`pythonw`, started at logon) | `127.0.0.1:3901` | `sidestack/scripts/voice_studio_launcher.py` (VS-27). Forwards to Voice Studio when it is up; otherwise runs `Start-VoiceStudio-ODS.ps1`, then forwards. |
     | ODS dashboard | ODS (Docker) | ODS UI | Lists Voice Studio under Applications. Links and health-checks the launcher page from the container via `host.docker.internal:3901`. |
     ```
4. At the end of `sidestack/ods/APPLY.md`, append this section after one blank line:
   ```markdown
   ## Start-on-click launcher (lane VS-27)

   ODS links `http://localhost:3901/`, the launcher page (`sidestack/scripts/voice_studio_launcher.py`), instead of Voice Studio itself.
   - When Voice Studio is up, the page forwards to `http://localhost:3900/`.
   - Otherwise it runs `Start-VoiceStudio-ODS.ps1` (the default, commercial-only profile) and forwards once `/health` answers.
   - ODS still never starts or stops anything itself. Its health check now shows the page, not Voice Studio.

   **Needs the user's approval.** To update an installed entry:

   1. Back up the installed `manifest.yaml` to the ODS backups folder, and record its SHA-256.
   2. Stage and install the new manifest as in step 3 above. `sha256sum` must equal the repo copy's hash.
   3. Run `docker restart ods-dashboard-api`, then check it as in step 4.
   4. Start the page at logon: create a per-user scheduled task, with no elevation, that runs `pythonw.exe -I <checkout>\sidestack\scripts\voice_studio_launcher.py` at logon. Start it once by hand with `Start-ScheduledTask`.
   5. Verify:
      - With Voice Studio stopped, the Applications entry shows healthy, because the page is up. Clicking it shows "Starting Voice Studio…", then opens Voice Studio.
      - With Voice Studio running, the link opens it directly.

   Rollback: restore the backed-up manifest, run `docker restart ods-dashboard-api`, and delete the scheduled task.
   ```
5. Create `sidestack/scripts/voice_studio_launcher.py` with exactly this content (LF line endings):
   ```python
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
   ```
   Keep one newline at the end of the file.
6. Create `tests/test_sidestack_vs_launcher.py` with exactly this content (LF line endings):
   ```python
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
   ```
   Keep one newline at the end of the file.
7. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

Run from the worktree root, with `$py` and the Hard law 9 environment.

```powershell
& $py -m pytest tests/test_sidestack_vs_launcher.py -q -p no:cacheprovider   # expect: 8 passed
& $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider   # expect: 14 passed
python sidestack/scripts/check_sidestack.py           # expect: OK
git status --short    # expect: the Preflight files plus exactly the files in "Files"
```

## Part B — ODS update and live check (Operator, after approval)

Follow `sidestack/ods/APPLY.md` → "Start-on-click launcher":
1. Back up the installed manifest, install the new one, and restart `ods-dashboard-api`.
2. Create the logon task and start it.
3. With Voice Studio stopped, open the ODS Applications link. Expect the "Starting Voice Studio…" page, then Voice Studio.
4. With Voice Studio running, the link forwards at once.

## Out of scope

- Stopping Voice Studio from the page. `Start-VoiceStudio-ODS.ps1 -Stop` stays the way to stop it.
- Starting in the private profile (`-AllowNonCommercial`) from the page. The page always uses the default profile.
- A desktop shortcut.

## Reviewer notes

- **Mutation checks** (to run after the build):
  - drop the Host check in `do_POST` → L2 fails;
  - drop the Origin check → L5 fails;
  - make the rate limit always pass → L5 fails;
  - make `/health` need the Host → L1 fails;
  - set the manifest port back to 3900 → `check_sidestack.py` reports a port mismatch;
  - change the launcher's `APP` port → `check_sidestack.py` reports a port mismatch.
- L5 checks that the start command ends with the neighbouring `Start-VoiceStudio-ODS.ps1 -TimeoutSec 180`. L7 checks that the script exists next to the page.
- The page's `/health` is always 200 while the page runs. So after this lane, ODS's health dot means "the launcher is available", not "Voice Studio is up". The page itself shows which.

## Builder report

LANE: VS-27 (Part A — dsh)
STATUS: PASS
FILES CHANGED:
- sidestack/ods/manifest.yaml (step 1: port 3901 + launcher comment)
- sidestack/scripts/check_sidestack.py (step 2: #5 docstring, required file, launcher port/APP cross-checks)
- sidestack/ARCHITECTURE.md (step 3: ODS row)
- sidestack/ods/APPLY.md (step 4: VS-27 section)
- sidestack/scripts/voice_studio_launcher.py (step 5, new, spec-exact content)
- tests/test_sidestack_vs_launcher.py (step 6, new, spec-exact content, 8 tests)
- sidestack/lanes/VS-27-ods-start-on-click.md (builder report)
- sidestack/lanes/README.md (tracker row: ready → running (dsh done))
COMMANDS RUN:
- & $py -m pytest tests/test_sidestack_vs_launcher.py -q -p no:cacheprovider → 8 passed
- & $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider → 14 passed
- & $py sidestack/scripts/check_sidestack.py → OK: 15 required files, 26 lane specs, links, manifest, env profile, secret scan
- git status --short → the Preflight files plus exactly the "Files" list above
NOT DONE:
- Part B (Operator, after approval): install new manifest + restart ods-dashboard-api, logon task SIDESTACK-VOICESTUDIO-LAUNCHER, live checks with Voice Studio stopped/running.

## Reviewer verification (Part A, 2026-11-08)

- **Builder:** dsh (Qwen 3.8 on ODS), 11 minutes. Preflight passed. Both new files, the manifest edit and the three `check_sidestack.py` edits match the spec byte for byte.
- **Not as written:** two Markdown steps.
  - **Step 3:** it dropped the new "Launcher page" row of `ARCHITECTURE.md` and reworded the ODS row.
  - **Step 4:** it wrote its own `APPLY.md` section. That section contains a private path, task names that do not exist, and a `.py` file run through `powershell -File`.
  - The reviewer replaced both with the spec text.
- **Acceptance (Hard law 9 environment):**
  - `test_sidestack_vs_launcher.py`: 8 passed;
  - `test_sidestack_launcher.py`: 14 passed;
  - `check_sidestack.py`: OK (15 required files, 26 lane specs).
- **Mutation checks (all 7 caught, files restored):**
  - Host check dropped in `do_POST` → L2;
  - Origin check dropped → L5;
  - rate limit always passes → L5;
  - `/health` needs the Host → L1;
  - `/api/status` without the token → L6;
  - manifest port back to 3900 → validator;
  - launcher `APP` port changed → validator.
- Lint was not run: `ruff` is not in the venv.

## Part B results (Operator, 2026-11-08)

The user approved the ODS change when choosing "Start-on-click launcher".

1. **Reachability:** the page was started by hand with `pythonw -I`. From inside `ods-dashboard-api`:
   - `http://host.docker.internal:3901/health` → 200;
   - `/` → 403, because the Host is not allowed.
2. **Manifest update (ODS):**
   - The repo manifest was staged with LF line endings: 1,227 bytes, sha256 `f20b6779253bb42e…`.
   - The installed VS-08 manifest (sha256 `ba2d54a4fa856856…`, port 3900) was backed up to the ODS backups folder.
   - The new manifest was installed as `ods:ods`, 0644, and its sha256 matches.
   - `docker restart ods-dashboard-api` at 2026-11-09T03:01:22Z: healthy after 6 s, same container, 0 restarts, no warnings.
   - ODS → Applications now shows **SideStack Voice Studio** linking `http://localhost:3901`.
   - The dashboard API's `/api/external-links` now needs a bearer token, so the entry was checked in the ODS UI instead.
3. **Logon task:**
   - A per-user task, "SideStack Voice Studio launcher page", runs `pythonw.exe -I <worktree>\sidestack\scriptsoice_studio_launcher.py` at logon.
   - Run level Limited, no time limit, a new instance is ignored if one is already running.
   - It was started once by hand. The page runs as `pythonw`, and `/health` → 200.
4. **Voice Studio running:** the ODS link forwarded straight to `http://localhost:3900/`.
5. **Voice Studio stopped** (`-Stop`; port 3900 free):
   - the ODS link opened the "Starting Voice Studio…" page;
   - the backend logged "Application startup complete" about 20 s later;
   - the page then forwarded to `http://localhost:3900/`.
   - The started instance is in the default profile: `engine=omnivoice` → 403 `commercial_only_mode`.

**Verdict:** PASS.

**Notes:**
- The task runs the page from the builder worktree, because only that checkout has a built `frontend/dist`. The page starts the `Start-VoiceStudio-ODS.ps1` next to it, so Voice Studio runs from the same checkout.
- **Rollback:**
  - restore the backed-up manifest and run `docker restart ods-dashboard-api`;
  - run `Unregister-ScheduledTask -TaskName "SideStack Voice Studio launcher page"`;
  - stop the `pythonw` process listening on 3901.
