# Manual fidelity audit — 2026-11-02

Verdict: **does not pass faithful reconstruction**. The current result is an
illustrative model that uses some datasheet dimensions. Valid native geometry,
STEP exchange and viewer behavior passed their own checks; those results do not
establish agreement with the product drawing.

Source: The supplied G2R datasheet, pages 6 and 8, SHA-256
`b3d0aed75980fa561695d4ea7432dfd6fb71455f380ef01b8d1cbe5c3ca82919`.
Reviewed delivered STEP SHA-256:
`75be2e87ccfc027f2655bc70137df1ae4d49e68fcf7e345b32c3f733d7495aa8`.
The editable model hash still matches the recorded native execution. No geometry
was changed during this audit. Evidence is in `evidence/verify/g2r-manual-audit/`.

| Feature | Drawing/source | Current model | Assessment |
| --- | --- | --- | --- |
| Relay external envelope | Page 6: 29, 13, 35.5 mm maxima | Built envelope is 29 x 13 x 35.5 mm | Matches the chosen maximum dimensions; maximum limits are not exact production measurements. |
| Broad terminal blades | Page 6: 4.75 mm blade width, with differing blade orientations visible in the bottom view | `coil_pin` is a 1.2 x 0.5 mm strip, all blades use the same narrow-axis convention | Mismatch. The 4.75 mm annotation was not mapped to the correct blade geometry; putting 4.75 mm on another blade does not satisfy it. |
| Socket mounting ear | Page 8: lower mounting extension, annotated 4 mm | Stepped block body, no corresponding mounting ear contour | Omitted. Overall body-size checks cannot verify this feature. |
| Socket contour and relay seating | Page 8: stepped side view and installation dimensions | Arbitrary terrace coordinates; relay seating plane 25.5 mm inferred from a nominal 61 mm envelope | Approximation. Dimension interpretation and placement need an explicit drawing-to-model mapping. |
| Internal mechanism | Photos and electrical schematic, no complete internal mechanical dimensions | Authored bobbin, winding envelope, core, yoke, armature and contact springs | Illustrative assumptions. Their shape, topology and operation are unverified. |
| Physical part tree | Datasheet lists relay, socket and accessories, not a complete internal BOM | 18 definitions, 27 placed bodies | A proposed decomposition, not a manufacturer-confirmed physical BOM. |
| Playback | No manufacturer assembly sequence was supplied | 32 native construction/placement checkpoints | Demonstrates how this model was authored; it is not a validated production or disassembly process. |

## Required acceptance change

Before claiming faithful reconstruction, map each relevant source feature to its
page/view, datum, model feature and independent geometric measurement. Separate
matched, mismatched, omitted and unknown features. A source dimension must not be
validated only by a hole or witness whose location was authored from the same
unverified model assumptions. Preserve maximum limits and tolerances as limits.

Correct the broad terminal blades and mounting ear, then verify their interfaces
against the drawing. Keep unobservable internals explicitly schematic or omit
them from a fidelity claim. Retain proposed decomposition and authored playback
as separate evidence from physical-BOM and assembly-process verification.

The normal-shading correction changes display only and does not resolve any of
these source-fidelity findings.
