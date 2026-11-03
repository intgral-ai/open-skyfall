const dimensionLabels = {
  box: ["X", "Y", "Z"],
  cylinder: ["Radius", "Height"],
  sphere: ["Radius"],
  shell: ["Lower radius", "Upper radius", "Height", "Wall"],
};

export function assertAnalysisBinding(project) {
  if (project.analysis == null) return;
  const binding = project.analysis.binding;
  if (
    binding?.project_id !== project.id ||
    binding?.revision !== project.revision
  )
    throw new Error(
      "Explanation binding does not match this project revision.",
    );
  if (
    project.program &&
    project.artifacts?.[project.program] !== binding.program_sha256
  )
    throw new Error(
      "Explanation does not match the registered program artifact.",
    );
}

function sameJson(left, right) {
  if (left === right) return true;
  if (!left || !right || typeof left !== "object" || typeof right !== "object")
    return false;
  if (Array.isArray(left) !== Array.isArray(right)) return false;
  const keys = Object.keys(left);
  return (
    keys.length === Object.keys(right).length &&
    keys.every(
      (key) => Object.hasOwn(right, key) && sameJson(left[key], right[key]),
    )
  );
}

export function assertProgramBinding(project, program) {
  if (!project.program) {
    if (project.plan && project.id !== "example")
      throw new Error("The displayed plan has no registered program artifact.");
    return;
  }
  assertAnalysisBinding(project);
  if (
    program?.format !== "open-skyfall-concept/1" ||
    !project.analysis?.binding ||
    !program.plan ||
    !program.source ||
    !program.runtime ||
    program.project_id !== project.id ||
    program.revision !== project.revision ||
    !sameJson(program.runtime, project.analysis?.binding?.runtime)
  )
    throw new Error(
      "Program artifact does not match this project revision or runtime.",
    );
  if (!sameJson(program.plan, project.plan))
    throw new Error(
      "Displayed plan does not match the registered program artifact.",
    );
  if (
    !sameJson(program.source, project.source) ||
    !sameJson(
      program.brief ?? null,
      project.workflow?.brief?.text ? project.workflow.brief : null,
    )
  )
    throw new Error(
      "Displayed source does not match the registered program artifact.",
    );
}

export function explainSelection(project, nodeId) {
  assertAnalysisBinding(project);
  const plan = project.plan;
  const explanation = plan?.explanation;
  const basisIds = new Set();
  function basis(id) {
    const entry = explanation?.bases?.[id];
    if (entry) basisIds.add(id);
    return entry ? { id, ...entry } : null;
  }
  const parameter = (address, label, value, unit) => ({
    address,
    label,
    value,
    unit,
    basis: basis(explanation?.parameters?.[address]),
  });
  const units = plan?.units === "mm" ? "mm" : "relative units";
  function pose(item, address) {
    return ["position", "rotation"].flatMap((kind) =>
      ["X", "Y", "Z"].map((axis, i) =>
        parameter(
          `${address}/${kind}/${i}`,
          `${kind === "position" ? "Position" : "Rotation"} ${axis}`,
          item[kind]?.[i] ?? 0,
          kind === "rotation" ? "deg" : units,
        ),
      ),
    );
  }
  const node = plan?.nodes.find((item) => item.id === nodeId);
  const definition = plan?.definitions.find(
    (item) => item.id === node?.definition_id,
  );
  const rationale = basis(explanation?.nodes?.[nodeId]?.part);
  const placement = basis(explanation?.nodes?.[nodeId]?.placement);
  const nodePose = node ? pose(node, `node/${node.id}`) : [];
  const shapes = (definition?.shapes || []).map((shape) => {
    const address = `shape/${definition.id}/${shape.id}`;
    return {
      id: shape.id,
      kind: shape.kind,
      basis: basis(explanation?.shapes?.[`${definition.id}/${shape.id}`]),
      dimensions: shape.dimensions.map((value, i) =>
        parameter(
          `${address}/dimensions/${i}`,
          dimensionLabels[shape.kind]?.[i] || `Dimension ${i + 1}`,
          value,
          units,
        ),
      ),
      pose: pose(shape, address),
    };
  });
  const scale = basis(explanation?.scale);
  const observations = (explanation?.observations || []).filter((observation) =>
    [...basisIds].some((id) =>
      explanation.bases[id].observations.includes(observation.id),
    ),
  );
  const tree = node ? hierarchy(plan.nodes) : null;
  const relevantNodes = new Set(
    node
      ? plan.nodes
          .filter((item) => tree.contains(node.id, item.id))
          .map((item) => item.id)
      : [],
  );
  const definitions = new Set(
    (plan?.nodes || [])
      .filter((item) => relevantNodes.has(item.id))
      .map((item) => item.definition_id),
  );
  const trace = node
    ? (project.analysis?.trace || []).filter((step) =>
        step.node_id
          ? relevantNodes.has(step.node_id)
          : step.definition_id
            ? definitions.has(step.definition_id)
            : step.operation === "normalize_view",
      )
    : [];
  return {
    complete: Boolean(
      explanation && project.analysis?.coverage?.status === "complete",
    ),
    coverage: project.analysis?.coverage,
    rationale,
    placement,
    nodePose,
    definitionId: definition?.id,
    occurrences: definition
      ? plan.nodes.filter((item) => item.definition_id === definition.id)
      : [],
    shapes,
    observations,
    trace,
    checks: project.analysis?.checks || [],
    scale,
  };
}

export function containedImageRect(width, height, imageWidth, imageHeight) {
  if (
    ![width, height, imageWidth, imageHeight].every(
      (value) => Number.isFinite(value) && value > 0,
    )
  )
    return null;
  const scale = Math.min(width / imageWidth, height / imageHeight);
  const w = imageWidth * scale,
    h = imageHeight * scale;
  return { x: (width - w) / 2, y: (height - h) / 2, width: w, height: h };
}

export function hostDownload(result, fallbackFilename) {
  if (result?.data_base64)
    return {
      filename: result.filename || fallbackFilename,
      mime: result.mime_type || "application/octet-stream",
      bytes: Uint8Array.from(atob(result.data_base64), (c) => c.charCodeAt(0)),
    };
  if (
    fallbackFilename.endsWith(".json") &&
    result &&
    typeof result === "object"
  )
    return {
      filename: fallbackFilename,
      mime: "application/json",
      bytes: new TextEncoder().encode(JSON.stringify(result, null, 2)),
    };
  throw new Error("The download did not contain an artifact.");
}
import { hierarchy } from "./decomposition-state.js";
