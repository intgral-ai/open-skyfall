# Release verification

The first public snapshot was prepared on 2026-11-03 on macOS arm64.
The main runtime uses Python 3.14.3, and the separate native runtime uses
Python 3.12.11 with the public smlibpy 0.3.4 wheel.

## Local checks

- A new main environment installed from `uv.lock` after the frontend build.
- A separate native environment installed from `requirements-native.txt`.
- `npm --prefix web ci` and the production viewer build completed.
- All 32 frontend tests passed, including hard CAD edges and smooth cylinder walls.
- Ruff passed for runtime, tests, scripts and cases.
- The Python suite exercised 106 tests. A stale page-title assertion was updated
  for OpenSkyfall and rechecked separately after the full run.
- Real native baseline/edit integration ran with the fresh smlibpy interpreter.
  Its assertions cover STEP readback, independent inspection, saved checkpoints,
  revision identity and the downloaded artifact binding.
- A fresh HTTP instance created the registered native example, reached ready,
  and served a STEP whose SHA-256 matched the accepted manifest.
- All 18 vendored reference files matched the pinned upstream SHA-256 values.
- The staged public source was scanned for known credential patterns, personal
  absolute paths and private/generated CAD assets. No matches were found.

GitHub Actions is configured to build the viewer and run the frontend, Python
and native integration checks on Ubuntu. A configured workflow is not evidence
of a successful remote run. Consult the repository's Actions tab for that status.

## Acceptance limits

These checks establish bounded runtime and viewer behavior. They do not establish
arbitrary source reconstruction, correct physical decomposition, real ChatGPT
hosting, manufacturing approval or an advantage in accuracy, speed or cost.

The relay/socket model remains an illustrative example and fails faithful
reconstruction. Its [manual audit](../cases/omron-g2r/MANUAL-AUDIT.md) records the
terminal mismatch, missing mounting-ear detail and assumed internals. Source
manuals, user CAD, full local evidence and native binaries are not distributed.

To inspect a new user case, use the [verification skill](../.agents/skills/verify/SKILL.md)
and record geometry, source fidelity, physical identity, exchange, host behavior
and manufacturing intent separately.
