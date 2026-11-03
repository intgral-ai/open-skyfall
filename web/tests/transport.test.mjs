import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const code = fs
  .readFileSync(new URL("../src/transport.js", import.meta.url), "utf8")
  .replace(/^import .*;\n/gm, "")
  .replace(/^export /gm, "");
function setup({ embedded = true, outcome = {}, deferred = false } = {}) {
  const calls = [],
    events = [],
    revoked = [],
    handlers = {},
    timers = [],
    nativeClicks = [];
  let host;
  let resolve;
  const pending = deferred
    ? new Promise((r) => {
        resolve = r;
      })
    : Promise.resolve(outcome);
  const window = { dispatchEvent: (event) => events.push(event) };
  window.parent = embedded ? {} : window;
  const ctx = {
    window,
    Uint8Array,
    Blob,
    atob,
    CustomEvent: class {
      constructor(type, data) {
        this.type = type;
        this.detail = data.detail;
      }
    },
    URL: {
      createObjectURL: () => "blob:native-step",
      revokeObjectURL: (url) => revoked.push(url),
    },
    setTimeout: (fn) => timers.push(fn),
    document: {
      addEventListener: (name, fn) => {
        handlers[name] = fn;
      },
      removeEventListener: (name) => {
        delete handlers[name];
      },
      createElement: () => {
        const anchor = {
          getAttribute: (name) => anchor[name],
          click() {
            nativeClicks.push(anchor.href);
            handlers.click?.({
              target: { closest: () => anchor },
              preventDefault() {
                throw new Error("Blob anchor was intercepted");
              },
            });
          },
        };
        return anchor;
      },
    },
    App: class {
      constructor() {
        host = this;
      }
      async connect() {}
      async callServerTool(payload) {
        calls.push(payload);
        return pending;
      }
    },
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return {
    ctx,
    calls,
    events,
    revoked,
    handlers,
    timers,
    nativeClicks,
    resolve,
    get host() {
      return host;
    },
  };
}
function link(href) {
  const attrs = new Map([["href", href]]);
  return {
    getAttribute: (name) => attrs.get(name),
    setAttribute: (name, value) => attrs.set(name, value),
    removeAttribute: (name) => attrs.delete(name),
  };
}
function click(h, target) {
  let prevented = false;
  const promise = h.handlers.click({
    target: { closest: () => target },
    preventDefault() {
      prevented = true;
    },
  });
  return {
    promise,
    get prevented() {
      return prevented;
    },
  };
}

test("host tool results with a job or nested job are forwarded to the viewer", async () => {
  const h = setup();
  for (const data of [
    { id: "A", revision: 1 },
    { job: { id: "B", revision: 2 } },
  ])
    h.host.ontoolresult({ structuredContent: data });
  assert.deepEqual(
    h.events.map((event) => event.type),
    ["assembly:job", "assembly:job"],
  );
  assert.equal(h.events[1].detail.job.id, "B");
});

test("browser reads fall through and host requests are GET only", async () => {
  const browser = setup({ embedded: false });
  assert.equal(await browser.ctx.hostRequest("/api/jobs/A"), null);
  const h = setup({ outcome: { structuredContent: { id: "A" } } });
  assert.equal((await h.ctx.hostRequest("/api/jobs/A")).id, "A");
  assert.equal(h.calls[0].arguments.method, "GET");
  for (const method of ["POST", "PUT", "PATCH", "DELETE"])
    await assert.rejects(
      h.ctx.hostRequest("/api/jobs/A", { method }),
      /only reads/,
    );
  assert.equal(h.calls.length, 1);
});

test("workflow writes have a separate narrow POST transport", async () => {
  const h = setup({
    outcome: { structuredContent: { id: "project1", workflow_revision: 2 } },
  });
  const payload = { revision: 1, workflow_revision: 1, confirmed: true };
  assert.equal(
    (
      await h.ctx.hostWorkflowAction(
        "/api/decompositions/project1/workflow/approve",
        payload,
      )
    ).workflow_revision,
    2,
  );
  assert.equal(h.calls[0].arguments.method, "POST");
  assert.equal(h.calls[0].arguments.payload, payload);
  await h.ctx.hostWorkflowAction("/api/decompositions", { workflow: true });
  await h.ctx.hostWorkflowAction(
    "/api/decompositions/project1/workflow/decompose-example",
    payload,
  );
  for (const path of [
    "/api/jobs/A",
    "https://other/api/decompositions",
    "/api/decompositions/A/workflow/delete",
    "/api/decompositions/A/../workflow/approve",
    "/api/decompositions/A/workflow/approve?x=1",
  ])
    await assert.rejects(
      h.ctx.hostWorkflowAction(path, payload),
      /Unsupported/,
    );
  assert.equal(h.calls.length, 3);
  await assert.rejects(
    h.ctx.hostRequest("/api/decompositions/A", { method: "POST" }),
    /only reads/,
  );
});

test("standalone handoff falls back honestly and embedded handoff uses the installed user message shape", async () => {
  const standalone = setup({ embedded: false });
  assert.equal(
    await standalone.ctx.hostIterationMessage("selected scope"),
    false,
  );
  const h = setup();
  const messages = [];
  h.host.sendMessage = async (message) => {
    messages.push(message);
    return {};
  };
  assert.equal(await h.ctx.hostIterationMessage("Ask me what to change"), true);
  assert.equal(messages[0].role, "user");
  assert.equal(messages[0].content[0].text, "Ask me what to change");
  h.host.sendMessage = async () => ({ isError: true });
  await assert.rejects(
    h.ctx.hostIterationMessage("selection"),
    /could not accept/,
  );
});

test("only relative final STEP download URLs are intercepted", async () => {
  const h = setup();
  h.ctx.installHostDownloads();
  for (const path of [
    "blob:native-step",
    "https://example.com/api/jobs/A/artifacts/assembly.step",
    "/api/jobs/A/bundle",
    "/api/jobs/A/artifacts/source.py",
    "/api/jobs/A/artifacts/assembly.step?other",
    "//evil.example/api/jobs/A/artifacts/assembly.step",
  ]) {
    const result = click(h, link(path));
    await result.promise;
    assert.equal(result.prevented, false, path);
  }
  assert.equal(h.calls.length, 0);
});

test("host STEP download suppresses duplicates, releases its URL and never intercepts the blob anchor", async () => {
  const h = setup({ deferred: true });
  h.ctx.installHostDownloads();
  const target = link("/api/jobs/A/artifacts/assembly.step");
  const first = click(h, target);
  await Promise.resolve();
  const second = click(h, target);
  await second.promise;
  assert.equal(target.getAttribute("aria-busy"), "true");
  h.resolve({
    structuredContent: {
      data_base64: btoa("ISO-10303-21;"),
      mime_type: "application/step",
      filename: "assembly.step",
    },
  });
  await first.promise;
  assert.equal(first.prevented, true);
  assert.equal(second.prevented, true);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.nativeClicks, ["blob:native-step"]);
  assert.equal(target.getAttribute("aria-busy"), undefined);
  h.timers.forEach((fn) => fn());
  assert.deepEqual(h.revoked, ["blob:native-step"]);
  assert.deepEqual(
    h.events
      .filter((event) => event.type === "assembly:download")
      .map((event) => event.detail.busy),
    [true, false],
  );
});

test("server download rejection reports the error and re-enables the final action", async () => {
  const h = setup({
    outcome: {
      isError: true,
      content: [{ type: "text", text: "STEP hash validation failed" }],
    },
  });
  h.ctx.installHostDownloads();
  const target = link("/api/jobs/A/artifacts/assembly.step");
  await click(h, target).promise;
  assert.equal(target.getAttribute("aria-disabled"), undefined);
  assert.deepEqual(h.nativeClicks, []);
  assert.match(
    h.events.find((event) => event.type === "assembly:error").detail.message,
    /hash validation/,
  );
});
