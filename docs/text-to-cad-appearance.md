# Text-to-CAD workbench appearance

The owner requested the appearance of Text-to-CAD, particularly its interaction
and rendering details. This is a local visual adaptation of the installed
0.10.0 viewer. It retains this product's three-column layout, physical hierarchy,
source/proposal review, context checks and native CAD workflow.

## Observed reference

The installed viewer has a36px document header, compact system-sans type, neutral
charcoal panels, restrained1px borders,6/8/10px corner roles and a small floating
icon strip. Hover, selected, disabled and keyboard-focus states are separate.
The observed workbench-dark canvas is#25272b; the actual same assembled STEP
renders with cool blue-gray faces and clear dark feature edges, without a floor.
The reference's tool selection, measurement, sectioning and view-cube features
are not introduced by this appearance change.

Shipped CSS and static preset observations inform the local theme:

- Dark background:oklch(28% .008 264), raised31%, secondary34%, accent38%.
- Text:98.5% foreground,75% muted; white10% dividers.
- Controls:compact13px system type,6–10px corner roles, restrained shadows.
- Workbench material:roughness.58, metalness.02, clearcoat.12,
  clearcoat roughness.42; exposure1.16 and cool-white lighting.
- Edge default:#18181b and opacity.84. Local selection uses brighter blue.

The local model palette is calibrated for this Three.js lighting setup; it is
not a CAD material assignment. Geometry, source colors, placements, approvals,
STEP and recorded artifact hashes are unchanged. The label distinguishes
concept geometry from the current verified native tessellation.

## Adaptation

[decomposition-theme.css](../web/src/decomposition-theme.css) scopes the visual
vocabulary to the decomposition workbench. The base layout and Silence token
source remain available, and the legacy STEP pane is unchanged. Dark appearance
matches the requested installed reference; no theme picker is implied.

Header, workflow and tree spacing are more compact. Existing panel placement,
controls and accessible names remain. Mobile keeps44px model/action targets.
Reference and Checks retain the selected title and prioritize their own content;
notes, IDs, duplicate entry buttons and Codex handoff remain in Details.
Tooltips describe the actual existing view actions. No inert controls are added.

## Evidence boundary

REA6.4.0 analyzed the shipped JavaScript/HTML tree:
`ev_f784147de28e2f1fe1643ed8b0c023469d60651df1f3d65bbb22cc4f227979a6`.
The summary view is
`ev_f8a14e04d58d912e17660357a8fe34727acbccea6b8c49e12e169c159bf6df63`.
The artifact SHA256 is
`9e447abc6e5a963b8296436effb265e6ed3e443d7b0b5721efb5495055f7b99f`.
All31 JavaScript files parsed with no parse failure. Application/semantic
relationship coverage is partial because expanded vendor relationships reached
resource limits. Static preset observations do not establish active behavior.
Separate local runtime observation opened the same independently verified
assembly STEP in the installed reference viewer and corroborated its visible
canvas, chrome and rendering. Private analysis, captures and local access tokens
are excluded from shared Git.

The reference is [text-to-cad](https://github.com/earthtojake/text-to-cad),
MIT-licensed. No shipped bundles, icons or proprietary branding are copied into
this application. Its native construction remains smlibpy.
