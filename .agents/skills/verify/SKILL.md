---
name: verify
description: Verify Open Assembly CAD through its real browser, CLI and MCP paths, including saved project context and change handoff, smlibpy kernel provenance, reconstruction evidence, native STEP delivery and truthful failure states. Use before accepting changes to the Open Assembly skill or its runtime.
---

# Verify Open Assembly CAD

## Goal

Help mechanical and industrial design users turn text, images, or STL plus cited manual context into a project that retains design intent and can be revised, checked, and handed off. The complete CAD goal requires genuine physical parts, editable per-part native construction, and an assembled STEP through a lightweight chat skill and side-window viewer. A general-purpose LLM interprets evidence, proposes genuine physical parts and authors measured construction. **smlibpy is the core kernel for construction, booleans, topology edits, placements and STEP export.** The viewer exposes decomposition, part inspection and construction/assembly playback. Specify adds confirmed factory intent when requested. No newly trained checkpoint is required; a cost advantage requires an actual comparison.

Read the [authoring skill](../../../skills/open-skyfall/SKILL.md), its [kernel reference](../../../skills/open-skyfall/references/smlibpy.md), and the [feature map](features/README.md). Verify the skill's behavior and produced artifacts, not just its wording. Keep driver execution, feature coverage and achievement of this goal as separate verdicts.

## Launch

The conversation owns project creation, inputs, context, proposals, execution, and validation discussion through tools. The side window is a STEP viewer. Verify conversation-side HTTP/MCP operations and browser display separately. A local browser run does not prove ChatGPT-host rendering or message delivery.

The main service's registered wiring-cover executor uses smlibpy. Its legacy reconstruction uses build123d/OCP and cannot pass the smlibpy reconstruction gate. Use [the native edit journey](features/native-edit.md) for the registered example. Do not repair the remaining product gaps by weakening this verifier.

Use a private checkout snapshot and an empty job directory. From the project root, in a shell whose variables you retain for the run:

```bash
export VERIFY_REPO="$PWD"
mkdir -p "$VERIFY_REPO/evidence/verify"
export VERIFY_EVIDENCE="$(mktemp -d "$VERIFY_REPO/evidence/verify/run-XXXXXX")"
export VERIFY_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/open-assembly-verify-XXXXXX")"
export VERIFY_PORT=8778
git rev-parse HEAD > "$VERIFY_EVIDENCE/source-commit.txt"
git status --short > "$VERIFY_EVIDENCE/source-status.txt"
git archive HEAD > "$VERIFY_EVIDENCE/source.tar"
tar -xf "$VERIFY_EVIDENCE/source.tar" -C "$VERIFY_SCRATCH"
```

This tests committed application code; record any uncommitted change as untested. To test an uncommitted candidate, make a separate disposable checkout containing that diff, inspect its status, and use it as `VERIFY_REPO`. Do not overlay unknown edits or mutate the user's running checkout. Record the current verification-skill digest separately from the application commit.

Require the repository's `.venv/bin/python` and `web/node_modules`; if absent, follow its README (`uv sync`, `npm ci`) in a dedicated checkout. The shared environment supplies dependencies read-only. Build into the private snapshot:

```bash
ln -s "$VERIFY_REPO/web/node_modules" "$VERIFY_SCRATCH/web/node_modules"
npm --prefix "$VERIFY_SCRATCH/web" run build > "$VERIFY_EVIDENCE/build.log" 2>&1
```

Check the chosen loopback port is free. If occupied, choose a different port and record it; never stop its owner. Launch in a foreground tool/PTY session you own and retain that session handle:

```bash
PYTHONPATH="$VERIFY_SCRATCH/runtime" "$VERIFY_REPO/.venv/bin/python" -c \
  'from open_assembly.cli import main; main()' \
  --workspace "$VERIFY_SCRATCH/jobs" serve --port "$VERIFY_PORT"
```

For the registered native journey, set `OPEN_ASSEMBLY_SMLIB_PYTHON` to the reviewed absolute smlibpy interpreter path in this owned server's environment before launch. Do not change the user's running service or global configuration. Record the selected interpreter in `launch.json`. Leave it unset in a separate capability-refusal run to check the visible unavailable state.

Capture stdout/stderr and the process PID/session in `launch.json` and `server.log`. Also record absolute repo, scratch, evidence, workspace and URL paths there. The CLI module has no `__main__` invocation; `python -m open_assembly.cli` does not start this server.

Ready means `/health` returns the expected service, `/api/jobs` is `[]`, `/` serves the built viewer, and the browser shows an empty STEP view with download disabled. This filesystem job store needs no database migration or seed. Create test projects through documented agent tools. A copied accepted case can cover display-only checks when its source and artifact hashes are retained; it cannot establish new construction or reconstruction.

## Doctor

Before driving, and whenever behavior looks wrong, perform this read-only check against the owned instance:

```bash
curl --fail --silent "http://127.0.0.1:$VERIFY_PORT/health"
curl --fail --silent "http://127.0.0.1:$VERIFY_PORT/api/jobs"
PYTHONPATH="$VERIFY_SCRATCH/runtime" "$VERIFY_REPO/.venv/bin/python" -c \
  'import open_assembly.server; print(open_assembly.server.__file__)'
```

Require `service=open-assembly-cad`, the expected job set and a module path inside this scratch snapshot. Check the retained process/session is live and its command names this exact job directory. Health does not attest source revision, kernel or ownership by itself. Record the source commit, build exit code, UI asset paths and browser URL in `doctor.json`.

For a smlibpy build, separately check the selected interpreter with `importlib.metadata.version("smlibpy")` and `smlibpy.__file__`. The native worker's CPython 3.12 environment differs from the main service's Python environment. A successful import is dependency evidence only. Inspect `GET /api/native-cases`, the pinned case source, actual execution transcript, and generated runtime provenance before accepting native execution. Capability metadata alone does not prove a build.

## Drive

Use an isolated browser, not the user's existing tab. With the installed `chrome-devtools-axi`, choose a unique `CHROME_DEVTOOLS_AXI_SESSION` and set `CHROME_DEVTOOLS_AXI_USER_DATA_DIR="$VERIFY_SCRATCH/chrome"`. Clear inherited AUTO_CONNECT, BROWSER_URL and shared MCP_SERVER_URL connection overrides for this run. Keep that environment on every command. Resolve the binary once with `command -v chrome-devtools-axi`.

```bash
chrome-devtools-axi open "http://127.0.0.1:$VERIFY_PORT/"
chrome-devtools-axi snapshot
chrome-devtools-axi screenshot "$VERIFY_EVIDENCE/before.png"
```

Follow one mapped journey using real controls, fresh accessibility refs or stable selectors. `run` exposes `page.click`, `page.fill`, `page.press`, `page.snapshot` and read-only `page.eval` observations. Supply inputs and manage context through the actual host or documented HTTP/MCP tools, then open the returned `?job=` URL or `show_assembly` result. Browser authoring forms have been removed.

Do not set internal state, dispatch synthetic input events, call renderers, fabricate accepted jobs, or use test-only endpoints to stand in for the user action. Read-only HTTP requests may verify the resulting job and artifact availability. API writes are the intended agent entry point for context and execution; record those separately from pane interactions.

For CLI/model journeys, run the reviewed editable case command that the authoring skill produced, capture its exit status and use a fresh output directory. Do not substitute the kernel reference's synthetic plate or the registered cover for the user's reconstruction. For host/MCP journeys, retain the actual tool/host transcript and identify the tested host.

## Evidence

Write proof under `evidence/verify/run-*`, outside scratch. Include the feature ID and entry point, source/skill/input hashes, exact command or browser action, before/action/after observations, screenshots, stdout/stderr, exit codes, persisted job state and resulting artifact hashes. Save read-only side-effect checks alongside what is visible. A screenshot or copied report alone is insufficient.

Full goal acceptance requires all applicable mapped journeys, actual LLM planning evidence, measured source-to-CAD comparisons with declared units and case-specific limits, editable smlibpy source, observed smlibpy execution/export, native STEP readback and separate independent inspection. Match the browser download to that exact STEP. Preserve physical-part identity and repeated-instance placements. Record omitted features and manufacturing assumptions. A preview, round-trip volume alone, a kernel-name field, static source import or the dependency probe cannot satisfy this gate.

A registered native edit can pass its own baseline, capture/execution, checkpoint, and current-delivery checks. It does not pass fresh image/STL reconstruction, general physical decomposition, or nested assembly export. Keep source accuracy, units, approximate regions, protected metric checks, and manufacturing acceptance as separate findings. A restored ready job after a failed edit still contains a failed execution and the prior accepted geometry.

Use `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN` and `NOT_APPLICABLE` per journey, with the reason and artifact paths. Missing preconditions are `BLOCKED`, never a pass. A successful refusal or saved-context journey can pass its own feature while full reconstruction remains blocked. Saved context, a captured pending request, copied text, a queued context, and host message acceptance each need separate evidence. None establishes executed geometry. For Skill changes, independently forward-test a realistic saved project and captured request without supplying the intended answer. Keep the evaluator's artifacts and scope its authority to the permitted planning or execution. Host-account integration, industrial fidelity, factory approval and relative model cost need their own evidence. Do not spend on providers, deploy or write real factory intent merely to fill coverage.

## Cleanup

Stop only the foreground server/tool session this run started and confirm exit. If using a retained PID, first confirm its live command still names the exact scratch job directory. Never kill by process name or listening port. Stop the named browser bridge using the same isolated browser environment:

```bash
chrome-devtools-axi stop
```

After every failed iteration, perform the same cleanup before retrying. Remove only this run's scratch tree after confirming its ownership and that it is outside the evidence directory. Keep the evidence, source archive, logs and reports. Recheck that the owned port is no longer listening and that `before.png`, `after.png` and the feature report still exist. Record cleanup in `cleanup.json`. Existing services on 8766, 8770 and the CAD Viewer remain outside this run.

## Helpers

No new executable helper or application endpoint is introduced. Use the repo's actual build/CLI, the installed browser driver and the feature recipes. The committed [undimensioned PNG](assets/undimensioned-cover.png) is a synthetic refusal input, with no scale or hidden-geometry evidence; it is not the user's wiring-cover STL.

Use `/maintain-verification-skill` when application paths, selectors, kernel execution or acceptance evidence change.
