# STEP side window

Mode: Operate. Scope: the existing model viewer. Preserve its Intgral Silence neutrals, Geist typography, native CAD canvas, and familiar view controls.

## Ownership

The user's 2026-11-02 direction puts project context in ChatGPT and leaves the side window for STEP. The conversation owns source inputs, requirements, manual excerpts, proposals, request capture, parameter edits, validation discussion, and factory confirmation. Its tools retain durable records in the existing project store.

The pane owns the generated model, physical-part selection, camera framing, isolation, explosion, optional saved construction playback, current output revision, and STEP download. It has no second conversation, project form, numeric proposal form, factory interview, JSON report, or source-bundle dashboard.

The accepted final STEP remains the download target while a construction checkpoint is on screen. Checkpoints are cumulative native geometry of the same physical part. A pending build does not become a new accepted STEP merely because the viewer is open.

Preview shading preserves creases above 30 degrees while smoothing smaller mesh
facets on curved surfaces. Averaging normals across every shared vertex makes
machined or moulded flat faces look rounded. The shared-box and cylinder-wall
regression checks preserve both hard corners and smooth curves without moving
preview vertices or changing the native STEP.

## Text-to-CAD source evidence

Public source inspected at commit `5efa85a911d9d0d3802fe516fe3c8cc387c47ea8`. The read-only source capture and hashes are retained locally in `evidence/chat-step-viewer/upstream/sources.json`.

- [Shared UI](https://github.com/earthtojake/text-to-cad/blob/5efa85a911d9d0d3802fe516fe3c8cc387c47ea8/packages/ui/README.md) separates reusable file rendering from its host.
- [Viewer host contract](https://github.com/earthtojake/text-to-cad/blob/5efa85a911d9d0d3802fe516fe3c8cc387c47ea8/packages/ui/docs/viewer-host.md) assigns environmental effects and prompt context to host adapters. A small conversation view still has a complete viewer rather than becoming a thumbnail.
- [Interaction contract](https://github.com/earthtojake/text-to-cad/blob/5efa85a911d9d0d3802fe516fe3c8cc387c47ea8/packages/ui/docs/settings-ui.md) gives the file navbar and floating tool strip separate responsibilities. File-side panels relate to the document. Its optional Quick Edit is a prompt handoff.

These are source observations, not an executed upstream-runtime test. Complete public source answers this UI-ownership question, so REA binary/session/provider setup is unnecessary. No upstream installation or configuration repair was performed.

The design choice here follows the user's narrower brief. Retain the file-and-canvas pattern, and remove Quick Edit and project editing from the pane. The modeling kernel remains smlibpy; the reference's build123d implementation does not change that requirement.

## Behavior contract

The pane follows only its explicitly supplied job. Visible ready views continue reading that job so later agent edits arrive without a reload. Context-only changes preserve mesh identity. Hidden views pause polling. New jobs, revisions, and artifact hashes invalidate old preview and checkpoint ownership.

Downloads retain the existing server's readiness, membership, containment, hash, and size checks. Host-side downloads intercept authorized artifact links and never recursively intercept temporary blob links. Missing output shows a concise state that directs the user to continue in the conversation.

## Verification

Verify one built candidate in a combined desktop/mobile inspection, fix all observed UI defects in one batch, and confirm at most once more. Keep agent-tool operations separate from browser actions. A copied accepted case proves display only; actual execution needs a real kernel run. Local MCP protocol and SDK tests do not establish a real ChatGPT-account connection.

The public release retains hard-edge and smooth-cylinder regression checks,
revision ownership tests and actual native example integration. See the
[release verification](../verification.md) for what ran and what remains outside
its scope. The relay [source-fidelity audit](../../cases/omron-g2r/MANUAL-AUDIT.md)
remains a failed reconstruction result despite valid solids and STEP exchange.
