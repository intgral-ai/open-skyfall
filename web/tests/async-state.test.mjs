import assert from "node:assert/strict";
import test from "node:test";
import { harness, job, ready } from "./viewer-harness.mjs";

test("late previews and old polls cannot replace the selected job", async () => {
  const h = harness();
  const first = h.controller.accept(job("A"));
  await ready(h, job("B"), { id: "B", parts: [] });
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "A", parts: [] });
  await first;
  assert.deepEqual(h.draws, ["B"]);
  const poll = h.runTimer();
  await h.controller.accept(job("C", 1, { state: "queued" }));
  h.next("/api/jobs/B").resolve(job("B", 2));
  await poll;
  assert.equal(h.controller.state.job.id, "C");
  assert.equal(h.pending.length, 0);
});

test("ready jobs keep polling without rebuilding unchanged geometry or interrupting selection", async () => {
  const h = harness();
  await ready(h);
  h.controller.select("plate-1");
  const poll = h.runTimer();
  h.next("/api/jobs/A").resolve(
    job("A", 1, { context_revision: 7, updated_at: "2026-11-02T13:00:00Z" }),
  );
  await poll;
  assert.deepEqual(h.draws, ["final"]);
  assert.equal(h.resets.length, 1);
  assert.equal(h.controller.state.selected, "plate-1");
  assert.equal(h.controller.state.job.context_revision, 7);
  assert.ok([...h.timers.values()].some((timer) => timer.ms === 2000));
});

test("polls never overlap and failed reads keep the refresh loop alive", async () => {
  const h = harness();
  await ready(h);
  const poll = h.runTimer();
  await h.controller.poll();
  assert.equal(h.pending.length, 1);
  h.next("/api/jobs/A").reject(new Error("Offline"));
  await poll;
  assert.match(h.errors[0], /Offline/);
  assert.equal(h.timers.size, 1);
});

test("hidden views pause reads and playback, then refresh immediately on visibility", async () => {
  const h = harness();
  await ready(h);
  await h.controller.setVisible(false);
  assert.equal(h.timers.size, 0);
  await h.controller.poll();
  assert.equal(h.pending.length, 0);
  const visible = h.controller.setVisible(true);
  h.next("/api/jobs/A").resolve(job());
  await visible;
  assert.equal(h.draws.length, 1);
  assert.equal(h.timers.size, 1);
});

test("a hidden in-flight preview is discarded and reloaded on return", async () => {
  const h = harness();
  const load = h.controller.accept(job());
  await h.controller.setVisible(false);
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "hidden" });
  await load;
  assert.deepEqual(h.draws, []);
  const visible = h.controller.setVisible(true);
  h.next("/api/jobs/A").resolve(job());
  await new Promise(setImmediate);
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "visible" });
  await visible;
  assert.deepEqual(h.draws, ["visible"]);
});

test("older revisions and earlier snapshots cannot restore stale status or geometry", async () => {
  const h = harness();
  await ready(h, job("A", 3));
  await h.controller.accept(
    job("A", 2, { updated_at: "2099-01-01T00:00:00Z", state: "queued" }),
  );
  await h.controller.accept(
    job("A", 3, { updated_at: "2026-11-02T11:00:00Z", state: "queued" }),
  );
  assert.equal(h.controller.state.job.revision, 3);
  assert.equal(h.controller.state.job.state, "ready");
  assert.deepEqual(h.draws, ["final"]);
});

test("a revision or changed STEP hash refreshes geometry and rejects a superseded preview", async () => {
  const h = harness();
  const first = h.controller.accept(job());
  const second = h.controller.accept(job("A", 2));
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "old" });
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "new" });
  await Promise.all([first, second]);
  const changed = h.controller.accept(
    job("A", 2, { artifacts: { "assembly.step": { sha256: "replaced" } } }),
  );
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "hash-change" });
  await changed;
  assert.deepEqual(h.draws, ["new", "hash-change"]);
});

test("a late initial URL read cannot override a host-selected job", async () => {
  const h = harness();
  const opening = h.controller.open("A");
  await h.controller.accept(job("B", 1, { state: "building" }));
  h.next("/api/jobs/A").resolve(job("A"));
  await opening;
  assert.equal(h.controller.state.job.id, "B");
  assert.equal(h.pending.length, 0);
});

test("same-geometry host updates share one in-flight preview and dispose invalidates all work", async () => {
  const h = harness();
  const first = h.controller.accept(job());
  const second = h.controller.accept(job("A", 1, { context_revision: 3 }));
  assert.equal(h.pending.length, 1);
  h.controller.dispose();
  h.next("/api/jobs/A/artifacts/preview.json").resolve({ id: "late" });
  await Promise.all([first, second]);
  assert.deepEqual(h.draws, []);
  assert.equal(h.timers.size, 0);
});
