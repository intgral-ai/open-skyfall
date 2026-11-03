# OpenSkyfall development

Read README.md and docs/design.md before changing the workflow.

- Use smlibpy for new native construction and STEP export. Legacy geometry
  paths remain explicitly identified until migrated.
- Manage iteration authoring in chat tools. The viewer supports source intake,
  proposal and part confirmation, and explicit native conversion. Keep its model
  inspector free of a second iteration composer. A clipboard locator does not
  establish host-message delivery.
- Keep physical parts, construction operations, placements and revisions separate.
- Source fidelity is a separate gate from valid solids and STEP round trips.
  A guessed internal part or a matching outer box does not establish fidelity.
- Preserve input rights, source hashes, upstream licenses and failure evidence.
- Run the relevant checks in CONTRIBUTING.md. Use .agents/skills/verify/SKILL.md
  for native, transport and browser journeys. Do not weaken an acceptance gate
  to make an illustrative demo pass reconstruction.
- Do not commit credentials, local environments, private inputs or generated
  bundles containing source manuals. Use independently shareable fixtures.
