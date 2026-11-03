export const palette = [
  "#9fb5c7",
  "#9bb2c5",
  "#acc0d0",
  "#92abbe",
  "#a6bdce",
  "#9eb5c8",
];
export function nodeColor(id) {
  let hash = 2166136261;
  for (const char of id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return palette[(hash >>> 0) % palette.length];
}

export function followExplosion(value, target, dt, reducedMotion = false) {
  if (reducedMotion || Math.abs(value - target) < 0.02) return target;
  return (
    value +
    (target - value) * (1 - Math.exp(-Math.min(Math.max(dt, 0), 0.05) / 0.2))
  );
}
export function hierarchy(nodes) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map(nodes.map((node) => [node.id, []]));
  const depths = new Map();
  for (const node of nodes)
    if (node.parent_id) children.get(node.parent_id).push(node.id);
  const root = nodes.find((node) => !node.parent_id).id;
  function visit(id, depth) {
    depths.set(id, depth);
    for (const child of children.get(id)) visit(child, depth + 1);
  }
  visit(root, 0);
  function contains(parent, id) {
    for (let node = byId.get(id); node; node = byId.get(node.parent_id))
      if (node.id === parent) return true;
    return false;
  }
  function atDepth(id, depth) {
    while (depths.get(id) > depth) id = byId.get(id).parent_id;
    return id;
  }
  return {
    byId,
    children,
    depths,
    root,
    contains,
    atDepth,
    maxDepth: Math.max(...depths.values()),
  };
}
export function partVisible(tree, id, selected, isolate, hidden) {
  return (
    (!isolate || !selected || tree.contains(selected, id)) &&
    ![...hidden].some((parent) => tree.contains(parent, id))
  );
}
export function explodeOffsets(tree, parts, depth, amount) {
  const centers = new Map();
  for (const id of tree.byId.keys()) {
    const members = parts.filter((part) => tree.contains(id, part.id));
    const low = [0, 1, 2].map((axis) =>
      Math.min(...members.map((p) => p.bounds[0][axis])),
    );
    const high = [0, 1, 2].map((axis) =>
      Math.max(...members.map((p) => p.bounds[1][axis])),
    );
    centers.set(
      id,
      low.map((v, axis) => (v + high[axis]) / 2),
    );
  }
  const local = new Map();
  for (const siblings of tree.children.values()) {
    const ordered = [...siblings].sort();
    if (!ordered.length) continue;
    const mean = [0, 1, 2].map(
      (axis) =>
        ordered.reduce((sum, id) => sum + centers.get(id)[axis], 0) /
        ordered.length,
    );
    const vectors = ordered.map((id) =>
      centers.get(id).map((v, axis) => v - mean[axis]),
    );
    const radius = Math.max(...vectors.map((v) => Math.hypot(...v)));
    ordered.forEach((id, index) => {
      const vector =
        radius > 1e-8
          ? vectors[index].map((v) => v / radius)
          : ordered.length > 1
            ? [Math.cos(index * 2.4), Math.sin(index * 2.4), 0]
            : [0, 0, 0];
      local.set(id, vector);
    });
  }
  return new Map(
    parts.map((part) => {
      const offset = [0, 0, 0];
      for (
        let id = tree.atDepth(part.id, depth);
        id !== tree.root;
        id = tree.byId.get(id).parent_id
      ) {
        const weight = amount * Math.pow(0.65, tree.depths.get(id) - 1);
        local.get(id).forEach((v, axis) => (offset[axis] += v * weight));
      }
      return [part.id, offset];
    }),
  );
}
