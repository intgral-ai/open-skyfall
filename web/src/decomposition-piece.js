import { selectionWorkflow } from "./decomposition-workflow.js";

const labels = ["Source", "Proposal", "Decompose", "Review", "CAD"];

export function workflowProgress(project) {
  const flow = project?.workflow;
  const hasSource = Boolean(project?.source?.sha256);
  const hasPlan = Boolean(project?.plan);
  const parts = flow?.parts || [];
  const pending = flow?.requests?.some(
    (request) => request.status === "pending",
  );
  const confirmed =
    parts.length > 0 && parts.every((part) => part.approved) && !pending;
  const complete = Boolean(selectionWorkflow(project, null).assembly);
  const active = !hasSource
    ? 0
    : !hasPlan
      ? flow?.proposal?.approved
        ? 2
        : 1
      : !confirmed
        ? 3
        : 4;
  const completed = [
    hasSource,
    flow?.proposal?.approved === true,
    hasPlan,
    confirmed,
    complete,
  ];
  return labels.map((label, index) => ({
    label,
    number: index + 1,
    state: completed[index]
      ? "complete"
      : index === active
        ? "current"
        : "upcoming",
    current: index === active,
  }));
}

export function pieceReferenceURL(base, projectId, nodeId) {
  const url = new URL(base);
  url.search = "";
  url.hash = "";
  url.searchParams.set("project", projectId);
  url.searchParams.set("part", nodeId);
  url.searchParams.set("view", "reference");
  return url.href;
}

export function currentCheckReport(project, nodeId) {
  const checks = project?.workflow?.checks?.[nodeId];
  const report = checks?.report;
  const binding = report?.binding;
  const scope = project?.workflow?.scopes?.[nodeId];
  if (
    !report ||
    report.status !== "current" ||
    !binding ||
    binding.project_id !== project.id ||
    binding.node_id !== nodeId ||
    binding.revision !== project.revision ||
    binding.source_sha256 !== project.source?.sha256 ||
    binding.brief_sha256 !== project.workflow?.brief?.sha256 ||
    binding.program_sha256 !== project.analysis?.binding?.program_sha256 ||
    binding.review_digest !== scope?.review_digest ||
    binding.criteria_digest !== checks.criteria_digest
  )
    return null;
  const nativeIds = binding.native_build_ids;
  if (
    !nativeIds ||
    Object.keys(nativeIds).length !== scope.part_ids.length ||
    scope.part_ids.some(
      (id) =>
        nativeIds[id] !==
        (project.workflow.parts.find((part) => part.node_id === id)
          ?.cad_build_id || null),
    )
  )
    return null;
  return report;
}

export function checkMessage(project, nodeId) {
  const scope = project.workflow?.scopes?.[nodeId];
  const node = project.plan?.nodes.find((item) => item.id === nodeId);
  return `Use the open-skyfall-check Skill to check ${node?.label || nodeId}. Project ${project.id}, revision ${project.revision}, workflow revision ${project.workflow_revision}, selected node ${nodeId}, review digest ${scope?.review_digest || "unavailable"}. Read the saved source, literal brief, selected references, manufacturing proposals and existing check context. Ask for missing requirements, preserve the user's exact words, then save quoted, unit-aware criteria through check-context and run check. Report pass, fail, blocked and unchecked separately. Do not infer factory approval, source fidelity or collision freedom from valid meshes. Do not alter geometry or confirm parts.`;
}
