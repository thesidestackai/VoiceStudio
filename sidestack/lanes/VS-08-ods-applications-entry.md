# VS-08 — ODS Applications entry

- **Phase:** 3
- **Run by:** Operator (it changes the ODS install, outside this repo)
- **Gate:** **ODS change approval** for steps 2–5: read-only ODS inspection, creating one new folder with one file, and restarting the `ods-dashboard-api` container.
- **Depends on:** VS-07
- **Status:** verified (installed 2026-11-06)

## Goal

ODS → Dashboard view → Applications lists **SideStack Voice Studio** (`http://localhost:3900/`).
It is healthy while Voice Studio runs (started with `Start-VoiceStudio-ODS.ps1`) and unhealthy while
it is stopped. ODS never starts or stops it (`type: windows-host`). The procedure is
[../ods/APPLY.md](../ods/APPLY.md).

Checked in code before writing this lane:
- The ODS health check reaches Voice Studio as `Host: host.docker.internal:3900`. Upstream's DNS-rebinding guard (`core/browser_guard.py`) allows `host.docker.internal` by default.
- `/health` is a public shell path.
- The API-key middleware is inactive, because no `OMNIVOICE_API_KEY` is set.
- The same pattern already works for the DeepSeek Harness entry (127.0.0.1:3080, reported healthy).

## Files

| Path | Change |
|---|---|
| `sidestack/ods/manifest.yaml` | edit (done with this spec): the header no longer says DRAFT |
| `sidestack/ods/APPLY.md` | edit (done with this spec): exact WSL commands |
| *(outside the repo)* `%USERPROFILE%\Documents\Codex\2026-10-16\ods-voice-studio-app-entry\manifest.yaml` | staged byte copy, with its SHA-256 |
| *(ODS)* `/home/ods/ods/extensions/services/sidestack-voice-studio/manifest.yaml` | create (0644, `ods`) |

## Preflight

```powershell
python sidestack/scripts/check_sidestack.py                      # expect: OK
powershell -NoProfile -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1 -DryRun   # expect: exit 0, url http://127.0.0.1:3900/
(Get-FileHash sidestack\ods\manifest.yaml).Hash                  # record it
```

## Steps

1. **No approval needed:** stage the byte copy on C: and record its SHA-256. `check_sidestack.py` must pass.
2. **Approved, read-only:** list `extensions/services/`, confirm `sidestack-voice-studio` is absent, and record the dashboard API's container id, restart count and health.
3. **Approved:** install the folder and the file, then compare `sha256sum` with step 1.
4. **Approved:** run `docker restart ods-dashboard-api`, wait for healthy, and confirm the same container id and 0 restarts.
5. **Verify:**
   - The dashboard API's external-links list includes `sidestack-voice-studio` on port 3900.
   - With Voice Studio stopped, ODS reports it unhealthy. Start it with the launcher, and ODS reports it healthy.
   - The link resolves to `http://localhost:3900/`. Stop Voice Studio again afterwards, unless the user wants it running.

## Acceptance

- The installed `manifest.yaml` SHA-256 equals the repo file's.
- `ods-dashboard-api` is healthy, with the same container id and 0 restarts.
- The external-links list includes `sidestack-voice-studio` (port 3900).
- The entry is healthy while Voice Studio runs and unhealthy while it is stopped, and ODS did not start it.
- `python sidestack/scripts/check_sidestack.py` is OK.

## Rollback

Move `/home/ods/ods/extensions/services/sidestack-voice-studio/` to `/home/ods/ods-deploy-backups/`,
then run `docker restart ods-dashboard-api`.

## Out of scope

- Autostart, desktop shortcut, Portal view (Applications shows in the Dashboard view only).
- Any other ODS change, and restarting any other ODS container.

## Reviewer notes

**PASS, 2026-11-06 (the ODS change was approved by the user).** The operator ran each step from a script staged on C:, through `wsl.exe -d Ubuntu-24.04 -u ods --exec bash /mnt/c/.../sN.sh`.

- **Step 1 (staged copy):** sha256 `ba2d54a4fa856856…`, which matches the repo file. `check_sidestack.py` passed.
- **Step 2 (read-only):**
  - `sidestack-voice-studio` was absent.
  - Both reference entries (`deepseek-harness` :3080 and `sidestack-meetings` :8901) are `windows-host` via `host.docker.internal`.
  - `ods-dashboard-api` before: container `d37e0fc47760…`, 0 restarts, healthy, port `127.0.0.1:3002`.
- **Step 3:** the folder and manifest were installed as `ods:ods`, 0644, 1000 bytes. The sha256 matches.
- **Step 4:** `docker restart ods-dashboard-api` at **2026-11-06T19:18:31Z**. It was healthy after 6 s, as the same container, with 0 restarts and no warnings or errors in its logs.
- **Step 5 (verify):**
  - `/api/external-links` needs dashboard credentials (401), and the operator did not read them. Verification used the ODS web UI (`http://localhost:3001`) and an in-container probe instead.
  - The sidebar → Applications shows **SideStack Voice Studio** linking to `http://localhost:3900`, between SideStack Meetings and Kokoro.
  - With Voice Studio started by the launcher (11 s): from inside `ods-dashboard-api`, `http://host.docker.internal:3900/health` returned **200**. Upstream's DNS-rebinding guard allows that host name, as expected. The Dashboard → Services list showed **SideStack Voice Studio: Healthy** (page 19 of 21).
  - After `-Stop` and 45 s: the Services list showed **SideStack Voice Studio: Down**. Port 3900 was still free, so ODS did not start it. Core services stayed at 8/8, and DeepSeek Harness and SideStack Meetings stayed Healthy.
  - While nothing listened on 3900, the in-container probe failed with `Errno 101 Network is unreachable` instead of "connection refused". That is how Docker Desktop's host gateway reports a closed host port, not a routing problem.
- **State left:** the entry is installed, and Voice Studio is stopped. The user starts it with `Start-VoiceStudio-ODS.ps1`.
- **Context:** the ODS LLM was loaded during the healthy check (24.7 GB VRAM, 128k), with Voice Studio running beside it with no model loaded.
- **Rollback:** see above. An ODS upgrade may remove this core-manifest folder; re-apply from `../ods/APPLY.md`.
