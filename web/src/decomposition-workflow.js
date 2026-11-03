export const phases = ["input", "proposal", "decomposition", "review", "cad"];

export function intakePayload({ name, rights, description, data_base64 }) {
  if (!description?.trim() && !data_base64)
    throw new Error("Add a reference image or describe the object.");
  if (!rights?.trim()) throw new Error("Describe your rights to this source.");
  return {
    name: name?.trim() || "Untitled decomposition",
    rights: rights.trim(),
    description: description || "",
    workflow: true,
    ...(data_base64 ? { data_base64 } : {}),
  };
}

export function selectionWorkflow(project, nodeId) {
  const workflow = project?.workflow;
  const scope = workflow?.scopes?.[nodeId];
  const parts = (workflow?.parts || []).filter((part) =>
    scope?.part_ids?.includes(part.node_id),
  );
  const busy = workflow?.status === "building";
  const bound = Boolean(scope?.review_digest && scope.part_count > 0);
  const pendingRequests = (workflow?.requests || []).filter(
    (request) =>
      request.status === "pending" &&
      request.part_ids?.some((id) => scope?.part_ids?.includes(id)),
  );
  const assemblyId = workflow?.cad?.assembly;
  const assembly = assemblyId ? workflow.builds?.[assemblyId] : null;
  const currentParts = new Map(
    (workflow?.parts || []).map((part) => [part.node_id, part]),
  );
  function buildIsCurrent(buildId, build) {
    const ids = build?.binding?.part_ids;
    return (
      build?.status === "ready" &&
      Array.isArray(ids) &&
      ids.length > 0 &&
      ids.every((id) => {
        const part = currentParts.get(id);
        return (
          part?.approved === true &&
          part.cad_build_id === buildId &&
          part.review_digest === build.binding.review_digests?.[id]
        );
      })
    );
  }
  const partBuildIds = new Set(
    parts.map((part) => part.cad_build_id).filter(Boolean),
  );
  const selectedBuildId =
    partBuildIds.size === 1 && parts.every((part) => part.cad_build_id)
      ? [...partBuildIds][0]
      : null;
  const selectedBuild = selectedBuildId
    ? workflow.builds?.[selectedBuildId]
    : null;
  return {
    scope,
    parts,
    busy,
    pendingRequests,
    canApprove: bound && !busy && !scope.approved && !pendingRequests.length,
    canBuild:
      bound &&
      !busy &&
      scope.approved === true &&
      !pendingRequests.length &&
      scope.can_build === true &&
      project.plan?.units === "mm",
    assembly: buildIsCurrent(assemblyId, assembly)
      ? { id: assemblyId, ...assembly }
      : null,
    selectedBuild: buildIsCurrent(selectedBuildId, selectedBuild)
      ? { id: selectedBuildId, ...selectedBuild }
      : null,
  };
}

export function workflowBinding(project) {
  if (
    !project?.id ||
    !Number.isInteger(project.revision) ||
    !Number.isInteger(project.workflow_revision)
  )
    throw new Error(
      "This project does not have a current workflow binding. Reopen it before acting.",
    );
  return {
    revision: project.revision,
    workflow_revision: project.workflow_revision,
  };
}

export function buildArtifactPath(projectId, buildId, filename) {
  if (
    !buildId ||
    !filename ||
    filename.startsWith("/") ||
    filename.split("/").some((part) => !part || part === "." || part === "..")
  )
    throw new Error("Invalid native artifact path.");
  return `/api/decompositions/${encodeURIComponent(projectId)}/workflow/builds/${encodeURIComponent(buildId)}/artifacts/${filename.split("/").map(encodeURIComponent).join("/")}`;
}

export function verifyNativePreview(project, build, preview) {
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object")
      return Object.fromEntries(
        Object.keys(value)
          .sort()
          .map((key) => [key, canonical(value[key])]),
      );
    return value;
  }
  const binding = build?.binding;
  if (
    !binding ||
    binding.project_id !== project.id ||
    binding.source_sha256 !== project.source.sha256 ||
    JSON.stringify(canonical(preview?.binding)) !==
      JSON.stringify(canonical(binding))
  )
    throw new Error("Native preview does not match this reviewed build.");
  const ids = preview.parts?.map((part) => part.id);
  const expected = binding.part_ids;
  if (
    preview.backend !== "smlibpy" ||
    !Array.isArray(ids) ||
    !Array.isArray(expected) ||
    ids.length !== expected.length ||
    new Set(ids).size !== ids.length ||
    ids.some((id) => !expected.includes(id)) ||
    preview.parts.some(
      (part) =>
        project.plan.nodes.find((node) => node.id === part.id)
          ?.definition_id !== part.definition_id,
    )
  )
    throw new Error(
      "Native preview part identities differ from the reviewed scope.",
    );
}

export function iterationMessage(project, nodeId) {
  const node = project.plan?.nodes.find((item) => item.id === nodeId);
  const shared =
    project.workflow?.parts?.find((part) => part.node_id === nodeId)
      ?.shared_occurrence_ids || [];
  const scope = project.workflow?.scopes?.[nodeId];
  return `I want to iterate on this OpenSkyfall selection. Project ${project.id}, revision ${project.revision}, workflow revision ${project.workflow_revision}. Source SHA256 ${project.source.sha256}. Selected node ${nodeId} (${node?.label || nodeId}). Scope ${scope?.part_ids?.join(", ") || nodeId}. Review digest ${scope?.review_digest || "unavailable"}. ${shared.length > 1 ? `The shared definition also affects ${shared.join(", ")}. ` : ""}Ask me what to change, then capture my literal request through the workflow request action before editing the Plan. Preserve unchanged IDs and poses. Do not approve or build parts on my behalf.`;
}

export function createWorkflowActions({
  getProject,
  getNavigationToken = () => undefined,
  action,
  accept,
  notify = () => {},
}) {
  let pending = false;
  return {
    get pending() {
      return pending;
    },
    async run(name, payload = {}) {
      if (pending) return null;
      const snapshot = getProject();
      const navigationToken = getNavigationToken();
      const binding = workflowBinding(snapshot);
      pending = true;
      notify(true);
      try {
        const project = await action(
          `/api/decompositions/${encodeURIComponent(snapshot.id)}/workflow/${name}`,
          { ...payload, ...binding },
        );
        if (
          getProject()?.id !== snapshot.id ||
          getNavigationToken() !== navigationToken
        )
          return null;
        if ((await accept(project)) === false) return null;
        return project;
      } finally {
        pending = false;
        notify(false);
      }
    },
  };
}
