# smlibpy kernel

Use smlibpy for new native construction, booleans, topology edits, rigid placement
and STEP export. Rendering a mesh does not establish native reconstruction.
Other readers may inspect the final STEP independently; they do not replace
native construction.

## Install a separate runtime

From the repository root:

```sh
uv venv --python 3.12 .venv-smlib
uv pip install --python .venv-smlib/bin/python -r requirements-native.txt
export OPEN_ASSEMBLY_SMLIB_PYTHON="$PWD/.venv-smlib/bin/python"
```

The main service uses a different Python environment. The operator chooses this
interpreter; HTTP input cannot override it. Check the actual Python/package
versions and native binary identity. Wheel availability is platform-specific.
See the [upstream installation guide](https://smlibpy.classcad.ch/docs/getting-started)
and [pinned PyPI release](https://pypi.org/project/smlibpy/0.3.4/).

The 0.3.4 distribution declares MIT AND Apache-2.0 AND OFL-1.1. Retain its
installed license and notice files if redistributing the dependency. This
repository distributes project source, not the native wheel or binary.

## Public native API

```python
from smlibpy import Box, Cylinder, export_step, read_step

part = (Box(80, 50, 8) - Cylinder(3, 10)).named("kernel-probe")
assert part.is_valid()
export_step(part, "probe.step", unit="mm", name="kernel-probe")
bodies = list(read_step("probe.step").bodies)
assert len(bodies) == 1 and bodies[0].is_valid()
```

This synthetic plate is a dependency probe, not a substitute for a user's case.
Do not silently fall back to OCP, build123d or another construction kernel.

## Native delivery

Keep parameterized source, units, input hashes, physical definitions and explicit
occurrence transforms. Check each native body and saved construction state for
validity and positive volume. Export through smlibpy, read the STEP back and
compare bounds, volumes and placement. Independently inspect its structure or
import it in a separate reader.

Record the actual runtime, source and STEP hashes, counts, measured deviations
and unavailable provenance. Source fidelity needs its own per-feature checks.
Same-kernel readback proves exchange consistency, not agreement with a drawing.

The registered wiring-cover source is bundled in `runtime/open_assembly/native_resources/`.
The [relay/socket case](../../../cases/omron-g2r/README.md) is separate offline
native authoring. It does not pass [faithful reconstruction](../../../cases/omron-g2r/MANUAL-AUDIT.md).
Its STEP exporter preserves named flat bodies; the JSON document retains the
hierarchy and repeated definitions. A nested native STEP product tree is pending.

[Specify](specify-one.md) is an optional factory-intent adapter, not a substitute
for native geometry or source-fidelity checks.
