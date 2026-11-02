import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import * as THREE from "three";
import { toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";

const source = fs.readFileSync(
  new URL("../src/main.js", import.meta.url),
  "utf8",
);
function rendererHarness() {
  const parts = new THREE.Group();
  const camera = new THREE.PerspectiveCamera();
  camera.up.set(0, 0, 1);
  const ctx = {
    THREE,
    toCreasedNormals,
    parts,
    camera,
    applyView() {},
    fit() {},
  };
  vm.createContext(ctx);
  vm.runInContext(
    source.slice(
      source.indexOf("function disposeParts()"),
      source.indexOf("function fit("),
    ) +
      source.slice(
        source.indexOf("function drawPreview("),
        source.indexOf("let pointerStart = null;"),
      ),
    ctx,
  );
  return ctx;
}

test("nested native vertices and triangles use the row-major transform with Z up and dispose old meshes", () => {
  const ctx = rendererHarness();
  const { parts, camera } = ctx;
  ctx.drawPreview({
    parts: [
      {
        id: "occurrence",
        definition_id: "physical-part",
        vertices: [
          [0, 0, 0],
          [1, 0, 0],
          [0, 1, 0],
        ],
        triangles: [[0, 1, 2]],
        transform: [
          [1, 0, 0, 12],
          [0, 1, 0, -4],
          [0, 0, 1, 8],
          [0, 0, 0, 1],
        ],
      },
    ],
  });
  const mesh = parts.children[0];
  assert.deepEqual(mesh.position.toArray(), [12, -4, 8]);
  assert.equal(mesh.geometry.getAttribute("position").count, 3);
  assert.deepEqual(
    [...mesh.geometry.attributes.position.array],
    [0, 0, 0, 1, 0, 0, 0, 1, 0],
  );
  assert.equal(mesh.userData.id, "occurrence");
  assert.equal(mesh.userData.definition_id, "physical-part");
  assert.deepEqual(camera.up.toArray(), [0, 0, 1]);
  let geometryDisposed = false,
    materialDisposed = false;
  mesh.geometry.addEventListener("dispose", () => {
    geometryDisposed = true;
  });
  mesh.material.addEventListener("dispose", () => {
    materialDisposed = true;
  });
  ctx.drawPreview({ parts: [] });
  assert.equal(parts.children.length, 0);
  assert.equal(geometryDisposed, true);
  assert.equal(materialDisposed, true);
});

test("shared box corners retain planar normals without moving the CAD preview", () => {
  const ctx = rendererHarness();
  const vertices = [
    [-1, -1, -1],
    [1, -1, -1],
    [1, 1, -1],
    [-1, 1, -1],
    [-1, -1, 1],
    [1, -1, 1],
    [1, 1, 1],
    [-1, 1, 1],
  ];
  const triangles = [
    [0, 2, 1],
    [0, 3, 2],
    [4, 5, 6],
    [4, 6, 7],
    [0, 1, 5],
    [0, 5, 4],
    [3, 7, 6],
    [3, 6, 2],
    [0, 4, 7],
    [0, 7, 3],
    [1, 2, 6],
    [1, 6, 5],
  ];
  ctx.drawPreview({ parts: [{ id: "box", vertices, triangles }] });
  const geometry = ctx.parts.children[0].geometry;
  const positions = geometry.attributes.position;
  const normals = geometry.attributes.normal;
  const a = new THREE.Vector3(),
    b = new THREE.Vector3(),
    c = new THREE.Vector3();
  for (let i = 0; i < positions.count; i += 3) {
    a.fromBufferAttribute(positions, i);
    b.fromBufferAttribute(positions, i + 1);
    c.fromBufferAttribute(positions, i + 2);
    const faceNormal = b.sub(a).cross(c.sub(a)).normalize();
    for (let j = 0; j < 3; j++) {
      assert.ok(
        faceNormal.dot(
          new THREE.Vector3().fromBufferAttribute(normals, i + j),
        ) > 0.99999,
      );
      assert.deepEqual(
        new THREE.Vector3().fromBufferAttribute(positions, i + j).toArray(),
        vertices[triangles[i / 3][j]],
      );
    }
  }
});

test("round cylinder walls stay smooth while their flat caps keep hard edges", () => {
  const ctx = rendererHarness();
  const cylinder = new THREE.CylinderGeometry(1, 1, 2, 32);
  const vertices = Array.from(
    { length: cylinder.attributes.position.count },
    (_, i) =>
      new THREE.Vector3()
        .fromBufferAttribute(cylinder.attributes.position, i)
        .toArray(),
  );
  const indices = [...cylinder.index.array];
  const triangles = Array.from({ length: indices.length / 3 }, (_, i) =>
    indices.slice(i * 3, i * 3 + 3),
  );
  ctx.drawPreview({ parts: [{ id: "cylinder", vertices, triangles }] });
  const geometry = ctx.parts.children[0].geometry;
  let wallVertices = 0,
    capVertices = 0;
  for (let i = 0; i < geometry.attributes.position.count; i++) {
    const point = new THREE.Vector3().fromBufferAttribute(
      geometry.attributes.position,
      i,
    );
    const normal = new THREE.Vector3().fromBufferAttribute(
      geometry.attributes.normal,
      i,
    );
    if (Math.abs(normal.y) > 0.99) {
      capVertices++;
      assert.ok(Math.abs(normal.y - Math.sign(point.y)) < 1e-5);
    } else {
      wallVertices++;
      const radial = point.setY(0).normalize();
      assert.ok(radial.dot(normal) > 0.995);
    }
  }
  assert.ok(wallVertices > 0 && capVertices > 0);
  cylinder.dispose();
});

test("viewer surface has one final STEP action and no model-writing UI", () => {
  assert.equal((source.match(/id="download-step"/g) || []).length, 1);
  assert.doesNotMatch(
    source,
    /<form|<textarea|type="file"|sendMessage|native-edits|jsonOptions|method:\s*"(?:POST|PUT|PATCH|DELETE)"/,
  );
  assert.match(source, /artifactPath\(job.id, "assembly.step"\)/);
});
