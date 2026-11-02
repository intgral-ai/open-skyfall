import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../src/main.js", import.meta.url),
  "utf8",
);
const code = source.slice(
  source.indexOf("let pointerStart = null;"),
  source.indexOf('$("#fit").onclick'),
);
function setup(
  hits = [{ object: { visible: true, userData: { id: "plate-1" } } }],
) {
  const handlers = {},
    selections = [];
  const ctx = {
    renderer: {
      domElement: {
        addEventListener: (name, handler) => {
          handlers[name] = handler;
        },
        getBoundingClientRect: () => ({
          left: 0,
          top: 0,
          width: 100,
          height: 100,
        }),
      },
    },
    mouse: { set() {} },
    camera: {},
    parts: { children: [] },
    raycaster: {
      setFromCamera() {},
      intersectObjects: () => hits,
    },
    selectOccurrence: (id) => selections.push(id),
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return { handlers, selections };
}

test("a primary click selects the visible occurrence", () => {
  const { handlers, selections } = setup();
  handlers.pointerdown({
    button: 0,
    isPrimary: true,
    clientX: 20,
    clientY: 20,
  });
  handlers.click({ button: 0, clientX: 21, clientY: 21 });
  assert.deepEqual(selections, ["plate-1"]);
});

test("a primary blank-canvas click clears selection even when only hidden parts intersect", () => {
  for (const hits of [
    [],
    [{ object: { visible: false, userData: { id: "hidden" } } }],
  ]) {
    const { handlers, selections } = setup(hits);
    handlers.pointerdown({
      button: 0,
      isPrimary: true,
      clientX: 20,
      clientY: 20,
    });
    handlers.click({ button: 0, clientX: 20, clientY: 20 });
    assert.deepEqual(selections, [null]);
  }
});

test("primary modifier-pan gestures do not change selection on the model or blank canvas", () => {
  for (const hits of [
    [],
    [{ object: { visible: true, userData: { id: "plate-1" } } }],
  ]) {
    const { handlers, selections } = setup(hits);
    for (const modifier of ["shiftKey", "ctrlKey", "metaKey"]) {
      handlers.pointerdown({
        button: 0,
        isPrimary: true,
        clientX: 20,
        clientY: 20,
        [modifier]: true,
      });
      handlers.click({ button: 0, clientX: 20, clientY: 20, [modifier]: true });
    }
    assert.deepEqual(selections, []);
  }
});

test("orbit, pan, secondary pointers and cancelled gestures do not select", () => {
  const { handlers, selections } = setup();
  handlers.pointerdown({
    button: 0,
    isPrimary: true,
    clientX: 20,
    clientY: 20,
  });
  handlers.click({ button: 0, clientX: 40, clientY: 35 });
  handlers.pointerdown({
    button: 2,
    isPrimary: true,
    clientX: 20,
    clientY: 20,
  });
  handlers.click({ button: 2, clientX: 20, clientY: 20 });
  handlers.pointerdown({
    button: 0,
    isPrimary: false,
    clientX: 20,
    clientY: 20,
  });
  handlers.click({ button: 0, clientX: 20, clientY: 20 });
  handlers.pointerdown({
    button: 0,
    isPrimary: true,
    clientX: 20,
    clientY: 20,
  });
  handlers.pointercancel();
  handlers.click({ button: 0, clientX: 20, clientY: 20 });
  assert.deepEqual(selections, []);
});
