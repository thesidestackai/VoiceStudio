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

1. **Read-only check** (WSL, as the ODS user): confirm that no `sidestack-voice-studio` folder exists yet
   under the ODS `extensions/services/` directory, and that the Meetings entry (`sidestack-meetings`)
   is present as the reference pattern.
2. **Backup point:** none is needed for a new folder. Rollback is removing it (see below).
3. **Install (approved):** create `extensions/services/sidestack-voice-studio/`, copy
   `manifest.yaml` into it byte for byte (mode 0644, owned by the ODS user), and compare the SHA-256 with the recorded hash.
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
