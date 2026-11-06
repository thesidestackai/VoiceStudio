# VS-xx — <short title>

- **Phase:** <0–4>
- **Run by:** dsh | Operator | dsh + Operator
- **Gate:** none | <what the user must approve first>
- **Depends on:** <lane ids>
- **Status:** planned | ready | running | verified | committed

## Goal

<One or two sentences: what is true when this lane is done.>

## Files

| Path | Change |
|---|---|
| `<path>` | create / edit (<anchor>) / copy from `sidestack/work/VS-xx/<file>` (sha256 `<hash>`) |

Only these files may change. Anything else showing in `git status` fails the lane.

## Preflight

```powershell
git -C <worktree> status --short          # expect: empty
git -C <worktree> rev-parse --short HEAD  # expect: <sha>
<other checks with expected output>
```

## Steps

1. <exact, small step>
2. <...>

## Acceptance

```powershell
<command>   # expect: <exit code / test count / output>
python sidestack/scripts/check_sidestack.py   # expect: OK
```

## Out of scope

- <things the builder must not do in this lane>

## Reviewer notes

<filled in after verification: PASS/FAIL, hashes, counts, commit sha>
