---
name: CAD workbench
description: Text-to-CAD workbench appearance for source evidence, physical parts and reviewed CAD.
colors:
  primary: "#e4e8ed"
  background: "#27292d"
  surface: "#25272b"
  surface-raised: "#2f3035"
  foreground-strong: "#fafafa"
  foreground-secondary: "#cecece"
  foreground-muted: "#aeaeae"
  border: "#3d3e42"
  control-border: "#5b5c5f"
  selection: "#404247"
  success: "#8ac7a3"
  success-soft: "#23352d"
  warning: "#e7c48b"
  warning-soft: "#393227"
  destructive: "#ffb4ab"
  destructive-soft: "#3a2628"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "32px"
    fontWeight: 500
    lineHeight: "40px"
    letterSpacing: "-0.02em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "20px"
    fontWeight: 500
    lineHeight: "28px"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "22px"
  ui:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "20px"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 500
    lineHeight: "20px"
  meta:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif'
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

# Design System: CAD workbench

## Overview

**Creative North Star: "The model comes first"**

This app uses the installed Text-to-CAD 0.10.0 workbench as its visual reference,
following the owner's explicit request. The existing three-column structure,
workflow, source review, scoped checks and native CAD gates remain in place.
The neutral dark shell, compact system type and restrained controls place the
actual model first. Local colors and geometry are untouched by display styling.

The underlying Silence token vocabulary stays available to existing surfaces.
[decomposition-theme.css](web/src/decomposition-theme.css) scopes this workbench's
visual override; the canonical team design system and legacy STEP viewer are
unchanged. [Architecture and limits](docs/design.md) remains authoritative for
workflow and CAD behavior. [Visual provenance](docs/text-to-cad-appearance.md)
records shipped artifact evidence, runtime observations and adaptation choices.

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

- **Charcoal:** the page and inspector background.
- **Canvas:** the solid model stage and quoted context.
- **Raised surface:** fields and secondary controls.
- **Foreground:** the strongest text emphasis.
- **Muted foreground:** provenance and supplementary metadata.
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

System sans serves this workbench, matching the installed reference. The bundled
Geist remains available to the legacy viewer. Geist Mono is the preferred
family for hashes, identifiers and numeric comparison, with system mono fallbacks.

The frontmatter records semantic roles. The local workbench theme uses compact
13px body/UI, 12px tree rows and 11px metadata. It preserves larger touch targets.
The inherited role hierarchy is: headline for the source/proposal
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
and bounded to its width. The header stays two rows at widths up to 760px:
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

The desktop shell uses flat dark surfaces and single low-contrast dividers. Floating
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
a display offset and preserves authored placements. The stage keeps orthographic rendering, a solid charcoal background, cool steel
blue display materials and crisp dark edges. It omits decorative ground/grid.
Selected geometry uses a brighter blue. The same style applies to concept and
verified native tessellations; the label continues to distinguish them.

### Inspector and independent references

Every selected piece exposes **Reference** and **Checks**, alongside **Details**.
The tab list supports arrow keys, Home and End. Details keeps notes, IDs, Codex handoff, confirmation and native artifacts.
Reference and Checks suppress repeated entry controls and notes so their scoped
content starts near the top. The controls remain available in Details.
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
