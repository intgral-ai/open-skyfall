import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";
import {
  hostRequest,
  hostWorkflowAction,
  hostIterationMessage,
} from "./transport.js";
import {
  intakePayload,
  selectionWorkflow,
  buildArtifactPath,
  createWorkflowActions,
  verifyNativePreview,
} from "./decomposition-workflow.js";
import { createDecompositionSession } from "./decomposition-session.js";
import {
  explainSelection,
  containedImageRect,
  hostDownload,
} from "./decomposition-explanation.js";
import {
  hierarchy,
  nodeColor,
  partVisible,
  explodeOffsets,
  followExplosion,
} from "./decomposition-state.js";
import "./decomposition.css";
import "./decomposition-theme.css";
import {
  changeSelection,
  selectionContains,
  selectionContext,
  selectionMessage,
} from "./decomposition-selection.js";
import { mountProjectPicker } from "./project-picker.js";
import {
  continuationBinding,
  createContinuationActions,
} from "./decomposition-continue.js";
import {
  workflowProgress,
  pieceReferenceURL,
  currentCheckReport,
  checkMessage,
} from "./decomposition-piece.js";

const paths = {
  cube: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
  fit: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
  focus:
    '<circle cx="12" cy="12" r="6"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  reset: '<path d="M4 9a8 8 0 1 1 0 6M4 3v6h6"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  image:
    '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1"/><path d="m3 16 5-5 4 4 4-6 5 7"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7"/>',
};
const icon = (name) =>
  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

export async function initDecomposition() {
  const $ = (selector) => document.querySelector(selector);
  const embedded = window.parent !== window;
  const entry = new URL(location.href);
  let entryPart = entry.searchParams.get("part");
  const entryProject = entry.searchParams.get("project");
  let inspectorTab =
    entry.searchParams.get("view") === "reference" ? "reference" : "details";
  let project = null,
    preview = null,
    conceptPreview = null,
    nativeBuildId = null,
    nativeTicket = 0,
    tree = null,
    depth = 2,
    selected = null;
  let selectedIds = [];
  let projectPicker, continuationActions, continuationSnapshot;
  let isolated = false,
    amount = 0,
    displayedAmount = 0,
    hidden = new Set(),
    collapsed = new Set();
  let frame,
    imageUrl,
    lastFrame = 0;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  const compact = matchMedia("(max-width: 1000px)");
  const meshes = new Map();
  document.title = "CAD workspace";
  document.querySelector('meta[name="theme-color"]').content = "#25272b";
  $("#app").innerHTML = `
    <div class="d-app">
      <header class="d-header">
        <a class="d-brand" href="/" aria-label="Home">${icon("layers")}<span>Research preview</span></a>
        <span class="d-divider"></span><strong id="d-name">Part workspace</strong>
        <button id="d-new">New source</button>
        <div class="d-project-picker"><button id="d-project-switch" aria-label="Open project" aria-haspopup="dialog" aria-expanded="false" aria-controls="d-project-menu">${icon("cube")}<span>Open project</span>${icon("arrow")}</button><div id="d-project-menu" class="d-project-menu" popover role="dialog" aria-label="Open project"><input id="d-project-search" type="search" aria-label="Search projects" placeholder="Search projects" autocomplete="off"><div id="d-project-options"></div><footer>Saved on this computer</footer></div></div>
        <button id="d-source-toggle" aria-label="Close inspector" aria-controls="d-reference-panel" aria-pressed="true">${icon("image")}<span>Inspector</span></button>
      </header>
      <div class="d-subheader"><span><i class="d-dot"></i><span id="d-status" role="status">Ready for an image</span></span><span id="d-revision">Concept decomposition</span></div>
      <ol id="d-phases" class="d-phases" aria-label="Object to CAD workflow"></ol>
      <main class="d-workspace">
        <aside id="d-sidebar" class="d-sidebar" aria-label="Assembly structure">
          <div class="d-panel-title"><span>Structure</span><span id="d-count">—</span><button id="d-sidebar-close" aria-label="Close structure">${icon("close")}</button></div>
          <div id="d-levels" class="d-levels" role="group" aria-label="Decomposition depth"></div>
          <nav id="d-tree" aria-label="Part hierarchy"><p class="d-muted d-padding">Physical parts and assemblies appear here.</p></nav>
          <div class="d-sidebar-note"><span>Click a part to inspect.<br>Use checkboxes or ⌘ / Ctrl-click for multiple parts.</span></div>
        </aside>
        <section class="d-stage" aria-label="Model inspection">
          <div id="d-viewport" tabindex="0" aria-label="3D decomposition. Drag to orbit, shift-drag to pan, scroll to zoom. F fits the model; Escape clears selection."></div>
          <div class="d-stage-label"><button id="d-structure-toggle" aria-label="Open structure" aria-controls="d-sidebar" aria-expanded="false">${icon("layers")}<span>Structure</span></button><span id="d-breadcrumb">Image → structure → parts</span><span id="d-scene-meta"></span></div>
          <div id="d-empty" class="d-empty">
            <div class="d-empty-symbol">${icon("layers")}</div>
            <h1>See how it comes apart.</h1><p>Bring an image or describe an object.<br>Review its proposal, refine each part in Codex, then confirm CAD.</p>
            <div id="d-proposal-overview" class="d-proposal-overview" hidden></div>
            <button id="d-start" class="d-primary">Start with your source ${icon("arrow")}</button>
            <button id="d-example">Explore the synthetic inspection rig</button><small>Original designed example · no parts pre-confirmed</small>
          </div>
          <div id="d-tools" class="d-tools" role="toolbar" aria-label="Model tools" hidden>
            <button id="d-fit" aria-label="Fit model" title="Fit model (F)">${icon("fit")}<span>Fit</span></button>
            <button id="d-focus" aria-label="Focus selection" disabled>${icon("focus")}<span>Focus</span></button>
            <button id="d-isolate" aria-label="Isolate selection" aria-pressed="false" disabled>${icon("cube")}<span>Isolate</span></button>
            <button id="d-hide" aria-label="Hide selection" disabled>${icon("eye")}<span>Hide</span></button>
            <span class="d-tool-divider"></span><button id="d-restore" aria-label="Restore original placements and visibility" title="Restore original placements and visibility">${icon("reset")}<span>Restore</span></button>
          </div>
          <div id="d-explode-panel" class="d-explode" hidden><label for="d-explode">Explode <output id="d-explode-value">0%</output></label><input id="d-explode" type="range" min="0" max="100" value="0" aria-label="Explode amount"><span>View offset only · placements preserved</span></div>
          <div class="d-stage-footer"><span id="d-selection">Z up · right-handed</span><span>Drag to orbit <b>·</b> Scroll to zoom</span></div>
          <div id="d-error" class="d-error" role="alert" hidden></div>
        </section>
        <aside id="d-reference-panel" class="d-reference" aria-label="Reference and selection">
          <div class="d-inspector-header"><span>Inspector</span><button id="d-inspector-close" aria-label="Close inspector">${icon("close")}</button></div><section id="d-selection-summary" class="d-selection-summary" aria-label="Selected parts" hidden><p id="d-selection-count"></p><ul id="d-selection-list"></ul><small id="d-selection-impact"></small><small id="d-selection-primary"></small><button id="d-multi-copy"></button></section>
          <section class="d-inspector"><h2 id="d-node-name">Select a part</h2><span id="d-node-kind" class="d-tag">Part workspace</span><details class="d-selection-note"><summary>Design note</summary><p id="d-node-note">Choose a part in the model or structure to inspect its references and checks.</p></details><code id="d-node-id"></code><div class="d-piece-actions"><button id="d-open-reference" disabled>${icon("image")}Reference</button><button id="d-open-checks" disabled>${icon("check")}Checks</button></div><button id="d-copy" disabled>${icon("copy")}Iterate in Codex</button><p id="d-handoff-mode" class="d-handoff-mode"></p><details id="d-handoff-context-panel" hidden><summary>Selection context</summary><pre id="d-handoff-context"></pre></details></section>
          <div class="d-inspector-tabs" role="tablist" aria-label="Part inspection"><button id="d-tab-details" role="tab" data-tab="details" aria-controls="d-pane-details">Details</button><button id="d-tab-reference" role="tab" data-tab="reference" aria-controls="d-pane-reference">Reference</button><button id="d-tab-checks" role="tab" data-tab="checks" aria-controls="d-pane-checks">Checks</button></div>
          <section id="d-continuation-panel" class="d-workflow-section" aria-label="Continue in Codex" hidden><p id="d-continuation-status" role="status"></p><details><summary>Continue prompt</summary><textarea id="d-continuation-text" readonly rows="8" aria-label="Continue prompt for Codex"></textarea></details><button id="d-copy-continuation">Copy prompt again</button></section>
          <section id="d-proposal" class="d-workflow-section" hidden></section>
          <div id="d-pane-reference" role="tabpanel" aria-labelledby="d-tab-reference">
          <div class="d-panel-title"><span id="d-reference-title">Source reference</span><span id="d-source-badge">Image</span></div>
          <a id="d-reference-separate" class="d-reference-separate" target="_blank" rel="noopener" hidden>Open this part separately ${icon("external")}</a>
          <div class="d-image-wrap"><div id="d-image-slot"></div><svg id="d-source-regions" aria-label="Selected source observations"></svg><span id="d-image-empty">${icon("image")}<span>Your image stays beside the model.</span></span></div>
          <div class="d-reference-meta"><span id="d-rights">Input provenance retained</span><code id="d-hash"></code></div>
          <section id="d-piece-reference" class="d-workflow-section"></section>
          <details id="d-brief" class="d-workflow-section" hidden><summary>Literal design brief</summary><p id="d-brief-text"></p></details>
          </div>
          <div id="d-pane-checks" role="tabpanel" aria-labelledby="d-tab-checks"><section id="d-piece-checks" class="d-workflow-section" aria-live="polite"></section></div>
          <div id="d-pane-details" role="tabpanel" aria-labelledby="d-tab-details">
          <section id="d-review" class="d-workflow-section" aria-label="Selected scope review" hidden></section>
          <section id="d-native" class="d-workflow-section" aria-label="Current native CAD" hidden></section>
          <section class="d-explanation" aria-label="Decomposition explanation"><p id="d-coverage" role="status">Explanation awaits an accepted plan.</p><div id="d-node-explanation"></div><details id="d-trace-panel"><summary>Executed construction trace</summary><div id="d-trace"></div></details><details><summary>Checks by scope</summary><p class="d-check-note">Each result applies only to its named scope. Documented bases do not establish their truth. Mesh checks do not establish source fidelity, native CAD, collision freedom, or manufacturing suitability.</p><ul id="d-checks"></ul></details></section>
          <details class="d-assumptions"><summary>Assumptions & scale</summary><p id="d-scale">Scale and hidden geometry need evidence.</p><ul id="d-assumptions"></ul></details>
          <section id="d-downloads" class="d-downloads" aria-label="Accepted revision downloads" hidden><h3>Accepted program</h3><a id="d-program-download" download="program.json">Download program JSON</a><a id="d-bundle-download" download="bundle.zip">Download replay bundle</a><p id="d-program-binding"></p></section>
          <p class="d-disclaimer">Concept geometry. CAD accuracy and manufacturing suitability are unverified.</p>
          </div>
        </aside>
      </main>
      <dialog id="d-intake" class="d-intake"><form id="d-intake-form"><div class="d-form-heading"><div><h2>Start with what you know.</h2></div><button type="button" id="d-intake-close" aria-label="Close source form">×</button></div><label>Project name<input name="name" maxlength="100" placeholder="Bench inspection fixture"></label><label>Reference image <span>Optional for a written brief</span><input name="image" type="file" accept="image/png,image/jpeg,image/webp"></label><label>Describe the object<textarea name="description" rows="4" placeholder="What it does, known dimensions, visible features, and what needs to remain uncertain."></textarea></label><label>Source rights<input name="rights" required maxlength="500" placeholder="For example, my original photograph or design"></label><p>Codex authors a proposal first. Your approval is required before geometry, and each CAD scope needs a separate confirmation.</p><button type="submit" class="d-primary">Save source & continue in Codex</button><p id="d-intake-error" role="alert" hidden></p></form></dialog>
    </div>`;

  for (const button of document.querySelectorAll(".d-tools button")) {
    button.dataset.tooltip = button.title || button.getAttribute("aria-label");
    button.removeAttribute("title");
  }

  async function api(path) {
    const host = await hostRequest(path);
    if (host !== null) return host;
    const response = await fetch(path);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : `Request failed (${response.status})`,
      );
    }
    return response.json();
  }
  async function action(path, payload) {
    const host = await hostWorkflowAction(path, payload);
    if (host !== null) return host;
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : `Workflow action failed (${response.status})`,
      );
    return data;
  }
  function error(message) {
    $("#d-error").textContent = message;
    $("#d-error").hidden = !message;
  }
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  } catch {
    error(
      "3D rendering is unavailable in this browser. Enable WebGL and reopen the viewer.",
    );
    return;
  }
  const viewport = $("#d-viewport");
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setClearColor("#25272b");
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.16;
  viewport.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-4, 4, 4, -4, 0.01, 200);
  camera.up.set(0, 0, 1);
  camera.position.set(8, -8, 6.53);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 0.5;
  controls.maxDistance = 80;
  controls.minZoom = 0.15;
  controls.maxZoom = 40;
  scene.add(new THREE.HemisphereLight(0xffffff, 0xc7d5e3, 1.12));
  const key = new THREE.DirectionalLight(0xffffff, 1.16);
  key.position.set(-4, -6, 9);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, {
    left: -8,
    right: 8,
    top: 8,
    bottom: -8,
    near: 0.1,
    far: 30,
  });
  key.shadow.bias = -0.0005;
  key.shadow.normalBias = 0.015;
  scene.add(key);
  scene.add(new THREE.AmbientLight(0xffffff, 0.4));
  const fill = new THREE.SpotLight(0xf4fbff, 0.52, 0, Math.PI / 3, 0.8, 0);
  fill.position.set(5, 3, 5);
  scene.add(fill);
  const rim = new THREE.PointLight(0xffe2ba, 0.28, 0, 0);
  rim.position.set(-5, 4, 3);
  scene.add(rim);
  const root = new THREE.Group();
  scene.add(root);
  const observer = new ResizeObserver(() => {
    const width = viewport.clientWidth,
      height = viewport.clientHeight;
    if (!width || !height) return;
    camera.left = (-4 * width) / height;
    camera.right = (4 * width) / height;
    camera.setViewOffset(
      width,
      height,
      0,
      Math.min(140, height * 0.28) / 2,
      width,
      height,
    );
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
    if (meshes.size) fit();
  });
  observer.observe(viewport);
  const referenceObserver = new ResizeObserver(renderRegions);
  referenceObserver.observe($("#d-image-slot"));
  function animate(now = 0) {
    frame = requestAnimationFrame(animate);
    const dt = lastFrame ? (now - lastFrame) / 1000 : 1 / 60;
    lastFrame = now;
    if (!document.hidden) {
      if (displayedAmount !== amount) {
        displayedAmount = followExplosion(
          displayedAmount,
          amount,
          dt,
          still.matches,
        );
        applyView();
      }
      controls.update();
      renderer.render(scene, camera);
    }
  }
  animate();
  function disposeMeshes() {
    for (const mesh of meshes.values()) {
      mesh.geometry.dispose();
      mesh.material.dispose();
      for (const edge of mesh.children) {
        edge.geometry.dispose();
        edge.material.dispose();
      }
    }
    meshes.clear();
    root.clear();
  }
  function fit(selectionOnly = false) {
    const box = new THREE.Box3();
    for (const [id, mesh] of meshes)
      if (
        mesh.visible &&
        (!selectionOnly || selectionContains(tree, selectedIds, id))
      )
        box.expandByObject(mesh);
    if (box.isEmpty()) return;
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const usableHeight =
      1 - Math.min(140, viewport.clientHeight * 0.28) / viewport.clientHeight;
    camera.zoom =
      Math.min(
        (camera.right - camera.left) / 2,
        ((camera.top - camera.bottom) / 2) * usableHeight,
      ) / Math.max(sphere.radius * 1.35, 0.01);
    camera.updateProjectionMatrix();
    const direction = camera.position.clone().sub(controls.target).normalize();
    controls.target.copy(sphere.center);
    camera.position
      .copy(sphere.center)
      .addScaledVector(direction, Math.max(12, sphere.radius * 4));
    controls.update();
  }
  function draw(data) {
    disposeMeshes();
    const { center, scale } = data.normalization;
    root.scale.setScalar(scale);
    root.position.set(...center.map((v) => -v * scale));
    for (const part of data.parts) {
      const indexed = new THREE.BufferGeometry();
      indexed.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(part.vertices.flat(), 3),
      );
      indexed.setIndex(part.triangles.flat());
      const geometry = toCreasedNormals(indexed, Math.PI / 5);
      indexed.dispose();
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshPhysicalMaterial({
          color: nodeColor(part.id),
          roughness: 0.58,
          metalness: 0.02,
          clearcoat: 0.12,
          clearcoatRoughness: 0.42,
        }),
      );
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.userData.id = part.id;
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry, 35),
        new THREE.LineBasicMaterial({
          color: 0x18181b,
          transparent: true,
          opacity: 0.84,
        }),
      );
      mesh.add(edges);
      meshes.set(part.id, mesh);
      root.add(mesh);
    }
    root.updateMatrixWorld(true);
  }
  function applyView() {
    if (!tree || !preview) {
      $("#d-scene-meta").textContent = "No geometry yet";
      return;
    }
    const offsets = explodeOffsets(
      tree,
      preview.parts,
      depth,
      (displayedAmount / 100 / preview.normalization.scale) * 1.3,
    );
    for (const [id, mesh] of meshes) {
      mesh.position.set(...offsets.get(id));
      mesh.visible =
        partVisible(tree, id, null, false, hidden) &&
        (!isolated || selectionContains(tree, selectedIds, id));
      const active = selectionContains(tree, selectedIds, id);
      mesh.material.color.set(
        active ? "#7db8ef" : nodeColor(tree.atDepth(id, depth)),
      );
      mesh.material.emissive.set("#000000");
      mesh.material.transparent = false;
      mesh.material.opacity = 1;
      mesh.material.depthWrite = true;
      mesh.children[0].material.opacity = active ? 1 : 0.84;
      mesh.children[0].material.color.set(active ? "#76baff" : "#18181b");
    }
    $("#d-isolate").setAttribute("aria-pressed", String(isolated));
    $("#d-explode").value = amount;
    $("#d-explode-value").textContent = `${Math.round(displayedAmount)}%`;
    $("#d-scene-meta").textContent =
      `${nativeBuildId ? "Native tessellation" : "Concept geometry"} · ${[...meshes.values()].filter((m) => m.visible).length} / ${meshes.size} parts visible`;
  }
  function renderTree() {
    if (!tree) {
      $("#d-tree").textContent = "Waiting for a part plan.";
      $("#d-levels").replaceChildren();
      return;
    }
    function row(id) {
      const node = tree.byId.get(id),
        children = tree.children.get(id),
        level = tree.depths.get(id);
      if (level > depth) return "";
      const branch = children.length > 0 && level < depth;
      return `<li><div class="d-tree-row" style="--indent:${level * 14}px" data-selected="${selectedIds.includes(id)}">
        <button class="d-disclosure" data-collapse="${escape(id)}" ${branch ? `aria-expanded="${!collapsed.has(id)}" aria-label="${collapsed.has(id) ? "Expand" : "Collapse"} ${escape(node.label)}"` : 'disabled aria-hidden="true" tabindex="-1"'}>${branch ? icon("arrow") : ""}</button>
        <button class="d-select-part" data-select="${escape(id)}" aria-pressed="${selectedIds.includes(id)}" aria-label="${selectedIds.includes(id) ? "Remove" : "Add"} ${escape(node.label)} ${selectedIds.includes(id) ? "from" : "to"} selection">${selectedIds.includes(id) ? icon("check") : ""}</button><button class="d-node" data-node="${escape(id)}" aria-pressed="${selectedIds.includes(id)}" title="${escape(node.label)} · ${escape(node.evidence)}"><i style="background:${nodeColor(id)}"></i><span>${escape(node.label)}</span>${children.length ? `<small>${children.length}</small>` : ""}</button>
      </div>${branch && !collapsed.has(id) ? `<ul>${children.map(row).join("")}</ul>` : ""}</li>`;
    }
    $("#d-tree").innerHTML = `<ul>${row(tree.root)}</ul>`;
    $("#d-levels").innerHTML = Array.from(
      { length: tree.maxDepth + 1 },
      (_, i) =>
        `<button data-depth="${i}" aria-pressed="${depth === i}" title="Inspect hierarchy depth ${i}">${i === 0 ? "Whole" : i === tree.maxDepth ? "Parts" : `Level ${i}`}</button>`,
    ).join("");
  }
  function basisMarkup(basis) {
    return basis
      ? `<span class="d-basis-kind" data-kind="${escape(basis.kind)}">${escape(basis.kind)}</span> <span>${escape(basis.why)}</span><code class="d-basis-id">${escape(basis.id)}${basis.observations.length ? ` · ${basis.observations.map(escape).join(", ")}` : ""}</code>`
      : '<span class="d-muted">Basis not documented in this snapshot.</span>';
  }
  function parameterMarkup(rows) {
    return `<dl class="d-parameters">${rows.map((row) => `<div><dt>${escape(row.label)}</dt><dd><span class="d-parameter-value">${escape(row.value)} <small>${escape(row.unit)}</small></span><div>${basisMarkup(row.basis)}</div></dd></div>`).join("")}</dl>`;
  }
  function renderWorkflow() {
    if (
      continuationSnapshot &&
      continuationSnapshot !== continuationBinding(project)
    ) {
      continuationSnapshot = null;
      $("#d-continuation-panel").hidden = true;
      $("#d-continuation-text").value = "";
    }
    const flow = project?.workflow;
    $("#d-phases").innerHTML = workflowProgress(project)
      .map(
        (step) =>
          `<li data-state="${step.state}" ${step.current ? 'aria-current="step"' : ""} aria-label="Step ${step.number} of 5: ${step.label}, ${step.state}"><span class="d-step-number" aria-hidden="true">${step.state === "complete" ? icon("check") : step.number}</span><span class="d-step-label">${step.label}</span></li>`,
      )
      .join("");
    renderPiece();
    const brief = flow?.brief?.text || "";
    $("#d-brief").hidden = !brief;
    $("#d-brief-text").textContent = brief;
    $("#d-proposal").hidden = !flow || Boolean(project.plan);
    $("#d-review").hidden = !flow;
    $("#d-native").hidden = !flow;
    if (!flow) return;
    const busy =
      workflowActions.pending ||
      continuationActions?.pending ||
      flow.status === "building";
    const proposal = flow.proposal;
    const proposed = proposal?.data;
    $("#d-proposal-overview").hidden = Boolean(project.plan || !proposed);
    if (!project.plan && proposed) {
      $("#d-empty h1").textContent = proposal.approved
        ? "Ready to see the parts."
        : "Review the proposed structure.";
      $("#d-empty p").textContent = proposed.summary;
      $("#d-proposal-overview").textContent = proposed.parts
        .filter(
          (part) =>
            part.parent_id ===
            proposed.parts.find((item) => !item.parent_id)?.id,
        )
        .map((part) => part.label)
        .join(" · ");
      $("#d-start").textContent = !proposal.approved
        ? "Approve & continue to Decompose"
        : "Continue to Decompose in Codex";
      $("#d-start").disabled = busy;
    } else $("#d-start").disabled = busy;
    const approvedNext = project.plan
      ? ""
      : `${flow.example_case === "inspection-rig" ? "<p>Synthetic designed example. Codex can load its authored part plan. No part is confirmed.</p>" : ""}<button data-workflow="decompose" ${busy ? "disabled" : ""}>Continue to Decompose in Codex</button>`;
    $("#d-proposal").innerHTML = proposed
      ? `<p class="d-proposal-status">${proposal.approved ? "Proposal approved" : "Awaiting your review"}</p><h3>${escape(proposed.summary)}</h3><details ${!project.plan ? "open" : ""}><summary>${proposed.parts.length} proposed parts & assemblies</summary><ul>${proposed.parts.map((part) => `<li><strong>${escape(part.label)}</strong><p>${escape(part.description)}</p></li>`).join("")}</ul>${proposed.unknowns?.length ? `<h4>Still unknown</h4><ul>${proposed.unknowns.map((note) => `<li>${escape(note)}</li>`).join("")}</ul>` : ""}${proposed.manufacturing_notes?.length ? `<h4>Proposed manufacturing notes</h4><ul>${proposed.manufacturing_notes.map((note) => `<li>${escape(note)}</li>`).join("")}</ul>` : ""}</details>${proposal.approved ? approvedNext : `<p>Approve the proposed direction before Codex creates geometry. This does not confirm any CAD part.</p><button class="d-primary" data-workflow="approve-proposal" ${busy ? "disabled" : ""}>Approve & continue to Decompose</button>`}`
      : `<h3>Proposal</h3><p>Your source is saved. Codex can propose the physical structure and identify the unknowns before creating geometry.</p><button data-workflow="proposal" ${busy ? "disabled" : ""}>Continue to Proposal in Codex</button>`;
    const review = selectionWorkflow(project, selected);
    const scope = review.scope;
    const shared = new Set(
      review.parts.flatMap((part) => part.shared_occurrence_ids || []),
    );
    const manufacturing = [
      ...new Map(
        review.parts
          .filter((part) => part.manufacturing)
          .map((part) => [part.definition_id, part]),
      ).values(),
    ];
    $("#d-review").innerHTML = scope
      ? `<h3>${scope.approved_count} / ${scope.part_count} parts confirmed</h3><details><summary>Parts in this confirmation</summary><ul>${review.parts.map((part) => `<li>${escape(part.label)} <code>${escape(part.node_id)}</code> · ${part.approved ? "confirmed" : "needs confirmation"}</li>`).join("")}</ul><code class="d-digest">Review ${escape(scope.review_digest)}</code></details>${shared.size > review.parts.length ? `<p>Shared definitions affect ${shared.size} occurrences. A geometry change invalidates confirmation wherever that definition is used.</p>` : ""}${review.pendingRequests.length ? `<p class="d-pending">${review.pendingRequests.length} captured change request${review.pendingRequests.length > 1 ? "s" : ""} must be applied before confirming this scope.</p>` : ""}<button data-workflow="review" ${busy ? "disabled" : ""}>Continue review in Codex</button><button data-workflow="approve" class="d-primary" ${!review.canApprove || busy ? "disabled" : ""}>${scope.approved ? "Selected parts confirmed" : `Confirm ${scope.part_count} part${scope.part_count === 1 ? "" : "s"} & continue${project.plan?.units === "mm" ? " to CAD" : ""}`}</button><button data-workflow="cad" ${!review.canBuild || busy ? "disabled" : ""}>${flow.status === "building" ? "Building native CAD…" : "Continue to CAD in Codex"}</button><p>${project.plan?.units !== "mm" ? "A supported millimeter scale is required for CAD conversion." : "Confirmation binds these exact part shapes and placements. Native build checks are separate from source fidelity and manufacturing review."}</p>${manufacturing.length ? `<details><summary>Proposed manufacturing · ${manufacturing.length} definition${manufacturing.length === 1 ? "" : "s"}</summary>${manufacturing.map((part) => `<h4>${escape(part.label)}</h4><p>${escape(part.manufacturing.process)} · ${escape(part.manufacturing.material || "Material unspecified")}</p><ul>${[...(part.manufacturing.notes || []), ...(part.manufacturing.critical_features || []).map((note) => `Critical feature: ${note}`)].map((note) => `<li>${escape(note)}</li>`).join("")}</ul>`).join("")}<p>Design proposals. Factory requirements and tolerances remain unconfirmed.</p></details>` : ""}`
      : `<h3>Part review</h3><p>Select a physical part or group to inspect and confirm its exact scope.</p>${project.plan ? `<button data-workflow="review" ${busy ? "disabled" : ""}>Continue review in Codex</button>` : ""}`;
    const native = review.selectedBuild || review.assembly;
    const nativeLink = (build, file, label) =>
      `<a download="${escape(file.split("/").at(-1))}" href="${escape(buildArtifactPath(project.id, build.id, file))}">${label}</a>`;
    const completeNative = native?.id === review.assembly?.id;
    const nativeFiles = native
      ? Object.keys(native.artifacts || {})
          .filter((file) => /\.smb$/i.test(file) || file === "assembly.json")
          .map((file) =>
            nativeLink(
              native,
              file,
              file === "assembly.json"
                ? "Download physical assembly manifest"
                : `Native part · ${escape(file.split("/").at(-1))}`,
            ),
          )
          .join("")
      : "";
    $("#d-native").innerHTML =
      `<h3>Native CAD</h3>${flow.status === "building" ? '<p role="status">Building and reading STEP back. Current geometry remains available for inspection.</p>' : ""}${flow.error ? `<p class="d-pending">${escape(flow.error)}</p>` : ""}${
        native
          ? `<p>${completeNative ? "Complete assembly" : "Build containing the selected scope"} · <code>${escape(native.id)}</code></p><button data-workflow="native" aria-pressed="${Boolean(nativeBuildId)}">${nativeBuildId ? "Return to concept preview" : "Inspect native preview"}</button>${native.step_path && !completeNative ? nativeLink(native, native.step_path, "Download built scope STEP") : ""}<button data-workflow="verify" ${busy ? "disabled" : ""}>Continue STEP review in Codex</button><details><summary>Native files & validation</summary>${native.report_path ? nativeLink(native, native.report_path, "Download native validation report") : ""}${nativeFiles}</details>`
          : "<p>No verified current build for this selection. Confirm parts and build native CAD to enable downloads.</p>"
      }${review.assembly ? nativeLink(review.assembly, review.assembly.step_path, "Download complete assembled STEP") : "<p>Complete assembly STEP becomes available after every physical part is confirmed and the full assembly is built.</p>"}<p>STEP contains named placed bodies. The physical tree and transforms remain in the assembly manifest. Source fidelity and production manufacturability require separate review.</p>`;
  }
  function setInspectorTab(name, open = false) {
    inspectorTab = name;
    $("#d-reference-panel").dataset.tab = name;
    for (const tab of ["details", "reference", "checks"]) {
      const active = tab === name;
      $(`#d-tab-${tab}`).setAttribute("aria-selected", String(active));
      $(`#d-tab-${tab}`).tabIndex = active ? 0 : -1;
      $(`#d-pane-${tab}`).hidden = !active;
    }
    if (open) {
      setInspectorVisibility(true);
      $("#d-reference-panel").scrollTop = 0;
    }
    requestAnimationFrame(renderRegions);
  }
  function setInspectorVisibility(visible) {
    $("#d-reference-panel").hidden = !visible;
    $(".d-workspace").classList.toggle("d-no-reference", !visible);
    $("#d-source-toggle").setAttribute("aria-pressed", String(visible));
    $("#d-source-toggle").setAttribute(
      "aria-label",
      visible ? "Close inspector" : "Open inspector",
    );
    if (visible && compact.matches) {
      $("#d-sidebar").hidden = true;
      $("#d-structure-toggle").setAttribute("aria-expanded", "false");
    }
  }
  function renderPiece() {
    const node = tree?.byId.get(selected);
    const scope = project?.workflow?.scopes?.[selected];
    const criteria = project?.workflow?.checks?.[selected];
    const report = currentCheckReport(project, selected);
    const observations = project
      ? explainSelection(project, selected).observations
      : [];
    $("#d-open-reference").disabled = $("#d-open-checks").disabled = !node;
    $("#d-reference-title").textContent = node
      ? `${node.label} · reference`
      : "Project reference";
    const separate = $("#d-reference-separate");
    separate.hidden = !node || embedded;
    if (node && !embedded)
      separate.href = pieceReferenceURL(location.href, project.id, node.id);
    else separate.removeAttribute("href");
    $("#d-piece-reference").innerHTML = node
      ? `<h3>References for ${escape(node.label)}</h3>${observations.length ? observations.map((item) => `<article class="d-source-observation"><h4>${escape(item.statement)}</h4>${item.kind === "text" ? `<blockquote>${escape(item.quote)}</blockquote>` : "<p>Highlighted in the source image above.</p>"}<code>${escape(item.id)}</code></article>`).join("") : "<p>No source observation is bound to this piece. Its geometry needs an explicit design basis.</p>"}${criteria?.context?.text ? `<h3>Your check context</h3><p class="d-literal-context">${escape(criteria.context.text)}</p>` : ""}`
      : "<p>Select a piece to see its own source observations and check context.</p>";
    const busy = Boolean(
      project?.workflow?.status === "building" || workflowActions.pending,
    );
    const hasRules = Boolean(criteria?.rules?.length);
    const criterionIds = new Set(criteria?.rules?.map((rule) => rule.id) || []);
    const checks = report?.results || [];
    const primary = hasRules
      ? checks.filter((result) => criterionIds.has(result.id))
      : checks;
    const supporting = hasRules
      ? checks.filter((result) => !criterionIds.has(result.id))
      : [];
    const titles = {
      "source-program": "Source and program",
      "selected-meshes": "Part geometry",
      "native-readback": "Saved native CAD",
      "user-intent": "Full design intent",
      "source-fidelity": "Reference accuracy",
      manufacturing: "Manufacturing",
    };
    function resultMarkup(result) {
      const unit = result.unit || result.expected_unit || "";
      const limit =
        result.min != null && result.max != null
          ? `${result.min} to ${result.max}`
          : result.max != null
            ? `At most ${result.max}`
            : `At least ${result.min}`;
      return `<li><div><strong>${escape(titles[result.id] || result.id.replaceAll("-", " "))}</strong><span data-outcome="${escape(result.outcome)}">${escape(result.outcome)}</span></div>${result.kind === "parameter_range" ? `<dl class="d-check-measure"><div><dt>Actual</dt><dd>${result.actual == null ? "Unavailable" : `${escape(result.actual)} ${escape(unit)}`}</dd></div><div><dt>Required</dt><dd>${escape(limit)} ${escape(result.expected_unit || unit)}</dd></div></dl>` : ""}${result.quote ? `<blockquote>${escape(result.quote)}</blockquote>` : ""}<p>${escape(result.detail)}</p></li>`;
    }
    $("#d-piece-checks").innerHTML = node
      ? `<h3>Checks for ${escape(node.label)}</h3>${report ? `<div class="d-current-check-summary"><span data-outcome="${escape(report.outcome)}">${escape(report.outcome)}</span><span>${report.summary.pass} passed${report.summary.fail ? ` · ${report.summary.fail} failed` : ""}${report.summary.blocked ? ` · ${report.summary.blocked} blocked` : ""} · ${report.summary.unchecked} unchecked</span></div>` : ""}<p>${hasRules ? "Check your saved requirements against this exact piece." : "Check the saved source, program and part geometry. Define criteria in Codex to test your requirements."}</p><div class="d-check-actions"><button id="d-run-piece-check" class="d-primary" ${!scope || busy ? "disabled" : ""}>${busy ? "Working…" : hasRules ? "Run part checks" : "Run structural checks"}</button><button id="d-define-piece-check" ${!scope || busy ? "disabled" : ""}>${hasRules ? "Refine criteria in Codex" : "Define criteria in Codex"}</button></div>${report ? `<div class="d-check-report"><ul>${primary.map(resultMarkup).join("")}</ul>${supporting.length ? `<details><summary>Supporting checks · ${supporting.length}</summary><ul>${supporting.map(resultMarkup).join("")}</ul></details>` : ""}<details><summary>CI report · revision ${project.revision}</summary><pre>${escape(JSON.stringify(report, null, 2))}</pre></details></div>` : criteria?.report ? '<p class="d-check-stale">Previous results are out of date. Run checks for the current part and criteria.</p>' : '<p class="d-check-empty">No check run yet. Source fidelity and manufacturing remain unverified.</p>'}${criteria?.context ? `<details class="d-check-context"><summary>Your requirements · ${criteria.rules.length} criteria</summary><p class="d-literal-context">${escape(criteria.context.text)}</p></details>` : ""}`
      : "<h3>Part checks</h3><p>Select a piece to inspect its criteria and run checks.</p>";
    setInspectorTab(inspectorTab);
  }
  function renderExplanation() {
    if (!project) return;
    const info = explainSelection(project, selected);
    $("#d-coverage").textContent = info.complete
      ? `Explanation complete · ${info.coverage.parameter_count} parameter bases · revision ${project.revision}`
      : `Explanation incomplete · revision ${project.revision}. This snapshot does not contain complete bound evidence.`;
    $("#d-coverage").dataset.complete = String(info.complete);
    $("#d-node-explanation").innerHTML = selected
      ? `
      <h3>Why this ${info.definitionId ? "part" : "assembly"} exists</h3><div class="d-basis">${basisMarkup(info.rationale)}</div>
      <h3>Placement basis</h3><div class="d-basis">${basisMarkup(info.placement)}</div>
      <details><summary>Occurrence local pose</summary><p>Parent-relative position in authored units. Euler rotation in degrees. Viewer normalization and explode offsets do not change these values.</p>${parameterMarkup(info.nodePose)}</details>
      ${info.definitionId ? `<h3>Definition reuse</h3><p><code>${escape(info.definitionId)}</code> · ${info.occurrences.length} occurrence${info.occurrences.length === 1 ? "" : "s"}</p><ul class="d-occurrences">${info.occurrences.map((node) => `<li>${escape(node.label)} <code>${escape(node.id)}</code></li>`).join("")}</ul>` : ""}
      ${info.shapes.map((shape, i) => `<details class="d-shape" open><summary>${escape(shape.kind)} · ${escape(shape.id || `shape ${i + 1}`)}</summary><h3>Representation basis</h3><div class="d-basis">${basisMarkup(shape.basis)}</div><h3>Dimensions</h3>${parameterMarkup(shape.dimensions)}<details><summary>Shape local pose</summary><p>Relative to the reusable definition.</p>${parameterMarkup(shape.pose)}</details></details>`).join("")}
      <h3>Source observations</h3>${info.observations.length ? `<ol class="d-observations">${info.observations.map((observation) => `<li><code>${escape(observation.id)}</code><p>${escape(observation.statement)}</p>${observation.kind === "text" ? `<blockquote>${escape(observation.quote)}</blockquote>` : `<small>Normalized image region ${observation.region.map(escape).join(", ")}</small>`}</li>`).join("")}</ol>` : "<p>No source observation is documented for this selection. Assumed and unknown geometry may have no source observation.</p>"}
      `
      : "<p>Select a part or assembly to inspect its bases and construction.</p>";
    $("#d-trace").innerHTML = info.trace.length
      ? `<ol class="d-trace">${info.trace.map((step) => `<li><strong>${escape(step.operation)}</strong><code>${escape(step.id)}</code><pre>${escape(JSON.stringify({ ...(step.definition_id ? { definition_id: step.definition_id } : {}), ...(step.shape_id ? { shape_id: step.shape_id } : {}), ...(step.node_id ? { node_id: step.node_id } : {}), parameters: step.parameters, ...(step.world_transform ? { world_transform: step.world_transform } : {}), outputs: step.outputs }, null, 2))}</pre></li>`).join("")}</ol>`
      : `<p>${selected ? "No executed trace is available for this selection." : "Select a part or assembly to inspect the actual runtime operations."}</p>`;
    $("#d-checks").innerHTML = info.checks.length
      ? info.checks
          .map(
            (check) =>
              `<li><strong>${escape(check.scope)}</strong><span class="d-check-outcome" data-outcome="${escape(check.outcome)}">${escape(check.outcome)}</span><p>${escape(check.detail)}</p></li>`,
          )
          .join("")
      : "<li>Scoped checks are unavailable in this snapshot.</li>";
    $("#d-scale-basis")?.remove();
    const scaleBasis = document.createElement("div");
    scaleBasis.id = "d-scale-basis";
    scaleBasis.className = "d-basis";
    scaleBasis.innerHTML = basisMarkup(info.scale);
    $("#d-scale").after(scaleBasis);
    renderRegions();
  }
  function renderRegions() {
    const overlay = $("#d-source-regions");
    overlay.replaceChildren();
    const image = $("#d-image-slot img");
    if (!project || !image) return;
    const rect = containedImageRect(
      image.clientWidth,
      image.clientHeight,
      image.naturalWidth,
      image.naturalHeight,
    );
    if (!rect) return;
    overlay.setAttribute(
      "viewBox",
      `0 0 ${image.clientWidth} ${image.clientHeight}`,
    );
    for (const observation of explainSelection(project, selected)
      .observations) {
      if (!Array.isArray(observation.region)) continue;
      const [x0, y0, x1, y1] = observation.region;
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      const box = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "rect",
      );
      box.setAttribute("x", rect.x + x0 * rect.width);
      box.setAttribute("y", rect.y + y0 * rect.height);
      box.setAttribute("width", (x1 - x0) * rect.width);
      box.setAttribute("height", (y1 - y0) * rect.height);
      const title = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "title",
      );
      title.textContent = `${observation.id} · ${observation.statement}`;
      const label = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text",
      );
      label.setAttribute("x", rect.x + x0 * rect.width + 3);
      label.setAttribute(
        "y",
        Math.min(rect.y + y0 * rect.height + 12, rect.y + rect.height - 3),
      );
      label.textContent = observation.id;
      group.append(title, box, label);
      overlay.append(group);
    }
  }
  function select(
    id,
    resetIsolation = true,
    additive = false,
    preserve = false,
  ) {
    if (!preserve) selectedIds = changeSelection(selectedIds, id, additive);
    $("#d-handoff")?.remove();
    selected = selectedIds.includes(id) ? id : selectedIds.at(-1) || null;
    id = selected;
    if (nativeBuildId) {
      const review = selectionWorkflow(project, selected);
      if (
        ![review.selectedBuild?.id, review.assembly?.id].includes(nativeBuildId)
      ) {
        nativeBuildId = null;
        ++nativeTicket;
        preview = conceptPreview;
        if (preview) draw(preview);
        $("#d-status").textContent =
          "Part decomposition · select a part to review";
      }
    }
    if (resetIsolation) isolated = false;
    const node = tree?.byId.get(id);
    $("#d-node-name").textContent = node?.label || "No selection";
    $("#d-node-kind").textContent = node
      ? `${node.definition_id ? "Part" : "Assembly"} · ${node.evidence}`
      : "Concept geometry";
    $("#d-node-note").textContent =
      node?.note || "Choose a group or part in the model or structure.";
    $("#d-node-id").textContent = id || "";
    $("#d-selection").textContent = node
      ? `${node.label} · ${id}`
      : "Z up · right-handed";
    const labels = [];
    for (let n = node; n; n = tree.byId.get(n.parent_id))
      labels.unshift(n.label);
    $("#d-breadcrumb").textContent = labels.length
      ? labels.join(" / ")
      : project?.name || "Image → structure → parts";
    for (const key of ["focus", "isolate", "hide", "copy"])
      $(`#d-${key}`).disabled = !node;
    const handoffLabel = embedded ? "Edit in Codex" : "Copy for Codex";
    $("#d-handoff-mode").textContent =
      project?.id === "example"
        ? "Read-only sample. Copy as a reference; start a saved reviewed project before editing."
        : embedded
          ? "Send this selection to the host conversation."
          : "Copy this selection, then paste it into Codex.";
    $("#d-handoff-context-panel").hidden = !selectedIds.length;
    $("#d-handoff-context").textContent = selectedIds.length
      ? JSON.stringify(selectionContext(project, selectedIds), null, 2)
      : "";
    $("#d-copy").innerHTML = `${icon("copy")}${handoffLabel}`;
    $("#d-multi-copy").textContent =
      `${handoffLabel} (${selectedIds.length} selected)`;
    $("#d-selection-summary").hidden = selectedIds.length < 2;
    if (selectedIds.length > 1) {
      const context = selectionContext(project, selectedIds);
      $("#d-selection-count").textContent =
        `${selectedIds.length} selected / ${context.physical_part_ids.length} physical parts`;
      $("#d-selection-list").replaceChildren(
        ...context.selected_nodes.map((item) => {
          const li = document.createElement("li");
          li.textContent = item.label;
          return li;
        }),
      );
      $("#d-selection-impact").textContent = context.shared_unselected_part_ids
        .length
        ? `Shared geometry also affects ${context.shared_unselected_part_ids.length} unselected occurrences.`
        : "No other shared occurrences.";
      $("#d-selection-primary").textContent = project.workflow
        ? `Details and CAD actions below apply to ${node.label}.`
        : "Read-only reference; import a saved reviewed project to edit.";
    }
    renderExplanation();
    renderTree();
    applyView();
    renderWorkflow();
  }
  function accept({
    project: data,
    preview: nextPreview,
    reference: source,
    changed,
    geometryChanged,
  }) {
    const firstGeometry = !conceptPreview && Boolean(nextPreview);
    project = data;
    $(".d-workspace").dataset.empty = String(!data.plan);
    if (changed) {
      selectedIds = [];
      selected = null;
      isolated = false;
      hidden.clear();
      collapsed.clear();
      displayedAmount = amount = 0;
    }
    tree = data.plan ? hierarchy(data.plan.nodes) : null;
    const openEntry =
      entryPart && data.id === entryProject && tree?.byId.has(entryPart);
    if (openEntry) {
      selected = entryPart;
      selectedIds = [entryPart];
      entryPart = null;
      isolated = true;
      setInspectorTab("reference", true);
    }
    if (changed && !data.plan) setInspectorTab("reference");
    depth =
      changed || firstGeometry
        ? tree?.maxDepth || 0
        : Math.min(depth, tree?.maxDepth || 0);
    selectedIds = selectedIds.filter((id) => tree?.byId.has(id));
    if (!selectedIds.includes(selected)) selected = selectedIds.at(-1) || null;
    hidden = new Set([...hidden].filter((id) => tree?.byId.has(id)));
    conceptPreview = nextPreview;
    const currentBuilds = selectionWorkflow(data, selected);
    const currentNativeIds = [
      currentBuilds.assembly?.id,
      currentBuilds.selectedBuild?.id,
    ];
    if (
      geometryChanged ||
      (nativeBuildId && !currentNativeIds.includes(nativeBuildId))
    ) {
      nativeBuildId = null;
      ++nativeTicket;
      preview = nextPreview;
      if (!geometryChanged && preview) draw(preview);
    } else if (!nativeBuildId) preview = nextPreview;
    if (geometryChanged) {
      if (preview) draw(preview);
      else disposeMeshes();
    }
    $("#d-name").textContent = data.name;
    $("#d-status").textContent =
      data.workflow?.status === "building"
        ? "Building native CAD · checking STEP readback"
        : data.workflow?.status === "failed"
          ? "Native build failed · inspect the report"
          : nativeBuildId
            ? "Native preview · current verified build"
            : data.plan
              ? "Part decomposition · select a part to review"
              : data.workflow?.proposal?.approved
                ? "Proposal approved · waiting for the part plan"
                : "Source saved · review a proposal in Codex";
    $("#d-revision").textContent =
      `${data.id === "example" ? "Example · " : ""}Revision ${data.revision} · ${data.plan?.units === "mm" ? "mm" : "Scale unverified"}`;
    $("#d-empty").hidden = Boolean(preview);
    if (!preview) {
      $("#d-empty h1").textContent = data.workflow?.proposal?.approved
        ? "A direction to build on."
        : "Your source is ready.";
      $("#d-empty p").textContent = data.workflow?.proposal
        ? "Review the proposal in the source panel. Continue with Codex to refine the plan."
        : "Continue in Codex to propose the hierarchy, physical parts, and unknowns.";
      $("#d-example").hidden = true;
      $("#d-start").textContent = "Continue in Codex";
    }
    $("#d-tools").hidden = $("#d-explode-panel").hidden = !preview;
    $("#d-count").textContent = preview ? `${preview.parts.length} parts` : "—";
    $("#d-rights").textContent = data.source.rights;
    $("#d-hash").textContent = `SHA256 ${data.source.sha256.slice(0, 12)}…`;
    $("#d-hash").title = data.source.sha256;
    $("#d-source-badge").textContent =
      data.source.kind === "text"
        ? "Text source"
        : data.id === "example"
          ? "Illustration"
          : "Original";
    $("#d-scale").textContent =
      data.plan?.scale_note || "Scale and hidden geometry need evidence.";
    $("#d-assumptions").innerHTML = (data.plan?.assumptions || [])
      .map((note) => `<li>${escape(note)}</li>`)
      .join("");
    if (changed) {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
      imageUrl = null;
      $("#d-image-slot").replaceChildren();
      $(".d-image-wrap").hidden = data.source.kind === "text";
      if (data.source.kind !== "text") {
        const image = document.createElement("img");
        image.alt = "Original reference used for the decomposition";
        image.onload = renderRegions;
        if (source) {
          imageUrl = URL.createObjectURL(
            new Blob([Uint8Array.from(atob(source), (c) => c.charCodeAt(0))], {
              type: "image/png",
            }),
          );
          image.src = imageUrl;
        } else image.src = `/api/decompositions/${data.id}/reference`;
        image.onerror = () =>
          error(
            "The source reference could not be loaded. Its hash is retained.",
          );
        $("#d-image-slot").replaceChildren(image);
        $("#d-image-empty").hidden = true;
      }
    }
    const hasDownloads = Boolean(data.program && data.bundle && data.analysis);
    $("#d-downloads").hidden = !hasDownloads;
    if (hasDownloads) {
      const base = `/api/decompositions/${encodeURIComponent(data.id)}`;
      $("#d-program-download").href =
        `${base}/artifacts/${data.program.split("/").map(encodeURIComponent).join("/")}`;
      $("#d-bundle-download").href =
        `${base}/revisions/${data.revision}/bundle`;
      $("#d-program-binding").textContent =
        `Revision ${data.revision} · program SHA256 ${data.analysis.binding.program_sha256}`;
    }
    if (geometryChanged || changed)
      select(selected, changed && !openEntry, false, true);
    else {
      applyView();
      renderWorkflow();
    }
    error("");
    if ((changed || firstGeometry) && preview) {
      if (firstGeometry) $("#d-reference-panel").scrollTop = 0;
      root.updateMatrixWorld(true);
      fit();
    }
    if (!embedded) {
      const url = new URL(location.href);
      url.searchParams.set("project", data.id);
      if (changed && data.id !== entryProject) {
        url.searchParams.delete("part");
        url.searchParams.delete("view");
      }
      history.replaceState(null, "", url);
    }
    projectOption(data);
    projectPicker?.loading(false);
  }
  const session = createDecompositionSession({
    request: api,
    embedded,
    onProject: accept,
    onLoading: () => {
      $("#d-status").textContent = "Loading decomposition…";
      projectPicker?.loading(true);
    },
    onError: (e) => {
      error(e.message);
      projectPicker?.loading(false);
      $("#d-status").textContent = "Read failed · current view retained";
    },
  });
  const workflowActions = createWorkflowActions({
    getNavigationToken: () => session.ownership,
    getProject: () => project,
    action,
    accept: (data) => session.accept(data),
    notify: renderWorkflow,
  });
  continuationActions = createContinuationActions({
    getProject: () => project,
    getNavigationToken: () => session.ownership,
    runWorkflow: (name, payload) => workflowActions.run(name, payload),
    send: async (text, snapshot) => {
      if (!embedded) text = `Workspace: ${location.origin}\n\n${text}`;
      setInspectorTab("details", true);
      continuationSnapshot = continuationBinding(snapshot);
      $("#d-continuation-panel").hidden = false;
      $("#d-continuation-text").value = text;
      $("#d-continuation-status").textContent = "Preparing continuation…";
      const status = await handoff(text, $("#d-continuation-text"));
      if (continuationSnapshot === continuationBinding(project))
        $("#d-continuation-status").textContent = status;
      return status;
    },
    notify: renderWorkflow,
  });
  $("#d-copy-continuation").onclick = async () => {
    if (continuationSnapshot !== continuationBinding(project)) return;
    $("#d-continuation-status").textContent = await handoff(
      $("#d-continuation-text").value,
      $("#d-continuation-text"),
    );
  };
  projectPicker = mountProjectPicker({
    button: $("#d-project-switch"),
    menu: $("#d-project-menu"),
    search: $("#d-project-search"),
    list: $("#d-project-options"),
    open: (id) => session.open(id),
    current: () => project,
  });
  function projectOption(data) {
    projectPicker?.upsert(data);
  }
  $("#d-open-reference").onclick = () => setInspectorTab("reference", true);
  $("#d-open-checks").onclick = () => setInspectorTab("checks", true);
  $(".d-inspector-tabs").onclick = (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) setInspectorTab(tab.dataset.tab);
  };
  $(".d-inspector-tabs").onkeydown = (event) => {
    const tabs = ["details", "reference", "checks"];
    const index = tabs.indexOf(inspectorTab);
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % 3
        : event.key === "ArrowLeft"
          ? (index + 2) % 3
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? 2
              : null;
    if (next === null) return;
    event.preventDefault();
    setInspectorTab(tabs[next]);
    $(`#d-tab-${tabs[next]}`).focus();
  };
  $("#d-piece-checks").onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled || !selected) return;
    try {
      if (button.id === "d-define-piece-check") {
        button.textContent = await handoff(checkMessage(project, selected));
      } else if (button.id === "d-run-piece-check") {
        const scope = project.workflow.scopes[selected];
        await workflowActions.run("check", {
          node_id: selected,
          review_digest: scope.review_digest,
        });
        $("#d-run-piece-check")?.focus({ preventScroll: true });
      }
    } catch (failure) {
      error(failure.message);
    }
  };
  async function handoff(text, promptField = null) {
    try {
      if (await hostIterationMessage(text)) return "Sent to Codex";
    } catch (failure) {
      error(failure.message);
    }
    try {
      await navigator.clipboard.writeText(text);
      return "Copied · paste into Codex";
    } catch {
      error(
        "Clipboard unavailable. The handoff text is shown below for manual copying.",
      );
      if (promptField) {
        promptField.closest("details").open = true;
        promptField.focus();
        promptField.select();
        return "Prompt ready · copy it into Codex";
      }
      let fallback = $("#d-handoff");
      if (!fallback) {
        fallback = document.createElement("textarea");
        fallback.id = "d-handoff";
        fallback.readOnly = true;
        fallback.setAttribute("aria-label", "Copy this handoff into Codex");
        $(".d-inspector").append(fallback);
      }
      fallback.value = text;
      fallback.focus();
      fallback.select();
      return "Copy the handoff text into Codex";
    }
  }
  $("#d-example").onclick = () => session.open("anatomy-example");
  $("#d-new").onclick = () => $("#d-intake").showModal();
  $("#d-start").onclick = async () => {
    try {
      if (!project) $("#d-intake").showModal();
      else if (
        project.workflow?.proposal &&
        !project.workflow.proposal.approved
      )
        await continuationActions.run("approve-proposal");
      else
        await continuationActions.run(
          project.workflow?.proposal?.approved ? "decompose" : "proposal",
        );
    } catch (failure) {
      error(failure.message);
    }
  };
  $("#d-intake-close").onclick = () => $("#d-intake").close();
  $("#d-intake-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    if (button.disabled) return;
    const navigationToken = session.ownership;
    button.disabled = true;
    $("#d-intake-error").hidden = true;
    try {
      const fields = new FormData(form);
      const file = fields.get("image");
      let data_base64;
      if (file?.size) {
        if (file.size > 10 * 1024 * 1024)
          throw new Error("Use an image smaller than 10 MB.");
        data_base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(",")[1]);
          reader.onerror = () =>
            reject(new Error("The image could not be read."));
          reader.readAsDataURL(file);
        });
      }
      const result = await action(
        "/api/decompositions",
        intakePayload({
          name: fields.get("name"),
          rights: fields.get("rights"),
          description: fields.get("description"),
          data_base64,
        }),
      );
      if (session.ownership !== navigationToken) return;
      if (!(await session.accept(result))) return;
      $("#d-intake").close();
      form.reset();
      await continuationActions.run("proposal");
    } catch (failure) {
      $("#d-intake-error").textContent = failure.message;
      $("#d-intake-error").hidden = false;
    } finally {
      button.disabled = false;
    }
  };
  $("#d-reference-panel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-workflow]");
    if (!button || button.disabled) return;
    const name = button.dataset.workflow;
    try {
      error("");
      if (["proposal", "decompose", "approve-proposal"].includes(name)) {
        await continuationActions.run(name);
      } else if (["review", "approve", "cad", "verify"].includes(name)) {
        await continuationActions.run(name, selected);
      } else if (name === "native") await toggleNative();
    } catch (failure) {
      error(failure.message);
    }
  });
  async function toggleNative() {
    if (nativeBuildId) {
      ++nativeTicket;
      nativeBuildId = null;
      preview = conceptPreview;
      draw(preview);
      applyView();
      $("#d-status").textContent =
        "Part decomposition · select a part to review";
      renderWorkflow();
      return;
    }
    const review = selectionWorkflow(project, selected);
    const build = review.selectedBuild || review.assembly;
    if (!build?.preview_path) return;
    const ticket = ++nativeTicket;
    const ownership = session.ownership;
    const id = project.id,
      revision = project.revision;
    const native = await api(
      buildArtifactPath(id, build.id, build.preview_path),
    );
    const current = selectionWorkflow(project, selected);
    if (
      ticket !== nativeTicket ||
      ownership !== session.ownership ||
      project.id !== id ||
      project.revision !== revision ||
      ![current.selectedBuild?.id, current.assembly?.id].includes(build.id)
    )
      return;
    if (!native?.normalization || !Array.isArray(native.parts))
      throw new Error("Native preview has an invalid geometry payload.");
    verifyNativePreview(project, build, native);
    nativeBuildId = build.id;
    preview = { ...native, normalization: conceptPreview.normalization };
    draw(preview);
    applyView();
    $("#d-status").textContent = "Native preview · current verified build";
    renderWorkflow();
  }
  $("#d-source-toggle").onclick = () => {
    setInspectorVisibility($("#d-reference-panel").hidden);
  };
  $("#d-inspector-close").onclick = () => {
    $("#d-source-toggle").click();
    $("#d-source-toggle").focus();
  };
  $("#d-structure-toggle").onclick = () => {
    const visible = $("#d-sidebar").hidden;
    if (visible && compact.matches) setInspectorVisibility(false);
    $("#d-sidebar").hidden = !visible;
    $("#d-structure-toggle").setAttribute("aria-expanded", String(visible));
  };
  $("#d-sidebar-close").onclick = () => {
    $("#d-structure-toggle").click();
    $("#d-structure-toggle").focus();
  };
  function applyPanelLayout() {
    $("#d-sidebar").hidden = compact.matches;
    $("#d-structure-toggle").setAttribute("aria-expanded", "false");
    setInspectorVisibility(!compact.matches);
  }
  compact.addEventListener("change", applyPanelLayout);
  applyPanelLayout();
  $("#d-tree").onclick = (event) => {
    const collapse = event.target.closest("[data-collapse]");
    if (collapse) {
      const id = collapse.dataset.collapse;
      collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id);
      renderTree();
      $("#d-tree").querySelector(`[data-collapse="${id}"]`)?.focus();
      return;
    }
    const toggle = event.target.closest("[data-select]");
    if (toggle) {
      select(toggle.dataset.select, true, true);
      $("#d-tree")
        .querySelector(`[data-select="${toggle.dataset.select}"]`)
        ?.focus();
      return;
    }
    const node = event.target.closest("[data-node]");
    if (node) {
      select(node.dataset.node, true, event.metaKey || event.ctrlKey);
      $("#d-tree").querySelector(`[data-node="${node.dataset.node}"]`)?.focus();
    }
  };
  $("#d-levels").onclick = (event) => {
    const button = event.target.closest("[data-depth]");
    if (!button) return;
    depth = Number(button.dataset.depth);
    selectedIds = [
      ...new Set(selectedIds.map((id) => tree.atDepth(id, depth))),
    ];
    select(selectedIds.at(-1) || null, true, false, true);
    $("#d-levels").querySelector(`[data-depth="${depth}"]`).focus();
  };
  $("#d-fit").onclick = () => fit();
  $("#d-focus").onclick = () => fit(true);
  $("#d-isolate").onclick = () => {
    isolated = !isolated;
    applyView();
  };
  $("#d-hide").onclick = () => {
    if (selected) {
      for (const id of selectedIds) hidden.add(id);
      select(null);
    }
  };
  $("#d-restore").onclick = () => {
    hidden.clear();
    amount = 0;
    isolated = false;
    select(null);
  };
  $("#d-explode").oninput = (event) => {
    amount = Number(event.target.value);
    if (still.matches) {
      displayedAmount = amount;
      applyView();
    }
  };
  async function copySelection(event) {
    if (!selectedIds.length) return;
    try {
      event.currentTarget.textContent = await handoff(
        selectionMessage(project, selectedIds),
      );
    } catch (failure) {
      error(failure.message);
    }
  }
  $("#d-copy").onclick = copySelection;
  $("#d-multi-copy").onclick = copySelection;
  $("#d-reference-panel").onclick = async (event) => {
    const link = event.target.closest("a[download]");
    if (!link || !embedded) return;
    event.preventDefault();
    if (link.getAttribute("aria-busy") === "true") return;
    const snapshot = project;
    link.setAttribute("aria-busy", "true");
    let url;
    try {
      const result = await hostRequest(link.getAttribute("href"));
      if (project !== snapshot) return;
      const artifact = hostDownload(result, link.download);
      url = URL.createObjectURL(
        new Blob([artifact.bytes], { type: artifact.mime }),
      );
      const download = document.createElement("a");
      download.href = url;
      download.download = artifact.filename;
      download.click();
    } catch (e) {
      if (project === snapshot) error(e.message);
    } finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      link.removeAttribute("aria-busy");
    }
  };
  let start;
  renderer.domElement.addEventListener(
    "pointerdown",
    (event) => {
      const additive = event.metaKey || event.ctrlKey;
      start =
        event.button === 0 && event.isPrimary !== false && !event.shiftKey
          ? [event.clientX, event.clientY, additive]
          : null;
      if (start && additive) {
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
      }
    },
    true,
  );
  renderer.domElement.addEventListener("pointerup", () => {
    controls.enabled = true;
  });
  renderer.domElement.addEventListener("pointercancel", () => {
    start = null;
    controls.enabled = true;
  });
  renderer.domElement.addEventListener("click", (event) => {
    const down = start;
    start = null;
    if (
      !tree ||
      !down ||
      Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5
    )
      return;
    const rect = renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(
      new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      camera,
    );
    const hit = ray.intersectObjects(
      [...meshes.values()].filter((m) => m.visible),
      false,
    )[0];
    select(
      hit ? tree.atDepth(hit.object.userData.id, depth) : null,
      true,
      down[2],
    );
  });
  viewport.addEventListener("keydown", (event) => {
    if (event.key === "Escape") select(null);
    if (event.key.toLowerCase() === "f" && !event.metaKey && !event.ctrlKey)
      fit();
  });
  window.addEventListener("assembly:job", (event) => {
    if (event.detail?.kind === "decomposition") session.accept(event.detail);
  });
  window.addEventListener("assembly:error", (event) =>
    error(event.detail.message || String(event.detail)),
  );
  document.addEventListener("visibilitychange", () =>
    session.setVisible(!document.hidden),
  );
  window.addEventListener(
    "pagehide",
    () => {
      session.dispose();
      projectPicker?.destroy();
      compact.removeEventListener("change", applyPanelLayout);
      cancelAnimationFrame(frame);
      observer.disconnect();
      referenceObserver.disconnect();
      controls.dispose();
      disposeMeshes();
      renderer.dispose();
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    },
    { once: true },
  );
  api("/api/decompositions")
    .then(({ projects }) => {
      for (const item of projects) {
        projectOption(item);
      }
    })
    .catch((e) => error(e.message));
  const initial = new URL(location.href).searchParams.get("project");
  renderWorkflow();
  if (initial) await session.open(initial);
}
