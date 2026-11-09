# Adding SideStack Voice Studio to ODS → Applications (lane VS-08)

**Needs the user's approval before step 3.** This changes the ODS install, outside this repo.

The ODS Applications list is built only from built-in `extensions/services/*/manifest.yaml`
(user extensions never appear there), so this is a core-manifest addition. An ODS upgrade may
remove it. Re-apply from this file if that happens.

## Preconditions

- VS-07 is done: the launcher starts Voice Studio on `127.0.0.1:3900`, and `/health` returns 200.
- `python sidestack/scripts/check_sidestack.py` passes; it validates `ods/manifest.yaml`.
- Record the manifest's SHA-256:
  `(Get-FileHash sidestack\ods\manifest.yaml -Algorithm SHA256).Hash`

## Steps

Commands run in the ODS distro as the ODS user: `wsl.exe -d Ubuntu-24.04 -u ods --exec bash -c '...'`.
ODS lives at `/home/ods/ods`. WSL mounts only `C:` (at `/mnt/c`), so the manifest is staged on C: first:
`C:\Users\<you>\Documents\Codex\2026-10-16\ods-voice-studio-app-entry\manifest.yaml`.

1. **Read-only check:**
   - `ls /home/ods/ods/extensions/services` shows no `sidestack-voice-studio`, and does show `deepseek-harness` and `sidestack-meetings` (the reference pattern).
   - `docker inspect -f '{{.Id}} {{.RestartCount}} {{.State.Health.Status}}' ods-dashboard-api` gives the "before" state.
2. **Backup point:** none is needed for a new folder. Rollback is removing it (see below).
3. **Install (approved):**
   - `install -d -m 0755 /home/ods/ods/extensions/services/sidestack-voice-studio`
   - `install -m 0644 /mnt/c/.../ods-voice-studio-app-entry/manifest.yaml /home/ods/ods/extensions/services/sidestack-voice-studio/manifest.yaml`
   - `sha256sum` must equal the recorded hash.
4. **Load:** `docker restart ods-dashboard-api`. Wait until it reports healthy, then check it
   has the same container id and 0 restarts.
5. **Verify:**
   - With Voice Studio running: ODS → Dashboard view → Applications shows **SideStack Voice Studio**
     as healthy, and the link opens `http://localhost:3900/`.
   - With Voice Studio stopped: the entry shows unhealthy. ODS must not try to start it.
6. Record date, hash and container restart time in `sidestack/lanes/README.md` (VS-08 row, Reviewer notes).

## Rollback

Move `extensions/services/sidestack-voice-studio/` out to the ODS backups folder, then run
`docker restart ods-dashboard-api`.

## Notes

- Applications appears in the ODS **Dashboard** view only, not the Portal view.
- ODS builds the link from the hostname the ODS page was opened on. Open ODS on `localhost` so
  the link matches the loopback bind.

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
