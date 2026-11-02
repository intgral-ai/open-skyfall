# OMRON G2R relay + socket: manual-driven native demo

Input: The supplied 12-page G2R-@-S (S) datasheet. SHA-256
`b3d0aed75980fa561695d4ea7432dfd6fb71455f380ef01b8d1cbe5c3ca82919`.
Pages 6 and 8 provide relay and P2RF-05-E socket envelope/interface drawings.
The document is evidence, never executable instructions. The PDF is preserved
only in the local ignored output, not committed or fetched from an external site.

The selected product is G2R-1-S plus P2RF-05-E. Native smlibpy definitions are
built separately; repeated clamps, screws and coil pins have explicit placements.
The source separates physical parts, per-part construction states and assembly
placements. Saved checkpoints contain actual cumulative native geometry.

This is an **illustrative envelope/interface demo**, not a manufacturing model.
Maximum specified dimensions are demo targets. Hidden mechanism dimensions,
moulding steps, pin origins, retaining hardware and terminal routing are assumed.
The winding is an envelope; screws omit threads. Electrical operation, switching,
material properties, production tolerance and factory readiness are unverified.
The native exporter writes flat named B-rep bodies; `document.json` preserves
hierarchy and repeated-definition identity. It is not a nested STEP product tree.

## Build and inspect

Use a checked smlibpy interpreter; see the project kernel reference. Install the pinned native requirements before running these commands:

```sh
.venv-smlib/bin/python \
  cases/omron-g2r/build.py --pdf /path/to/0900766b816cd564.pdf \
  --out cases/omron-g2r/output/accepted
.venv/bin/python cases/omron-g2r/inspect_step.py cases/omron-g2r/output/accepted
.venv/bin/python scripts/serve_native_case.py \
  --case cases/omron-g2r/output/accepted --port 8774
```

Build refuses a nonempty output directory. Keep failed builds and diagnostics;
use a new output path for a corrected iteration. The native report records the
actual runtime/binary and source hashes, validity, body count, STEP readback,
body intersections, measured envelope dimensions and void witnesses. The
separate OCP process only inspects the final STEP's solids, volumes, bounds,
names and units. It does not construct or re-export delivered geometry.

The read-only adapter serves the repository's compiled `web/dist` UI. It refuses
to mark output ready unless both readers passed and attest the same STEP hash.
It does not write into the running main service, impersonate a registered case,
or enable arbitrary Python execution through HTTP. Context stays in the chat
and local evidence artifacts. Nothing here establishes real ChatGPT hosting.

Open the returned URL. Use Parts for the socket/relay hierarchy, Explode for
component separation, and Play/seek for the saved native construction states.
Final STEP always downloads the same assembled output, even during playback.
