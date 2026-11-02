# Native smlibpy reconstruction

The user receives an editable native reconstruction derived from the supplied evidence, built and exported with smlibpy.

## Sub-features

- `llm-plan` links the agent's interpretation, dimensions, physical parts and construction plan to the actual input.
- `native-build` constructs and modifies native smlibpy solids with explicit units.
- `source-agreement` checks case-specific features and deviations against the source.
- `no-kernel-fallback` reports unavailable capabilities without substituting another construction kernel.

## How to get to it (user POV)

- Invoke `skills/open-skyfall/SKILL.md` in the chat with an STL or image.
- Run the resulting reviewed editable case build command in its documented smlibpy environment.

## Driving it with the chat host and case CLI

Preconditions: a preserved input, declared scale/assumptions, an actual smlibpy interpreter, and the case's accepted feature/deviation limits recorded before measuring the candidate. The authoring agent must own the case; do not edit a concurrent writer's checkout.

- **Invoke the skill.** Give a cold authoring agent the real input and goal. Retain its actual tool/actions and plan. Do not give it a completed reconstruction as a substitute input or count a preauthored fixture as proof of LLM reasoning.
- **Check the executor.** Record `importlib.metadata.version('smlibpy')`, `smlibpy.__file__`, Python/ABI and available native binary identity in the interpreter the case actually uses. Inspect editable construction and exporter source.
- **Build.** Execute the reviewed command documented by that case in a new output directory. Capture command, stdout/stderr and exit code. Require observed smlibpy construction/Boolean/topology/placement/export operations and saved native STEP. Static import text or a JSON field naming the kernel is insufficient.
- **Compare source.** Measure the input and saved candidate, including requested holes, cutouts, walls, orientation and placement. Record metrics, sampling method and omitted features. Use the predeclared case limits; do not choose thresholds after seeing the result.
- **Check refusal.** On an unavailable operation or invalid result, preserve the failure and diagnostic. No valid export claim may accompany a mesh wrapper, faceted triangle STEP or OCCT-built replacement.

## Gotchas

- There is no smlibpy-backed general reconstruction endpoint in the current main service. Calling its legacy `/api/jobs/{id}/design` is `BLOCKED` for this journey. The registered native wiring-cover edit executes existing trusted CAD and cannot satisfy fresh source reconstruction.
- The kernel reference's one-hole probe validates dependency construction/exchange only. It is not this journey's LLM/input reconstruction proof.
- The local reference is smlibpy 0.3.4 on CPython 3.12 arm64; the old workspace's Python environment is different. Check the actual executor, not another installed environment.
- Fused or organic geometry and missing hidden details may require explicit assumptions or refusal. Do not invent dimensions or claim held-out industrial accuracy from a synthetic case.
