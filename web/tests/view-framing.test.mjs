import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const source = fs.readFileSync(
  new URL("../src/main.js", import.meta.url),
  "utf8",
);
function setup(width, height, size = [200, 200, 20]) {
  const camera = new THREE.PerspectiveCamera(35, width / height, 0.01, 100000);
  camera.up.set(0, 0, 1);
  const parts = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size));
  mesh.position.set(120, -40, 60);
  mesh.rotation.set(0.2, -0.35, 0.6);
  parts.add(mesh);
  const controls = new OrbitControls(camera);
  controls.enableDamping = true;
  const viewer = { clientWidth: width, clientHeight: height };
  const ctx = {
    THREE,
    camera,
    controls,
    parts,
    grid: new THREE.Group(),
    renderer: { setSize() {} },
    $: () => viewer,
  };
  vm.createContext(ctx);
  vm.runInContext(
    source.slice(
      source.indexOf("function resize()"),
      source.indexOf("const resizeObserver"),
    ) +
      source.slice(
        source.indexOf("function fit("),
        source.indexOf("function applyView()"),
      ),
    ctx,
  );
  return { ctx, camera, controls, parts, viewer };
}

function assertFramed(camera, parts) {
  camera.updateMatrixWorld();
  const box = new THREE.Box3().setFromObject(parts);
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        const p = new THREE.Vector3(x, y, z).project(camera);
        assert.ok(
          Math.abs(p.x) <= 0.95 && Math.abs(p.y) <= 0.95,
          `box corner projects outside padded view at (${p.x.toFixed(3)}, ${p.y.toFixed(3)})`,
        );
        assert.ok(p.z > -1 && p.z < 1, "box corner is clipped by camera depth");
      }
    }
  }
}

for (const [width, height] of [
  [1440, 852],
  [430, 802],
  [360, 640],
]) {
  test(`Fit frames actual box corners with padding at ${width}x${height}`, () => {
    const { ctx, camera, parts } = setup(width, height);
    ctx.fit();
    assertFramed(camera, parts);
  });
}

test("Fit frames a tall model with a changed perspective FOV and zoom", () => {
  const { ctx, camera, parts } = setup(1440, 852, [20, 40, 500]);
  camera.fov = 50;
  camera.zoom = 1.5;
  ctx.fit();
  assertFramed(camera, parts);
});

test("viewport resize keeps the model in frame and preserves the orbit direction", () => {
  const { ctx, camera, controls, parts, viewer } = setup(1440, 852);
  ctx.fit();
  camera.position.copy(controls.target).add(new THREE.Vector3(-400, 300, 200));
  controls.update();
  const direction = camera.position.clone().sub(controls.target).normalize();
  for (const [width, height] of [
    [430, 802],
    [1440, 852],
  ]) {
    viewer.clientWidth = width;
    viewer.clientHeight = height;
    ctx.resize();
    assertFramed(camera, parts);
    assert.ok(
      direction.distanceTo(
        camera.position.clone().sub(controls.target).normalize(),
      ) < 1e-10,
      "resizing changed the user's orbit direction",
    );
  }
});
