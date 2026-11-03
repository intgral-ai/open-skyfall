export function changeSelection(current, id, additive = false) {
  if (!id) return additive ? [...current] : [];
  if (!additive) return [id];
  return current.includes(id)
    ? current.filter((item) => item !== id)
    : [...current, id];
}

export function selectionContains(tree, ids, partId) {
  return ids.some((id) => tree.contains(id, partId));
}

export function selectionContext(project, ids) {
  const nodes = new Map(
    (project.plan?.nodes || []).map((node) => [node.id, node]),
  );
  const nodeIds = [...new Set(ids)];
  if (!nodeIds.length || nodeIds.some((id) => !nodes.has(id)))
    throw new Error("Select current parts before handing them to Codex.");
  const inScope = (id) => {
    for (let node = nodes.get(id); node; node = nodes.get(node.parent_id))
      if (nodeIds.includes(node.id)) return true;
    return false;
  };
  const physical = [...nodes.values()].filter(
    (node) => node.definition_id && inScope(node.id),
  );
  const definitions = new Set(physical.map((node) => node.definition_id));
  const shared = new Set(
    physical.flatMap(
      (node) =>
        project.workflow?.parts?.find((part) => part.node_id === node.id)
          ?.shared_occurrence_ids || [],
    ),
  );
  for (const node of nodes.values())
    if (node.definition_id && definitions.has(node.definition_id))
      shared.add(node.id);
  const partIds = physical.map((node) => node.id).sort();
  return {
    format: "cad-selection/1",
    project_id: project.id,
    revision: project.revision,
    workflow_revision: project.workflow_revision ?? null,
    source_sha256: project.source.sha256,
    program_sha256: project.analysis?.binding?.program_sha256 ?? null,
    units: project.plan?.units || "unverified",
    node_ids: nodeIds,
    selected_nodes: nodeIds.map((id) => {
      const node = nodes.get(id);
      return {
        id,
        label: node.label,
        definition_id: node.definition_id || null,
        parent_id: node.parent_id || null,
        position: node.position || [0, 0, 0],
        rotation: node.rotation || [0, 0, 0],
        review_digest: project.workflow?.scopes?.[id]?.review_digest || null,
      };
    }),
    physical_part_ids: partIds,
    affected_part_ids: [...new Set([...partIds, ...shared])].sort(),
    shared_unselected_part_ids: [...shared]
      .filter((id) => !partIds.includes(id))
      .sort(),
    review_workflow: Boolean(project.workflow),
    read_only_example: project.id === "example",
  };
}

export function selectionMessage(project, ids) {
  const context = selectionContext(project, ids);
  return `I want to modify the selected CAD parts in project ${project.id}, revision ${project.revision}, workflow revision ${project.workflow_revision ?? "unavailable"}. Ask me what to change, then capture my literal request before editing.\n\nSelection context:\n${JSON.stringify(context, null, 2)}\n\nRead the current saved Plan and reference before changing geometry. Check the revision, source hash and every selected review digest; ask me to reselect if they changed. ${context.review_workflow ? "Capture one request using request_id, node_ids from this selection, my exact text, revision and workflow_revision. The server expands shared definitions." : "This source has no review workflow. Import it into a saved reviewed project before capturing a change; the example is read-only."} Explain the impact of shared definitions, including unselected occurrences. Change only the selected scope and explicitly disclosed shared occurrences. Preserve all other IDs, dimensions and assembled poses. Viewer explosion offsets are not CAD placements. Submit the full updated Plan with the captured request_id. Do not approve or build parts on my behalf.`;
}
