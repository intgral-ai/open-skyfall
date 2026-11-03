---
name: OpenSkyfall workbench
description: Silence adoption for inspecting source evidence, physical parts and reviewed CAD.
colors:
  primary: "#262626"
  background: "#fcfcfc"
  surface: "#f8f8f8"
  surface-raised: "#ffffff"
  foreground-strong: "#171717"
  foreground-secondary: "#525252"
  foreground-muted: "#6b6b6b"
  border: "#e5e5e5"
  control-border: "#858585"
  selection: "#edf0f2"
  success: "#24704d"
  success-soft: "#edf5ef"
  warning: "#805515"
  warning-soft: "#faf4e8"
  destructive: "#a83a3a"
  destructive-soft: "#f8eeee"
typography:
  headline:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "32px"
    fontWeight: 500
    lineHeight: "40px"
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "20px"
    fontWeight: 500
    lineHeight: "28px"
  body:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "22px"
  ui:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "20px"
  label:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 500
    lineHeight: "20px"
  meta:
    fontFamily: '"Geist", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "18px"
  code:
    fontFamily: '"Geist Mono", ui-monospace, "SFMono-Regular", Consolas, monospace'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "18px"
rounded:
  tag: "6px"
  control: "8px"
  media: "12px"
  floating: "16px"
spacing:
  compact: "4px"
  related: "8px"
  control: "12px"
  group: "16px"
  panel: "20px"
  section: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.foreground-secondary}"
    textColor: "{colors.background}"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.primary}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  project-select:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.primary}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  inspector-tab:
    textColor: "{colors.foreground-muted}"
    typography: "{typography.ui}"
    padding: "8px 0"
    height: "44px"
  outcome-pass:
    backgroundColor: "{colors.success-soft}"
    textColor: "{colors.success}"
    typography: "{typography.meta}"
    rounded: "{rounded.tag}"
    padding: "2px 8px"
  floating-panel:
    backgroundColor: "{colors.background}"
    textColor: "{colors.primary}"
    rounded: "{rounded.floating}"
---

# Design System: OpenSkyfall workbench

## Overview

**Creative North Star: "The model comes first"**

This is the workbench's app-specific adoption of Silence 1.0.2. It records the
existing inspection surface after an authorized refinement. The neutral shell,
clear type and restrained dividers keep attention on the actual model and its
evidence. Model materials and source imagery retain their own color.

The workbench supports source intake, proposal review, decomposition, physical
scope confirmation and explicit native conversion. Interpretation and iteration
remain in the host conversation. This visual document complements the existing
[architecture and limits](docs/design.md); it does not replace that document.
The implemented token subset is in [silence-tokens.css](web/src/silence-tokens.css),
with component and layout rules in [decomposition.css](web/src/decomposition.css).

**Key Characteristics:**

- A full-height model stage with complementary structure and inspector panels.
- Neutral actions and selection; semantic color accompanies written outcomes.
- Evidence, uncertainty, confirmation and native artifacts remain distinct.
- Keyboard controls, explicit focus and a native project selector.

## Colors

The palette uses near-white surfaces and dark neutral controls. Source images
and model colors are content, independent of the interface palette.

### Primary

- **Graphite:** primary actions, selected step markers and ordinary foreground.
- **Secondary graphite:** supporting prose and primary-action hover feedback.

### Neutral

- **Paper:** the page and inspector background.
- **Quiet surface:** the stage surround and quoted context.
- **Raised white:** fields and secondary controls.
- **Strong ink:** the strongest text emphasis.
- **Muted ink:** provenance and supplementary metadata.
- **Divider:** structural boundaries that do not identify an input.
- **Control border:** boundaries needed to recognize an interactive control.
- **Cool selection:** selected rows, toggles and completed step markers.

### Semantic outcomes

Success, warning and destructive tokens each have a foreground and soft surface.
Use them with the words **pass**, **blocked** or **fail**. An untested check stays
**unchecked**. A warning or unknown is not presented as success.

**The Content Color Rule.** Preserve the model and source colors; keep repeated
interface controls neutral and reserve semantic color for meaningful state.

## Typography

Geist serves the interface with the recorded CJK fallbacks. Geist is bundled;
the other named families depend on availability. Geist Mono is the preferred
family for hashes, identifiers and numeric comparison, with system mono fallbacks.

The frontmatter records the reused hierarchy: headline for the source/proposal
empty stage, title for the selected piece, body for inspector explanations, UI
and label for actions, and meta/code for provenance. At narrow widths the empty
stage headline becomes compact (24px / 32px). Numeric measurements use tabular
figures where declared. Long part labels and identifiers wrap in the inspector.

## Layout

The app fills the dynamic viewport. The desktop workspace has a structure column
(268px), a flexible model stage and an inspector (340px). Closing the inspector
returns its width to the stage. Before geometry exists, the structure column is
hidden. Panel content scrolls independently.

At widths up to 1000px, the model receives the whole workspace. Structure and
inspector become explicitly opened floating panels, inset from the stage (16px)
and bounded to its width. The header becomes two rows at widths up to 760px:
brand/actions first, then the visible **Project** label and native selector.
The selector groups **Examples** and **Saved projects**. The five-step sequence
keeps every label visible, with centered markers above labels on narrow screens.
Entering the compact layout closes both panels; opening one closes the other.
Panel visibility and accessible toggle labels stay synchronized when the window
crosses the layout breakpoint.

Use the recorded spacing rhythm for related controls and section separation.
Desktop primary controls are at least 40px high; narrow-screen primary actions,
tree selections and model toolbar targets reach 44px. Compact close/disclosure
controls have their own implemented sizes and are not a universal touch-size rule.

## Elevation & Depth

The desktop shell uses flat surfaces, whitespace and single dividers. Floating
structure/inspector panels use one soft shadow; its exact value is retained in
the sidecar. The model's lighting and shadows belong to the rendered content.
They do not prescribe elevation for ordinary UI containers.

## Shapes

Controls use gently curved corners, compact outcome labels use the tag radius,
source media uses the media radius, and floating panels use the floating radius.
Workflow markers are centered circles (26px) containing either a number or an
inline SVG check. Icons use a consistent thin stroke and explicit accessible
labels when no text is visible.

## Components

### Actions, fields and project selection

Primary actions use graphite and paper; hover uses secondary graphite. Secondary
controls use raised white or a transparent surface, with selection feedback.
Focus is a visible two-pixel graphite outline. Disabled controls retain a visible
disabled state and cannot trigger an action. Working actions use a written busy
label. Source intake uses labeled name, image, description and rights fields,
with explicit validation errors. Field styling remains local to that existing
dialog rather than defining a new general form system.

The project picker remains a native `select` with a visible label, grouped
options and saved project revision labels. It is usable by keyboard and has a
dedicated full-width row on narrow screens.

### Workflow progress

The sequence is **1 Source → 2 Proposal → 3 Decompose → 4 Review → 5 CAD**.
It is status information, not an alternate navigation system. Upcoming/current
steps retain centered numbers; completed steps use centered SVG checks.

Source requires a stored source identity. Proposal confirmation allows
decomposition; an accepted Plan moves the workflow to review. Review requires
the current physical parts to be confirmed with no pending captured requests.
CAD remains current until a current, ready full-assembly build is available.
The renderer uses the workflow's verified current-build eligibility, including
part approval, build identity and review digests; a concept preview or an old
build cannot complete the sequence.

**The Current Evidence Rule.** A visible completion or passing report must bind
to the current source, accepted program and reviewed physical scope.

### Structure and model tools

The tree represents physical occurrences and groups; reusable definitions stay
distinct from occurrences. Selected rows use cool selection. Fit, focus,
isolation, hide and restore retain their existing model behavior. Explosion is
a display offset and preserves authored placements. The stage keeps shaded
orthographic rendering and the actual model as its primary content.

### Inspector and independent references

Every selected piece exposes **Reference** and **Checks**, alongside **Details**.
The tab list supports arrow keys, Home and End. Details keeps the design note
collapsed, with confirmation, native artifact and construction evidence below.
Reference shows actual bound source observations, image regions or literal
quotes, plus saved check context. Missing observations remain explicitly missing.

In the standalone viewer, **Open this part separately** opens
`?project=PROJECT_ID&part=NODE_ID&view=reference`. It selects that occurrence and
opens its Reference panel at the top. An embedded host uses its existing inspection and
handoff affordances. Copy feedback distinguishes host delivery, clipboard copy
and a manual-copy fallback.

### Scoped checks and outcomes

Checks belong to the selected part or group. A group covers its physical
descendants; shared definitions can affect other occurrences. The current report
must match project, revision, source, literal brief, accepted program, selected
node, scope review digest, criteria digest and native build IDs. Mismatches show
an out-of-date message and require a new run.

The Checks panel presents the overall outcome and counts, then the user's saved
criteria. Numeric criteria show actual value, required limit/range, unit and the
literal quoted requirement. Supporting structural checks and raw CI evidence
remain expandable. No rules means **Run structural checks**; defining or refining
requirements hands the literal context to the host's `open-skyfall-check` Skill.

Use [the check Skill](skills/open-skyfall-check/SKILL.md) for the authoritative
HTTP payloads, parameter address scope, supported units and CI command. Required
manual criteria remain blocked. Structural validity and a passing authored
parameter range do not establish source fidelity, collision freedom, tolerance
stacks, load capacity, fit, finish or manufacturing acceptance. Relative geometry
cannot satisfy an unsupported millimeter requirement.

### Native builds and downloads

Confirmation binds the exact current shape and placement scope. Pending changes,
unsupported units and ineligible scopes keep native conversion disabled. Building,
failure, no current build, current selected build and complete assembly are
separate visible states. Complete assembly download appears only for the current
full build; it is distinct from a selected-scope STEP and from accepted concept
program/replay downloads. Source fidelity and manufacturing review stay separate.

## Do's and Don'ts

### Do:

- **Do** keep the actual model and its source evidence visually primary.
- **Do** preserve literal requirements, units, unknowns and current scope identities.
- **Do** pair outcome color with written status and readable evidence.
- **Do** retain visible keyboard focus and native project selection.

### Don't:

- **Don't** treat proposal approval, part confirmation and CAD completion as one state.
- **Don't** reuse a passing report after its revision, criteria or scope binding changes.
- **Don't** imply manufacturing acceptance from structural checks or valid STEP.
- **Don't** turn model materials, legacy one-off colors or decorative labels into UI tokens.
