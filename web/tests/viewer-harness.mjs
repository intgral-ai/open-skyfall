import { createViewer } from "../src/viewer-state.js";

export const job = (id = "A", revision = 1, extra = {}) => ({
  id,
  name: `Model ${id}`,
  revision,
  state: "ready",
  updated_at: `2026-11-02T12:00:0${revision}Z`,
  artifacts: { "assembly.step": { sha256: `${id}-${revision}` } },
  document: {
    occurrences: [{ id: "plate-1", definition_id: "plate" }],
    definitions: [{ id: "plate", label: "Plate" }],
  },
  ...extra,
});
export function harness() {
  const pending = [],
    draws = [],
    errors = [],
    resets = [],
    timers = new Map();
  let timerId = 0;
  const controller = createViewer({
    read: (path) =>
      new Promise((resolve, reject) => pending.push({ path, resolve, reject })),
    draw: (preview) => draws.push(preview.id),
    error: (error) => errors.push(error.message),
    reset: () => resets.push(true),
    setTimer: (fn, ms) => {
      const id = ++timerId;
      timers.set(id, { fn, ms });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
  });
  const next = (path) => {
    const index = pending.findIndex((item) => item.path === path);
    if (index < 0)
      throw new Error(
        `No pending read for ${path}; got ${pending.map((p) => p.path)}`,
      );
    return pending.splice(index, 1)[0];
  };
  const runTimer = (ms = 2000) => {
    const entry = [...timers].find(([, timer]) => timer.ms === ms);
    if (!entry) throw new Error(`No ${ms}ms timer`);
    timers.delete(entry[0]);
    return entry[1].fn();
  };
  return { controller, pending, draws, errors, resets, timers, next, runTimer };
}
export async function ready(
  h,
  snapshot = job(),
  preview = { id: "final", parts: [] },
) {
  const loading = h.controller.accept(snapshot);
  h.next(`/api/jobs/${snapshot.id}/artifacts/preview.json`).resolve(preview);
  if (snapshot.document?.backend === "smlibpy")
    h.next(`/api/jobs/${snapshot.id}/artifacts/construction.json`).resolve({
      stages: [
        { label: "Base", preview_artifact: "checkpoints/1.json" },
        { label: "Hole", preview_artifact: "checkpoints/2.json" },
      ],
    });
  await loading;
}
