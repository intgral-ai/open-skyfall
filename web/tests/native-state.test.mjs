import assert from "node:assert/strict";
import test from "node:test";
import { harness, job, ready } from "./viewer-harness.mjs";
const native = () =>
  job("A", 1, { document: { ...job().document, backend: "smlibpy" } });

test("checkpoint preview stays separate from final geometry and physical parts", async () => {
  const h = harness();
  await ready(h, native());
  const stage = h.controller.selectStage(0);
  h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({
    id: "base",
    parts: [],
  });
  await stage;
  assert.equal(h.controller.state.stageIndex, 0);
  assert.equal(h.controller.state.preview.id, "final");
  assert.equal(h.controller.state.displayedPreview.id, "base");
  assert.equal(h.controller.state.job.document.occurrences.length, 1);
  assert.equal(h.controller.state.job.artifacts["assembly.step"].sha256, "A-1");
  await h.controller.selectStage(null);
  assert.deepEqual(h.draws, ["final", "base", "final"]);
});

test("late checkpoint reads cannot replace a newer stage or final model", async () => {
  const h = harness();
  await ready(h, native());
  const first = h.controller.selectStage(0);
  const second = h.controller.selectStage(1);
  h.next("/api/jobs/A/artifacts/checkpoints/2.json").resolve({ id: "second" });
  await second;
  h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({ id: "first" });
  await first;
  const late = h.controller.selectStage(0);
  await h.controller.selectStage(null);
  h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({ id: "late" });
  await late;
  assert.deepEqual(h.draws, ["final", "second", "final"]);
});

test("new STEP identity invalidates checkpoint and construction responses", async () => {
  const h = harness();
  await ready(h, native());
  const stage = h.controller.selectStage(0);
  await ready(h, job("B"), { id: "B" });
  h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({ id: "stale" });
  await stage;
  assert.deepEqual(h.draws, ["final", "B"]);
  assert.equal(h.controller.state.construction, null);
});

test("construction playback visits cumulative stages then restores final and stops", async () => {
  const h = harness();
  await ready(h, native());
  const play = h.controller.play();
  h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({ id: "base" });
  await play;
  const advance = h.runTimer(1200);
  h.next("/api/jobs/A/artifacts/checkpoints/2.json").resolve({ id: "hole" });
  await advance;
  await h.runTimer(1200);
  assert.deepEqual(h.draws, ["final", "base", "hole", "final"]);
  assert.equal(h.controller.state.playing, false);
  assert.equal(h.controller.state.stageIndex, null);
});

test("hiding or selecting final cancels pending playback and stale checkpoint work", async () => {
  for (const hide of [true, false]) {
    const h = harness();
    await ready(h, native());
    const play = h.controller.play();
    if (hide) await h.controller.setVisible(false);
    else await h.controller.selectStage(null);
    h.next("/api/jobs/A/artifacts/checkpoints/1.json").resolve({ id: "late" });
    await play;
    assert.deepEqual(h.draws, hide ? ["final"] : ["final", "final"]);
    assert.equal(h.controller.state.playing, false);
    assert.equal(
      [...h.timers.values()].filter((timer) => timer.ms === 1200).length,
      0,
    );
  }
});
