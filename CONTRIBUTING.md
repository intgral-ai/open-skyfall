# Contributing

Read the current limitations in [README.md](README.md) before choosing a task.
Keep new native geometry construction, booleans, placement and STEP export on
smlibpy. Other readers may inspect the output independently. Do not silently
replace native construction with a legacy kernel to make a test pass.

## Development checks

```sh
npm --prefix web ci
npm --prefix web run build
uv sync --frozen
uv run --frozen ruff check runtime tests scripts cases
node --test web/tests/*.test.mjs
uv run --frozen pytest -q
```

Set `OPEN_ASSEMBLY_SMLIB_PYTHON` to a checked native interpreter to include the
real wiring-cover integration. Without it, those tests skip, which is not
evidence that native execution passed. The [verification skill](.agents/skills/verify/SKILL.md)
covers isolated browser and agent journeys.

## CAD examples

Use inputs you have permission to share. Retain units, hashes, source dimensions,
editable source, placements and checks. Mark each feature as observed, inferred,
omitted or conflicting. Keep the physical-part tree separate from construction
steps and revision history. A speculative internal mechanism is not a confirmed
BOM, and an authored animation is not a recovered manufacturing process.

Provide a small reproduction, expected result, actual result and the check that
shows the difference. Do not submit credentials, private manuals, customer files,
licensed binaries or external CAD assets without redistribution permission.

## Pull requests

Describe the problem and resulting behavior. Include the checks you ran and
their scope. Preserve upstream notices. Keep changes focused, and list source
fidelity, exchange compatibility and manufacturing limitations separately.
