import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { toCreasedNormals } from "three/addons/utils/BufferGeometryUtils.js";
import { hostRequest, installHostDownloads } from "./transport.js";
import { artifactPath, createViewer } from "./viewer-state.js";
import "./style.css";
import { initDecomposition } from "./decomposition-viewer.js";

if (
  new URL(location.href).searchParams.has("job") ||
  document.body.dataset.viewer === "step"
) {
  initAssemblyViewer();
} else {
  initDecomposition();
}

function initAssemblyViewer() {
  const icons = {
    cube: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    fit: '<path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
    isolate:
      '<path d="m12 5 6 3.5v7L12 19l-6-3.5v-7L12 5Z"/><path d="m6 8.5 6 3.5 6-3.5M12 12v7M3 4v3m0 10v3m18-3v3M21 4v3"/>',
    explode:
      '<path d="m8 8-4-4m0 5V4h5m7 4 4-4m-5 0h5v5M8 16l-4 4m0-5v5h5m7-4 4 4m-5 0h5v-5"/>',
    tree: '<rect x="3" y="3" width="7" height="5" rx="1"/><rect x="14" y="16" width="7" height="5" rx="1"/><rect x="14" y="7" width="7" height="5" rx="1"/><path d="M6 8v10h8M6 10h8"/>',
    download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    play: '<path d="m8 5 11 7-11 7V5Z"/>',
    pause: '<path d="M9 5v14M15 5v14"/>',
  };
  const icon = (name) =>
    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
  const $ = (selector) => document.querySelector(selector);
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );

  $("#app").innerHTML = `
<header class="file-navbar">
  <div class="file-identity">${icon("cube")}<div><strong class="file-name">assembly.step</strong><span class="file-meta"><span id="job-name">No model yet</span><span id="revision"></span></span></div></div>
  <p id="status" class="status" role="status" aria-live="polite">Waiting for a model</p>
  <a id="download-step" class="primary download" download="assembly.step" aria-disabled="true">${icon("download")}<span>Download final STEP</span></a>
</header>
<main id="viewport" class="workspace">
  <div id="viewer" tabindex="-1" aria-label="3D model. Drag to orbit, shift-drag to pan, scroll to zoom."></div>
  <div id="viewer-empty" class="viewer-empty">${icon("cube")}<strong id="empty-title">Your model appears here.</strong><span id="empty-help">Describe what you want to make in ChatGPT.<br>Continue the design conversation there.</span></div>
  <button id="open-tree" class="icon-button parts-toggle" title="Parts" aria-label="Show parts" aria-expanded="false" aria-controls="parts-panel">${icon("tree")}</button>
  <aside id="parts-panel" class="parts-panel" aria-labelledby="parts-title" hidden>
    <div class="panel-heading"><strong id="parts-title">Parts <span id="part-count"></span></strong><button id="close-tree" class="icon-button" aria-label="Close parts">${icon("close")}</button></div>
    <div id="tree" class="tree"></div>
  </aside>
  <div class="viewer-toolbar" role="toolbar" aria-label="Model view">
    <button id="fit" title="Fit model" disabled>${icon("fit")}<span>Fit</span></button>
    <button id="isolate" title="Show only selected part" aria-pressed="false" hidden>${icon("isolate")}<span>Isolate</span></button>
    <div id="explode-wrap" class="explode-wrap" hidden><button id="explode" aria-expanded="false" aria-controls="explode-popover">${icon("explode")}<span>Explode</span></button>
      <div id="explode-popover" class="explode-popover" hidden><label for="explode-amount">Explode <output id="explode-value">0%</output></label><input id="explode-amount" type="range" min="0" max="100" step="1" value="0"><button id="explode-reset">Reset</button></div>
    </div>
  </div>
  <div id="notice" class="notice" role="alert" hidden><span id="notice-text"></span><button id="notice-close" class="icon-button" aria-label="Dismiss message">${icon("close")}</button></div>
  <div class="viewer-bottom">
    <span id="selection-label" class="selection-label"></span>
    <section id="checkpoint-bar" class="checkpoint-bar" aria-label="Construction checkpoints" hidden>
      <button id="checkpoint-play" class="icon-button" title="Play construction" aria-label="Play construction">${icon("play")}</button>
      <div class="checkpoint-track"><label id="checkpoint-label" for="checkpoint-scrubber">Final model</label><input id="checkpoint-scrubber" type="range" min="0" max="10" value="10" step="1" aria-valuetext="Final model"></div>
      <button id="checkpoint-final" class="final-button">Final</button>
    </section>
    <span class="view-hint">Drag to orbit · Scroll to zoom</span>
  </div>
</main>`;

  async function api(path) {
    const hosted = await hostRequest(path);
    if (hosted !== null) return hosted;
    const response = await fetch(path);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const data = await response.json();
        if (typeof data.detail === "string") message = data.detail;
      } catch {}
      throw new Error(message);
    }
    return response.json();
  }
  function showError(error) {
    $("#notice").hidden = false;
    $("#notice-text").textContent = String(error.message || error).split(
      "\n",
    )[0];
  }
  function rememberJob(id) {
    if (!["http:", "https:"].includes(window.location.protocol)) return;
    const url = new URL(window.location.href);
    url.searchParams.set("job", id);
    window.history.replaceState(null, "", url);
  }
  const viewer = createViewer({
    read: api,
    changed: render,
    draw: drawPreview,
    reset: () => {
      disposeParts();
      $("#notice").hidden = true;
    },
    error: showError,
    remember: rememberJob,
    visible: !document.hidden,
  });
  const state = viewer.state;
  let downloading = false;
  let treeMarkup = "";

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#f8f8f8");
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100000);
  camera.up.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  $("#viewer").appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xffffff, 0xa3a3a3, 2));
  const light = new THREE.DirectionalLight(0xffffff, 2);
  light.position.set(5, -8, 15);
  scene.add(light);
  const grid = new THREE.GridHelper(400, 40, 0xd4d4d4, 0xe5e5e5);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);
  const parts = new THREE.Group();
  scene.add(parts);
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  function resize() {
    const el = $("#viewer");
    const w = el.clientWidth,
      h = el.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    fit(true);
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe($("#viewer"));
  let animationFrame;
  function animate() {
    animationFrame = requestAnimationFrame(animate);
    if (document.hidden) return;
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
  function disposeParts() {
    while (parts.children.length) {
      const obj = parts.children[0];
      parts.remove(obj);
      obj.geometry.dispose();
      obj.material.dispose();
    }
  }
  function fit(preserveDirection = false) {
    const box = new THREE.Box3();
    parts.children
      .filter((part) => part.visible)
      .forEach((part) => box.expandByObject(part));
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const dim = Math.max(size.x, size.y, size.z, 1);
    const radius = Math.max(
      box.getBoundingSphere(new THREE.Sphere()).radius,
      0.5,
    );
    const verticalHalfFov =
      THREE.MathUtils.degToRad(camera.getEffectiveFOV()) / 2;
    const horizontalHalfFov = Math.atan(
      Math.tan(verticalHalfFov) * camera.aspect,
    );
    const distance =
      (radius / Math.sin(Math.min(verticalHalfFov, horizontalHalfFov))) * 1.15;
    const direction = preserveDirection
      ? camera.position.clone().sub(controls.target).normalize()
      : new THREE.Vector3(1.6, -2, 1.5).normalize();
    controls.target.copy(center);
    camera.position.copy(center).addScaledVector(direction, distance);
    camera.near = dim / 1000;
    camera.far = distance + radius * 100;
    camera.updateProjectionMatrix();
    grid.position.z = box.min.z - dim * 0.02;
    grid.scale.setScalar(Math.max(dim / 160, 0.1));
    controls.update();
  }
  function applyView() {
    const centers = parts.children.map((part) => part.userData.center);
    const all = centers.reduce(
      (sum, center) => sum.add(center),
      new THREE.Vector3(),
    );
    if (centers.length) all.divideScalar(centers.length);
    parts.children.forEach((part, i) => {
      part.visible = !state.isolate || part.userData.id === state.selected;
      part.position.copy(part.userData.position);
      if (state.explode) {
        if (part.userData.explodeVector) {
          part.position.addScaledVector(
            part.userData.explodeVector,
            state.explode / 100,
          );
        } else {
          const direction = centers[i].clone().sub(all);
          if (direction.length() < 0.001)
            direction.set((i % 3) - 1, (Math.floor(i / 3) % 3) - 1, 1);
          part.position.add(direction.multiplyScalar(state.explode * 0.012));
        }
      }
      part.material.color.set(
        part.userData.id === state.selected ? "#5b6670" : part.userData.color,
      );
    });
    const multiple = (state.job?.document?.occurrences?.length || 0) > 1;
    $("#isolate").hidden = !multiple;
    $("#isolate").disabled =
      !state.selected ||
      !parts.children.some((part) => part.userData.id === state.selected);
    $("#isolate").setAttribute("aria-pressed", String(state.isolate));
    $("#fit").disabled = !parts.children.length;
    $("#explode-wrap").hidden = !multiple;
    $("#explode").disabled = !parts.children.length;
    $("#explode").classList.toggle("active", state.explode > 0);
    $("#explode-amount").value = state.explode;
    $("#explode-value").textContent = `${state.explode}%`;
  }
  function drawPreview(preview) {
    const preserveDirection = camera.position.length() > 0;
    disposeParts();
    for (const part of preview.parts || []) {
      if (!part.vertices?.length || !part.triangles?.length) continue;
      const indexedGeometry = new THREE.BufferGeometry();
      indexedGeometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(part.vertices.flat(), 3),
      );
      indexedGeometry.setIndex(part.triangles.flat());
      const geometry = toCreasedNormals(indexedGeometry, Math.PI / 6);
      indexedGeometry.dispose();
      const color = /^#[0-9a-f]{6}$/i.test(part.color) ? part.color : "#b3b3b3";
      const opacity = Number.isFinite(part.opacity)
        ? THREE.MathUtils.clamp(part.opacity, 0.05, 1)
        : 1;
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({
          color,
          transparent: opacity < 1,
          opacity,
          depthWrite: opacity === 1,
          roughness: 0.65,
          metalness: 0.18,
          side: THREE.DoubleSide,
        }),
      );
      if (part.transform?.length === 4) {
        mesh.matrix.fromArray(part.transform.flat());
        mesh.matrix.transpose();
        mesh.matrix.decompose(mesh.position, mesh.quaternion, mesh.scale);
      }
      mesh.userData = {
        id: part.id,
        definition_id: part.definition_id,
        color,
        explodeVector:
          part.explode_vector?.length === 3 &&
          part.explode_vector.every(Number.isFinite)
            ? new THREE.Vector3(...part.explode_vector)
            : null,
        position: mesh.position.clone(),
        center: new THREE.Box3()
          .setFromObject(mesh)
          .getCenter(new THREE.Vector3()),
      };
      parts.add(mesh);
    }
    applyView();
    fit(preserveDirection);
  }
  let pointerStart = null;
  renderer.domElement.addEventListener("pointerdown", (event) => {
    pointerStart =
      event.isPrimary &&
      event.button === 0 &&
      !event.shiftKey &&
      !event.ctrlKey &&
      !event.metaKey
        ? { x: event.clientX, y: event.clientY }
        : null;
  });
  renderer.domElement.addEventListener("pointercancel", () => {
    pointerStart = null;
  });
  renderer.domElement.addEventListener("click", (event) => {
    const start = pointerStart;
    pointerStart = null;
    if (
      event.button !== 0 ||
      !start ||
      Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5
    )
      return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      (-(event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(mouse, camera);
    const hit = raycaster
      .intersectObjects(parts.children)
      .find((item) => item.object.visible);
    selectOccurrence(hit ? hit.object.userData.id : null);
  });
  $("#fit").onclick = () => fit();
  $("#isolate").onclick = () => {
    if (state.selected) {
      state.isolate = !state.isolate;
      applyView();
    }
  };
  $("#explode").onclick = () => {
    const popover = $("#explode-popover");
    popover.hidden = !popover.hidden;
    $("#explode").setAttribute("aria-expanded", String(!popover.hidden));
  };
  $("#explode-amount").oninput = (event) => {
    state.explode = Number(event.target.value);
    applyView();
  };
  $("#explode-reset").onclick = () => {
    state.explode = 0;
    applyView();
  };
  function selectOccurrence(id) {
    viewer.select(id);
  }
  function setPartsOpen(value) {
    state.partsOpen = value;
    render();
    if (!value) $("#open-tree").focus({ preventScroll: true });
  }
  $("#open-tree").onclick = () => setPartsOpen(!state.partsOpen);
  $("#close-tree").onclick = () => setPartsOpen(false);
  $("#notice-close").onclick = () => {
    $("#notice").hidden = true;
  };
  $("#checkpoint-play").onclick = () => viewer.play();
  $("#checkpoint-final").onclick = () => viewer.selectStage(null);
  $("#checkpoint-scrubber").oninput = (event) => {
    const index = Number(event.target.value);
    viewer.selectStage(
      index === state.construction.stages.length ? null : index,
    );
  };
  $("#tree").onclick = (event) => {
    const item = event.target.closest("[data-part-id]");
    if (item)
      selectOccurrence(
        item.dataset.partId === state.selected ? null : item.dataset.partId,
      );
  };
  function render() {
    const job = state.job;
    const occurrences = job?.document?.occurrences || [];
    const definitions = job?.document?.definitions || [];
    const ready = job?.state === "ready";
    const downloadable = ready && Boolean(job.artifacts?.["assembly.step"]);
    const name = job?.name || "Untitled model";
    $("#job-name").textContent = job ? name : "No model yet";
    $("#job-name").title = job ? name : "";
    $("#revision").textContent = job ? `Rev ${job.revision}` : "";
    const statuses = {
      queued: "Model queued",
      building: "Building model…",
      ready: "STEP ready",
      failed: "Build failed · Continue in ChatGPT",
      needs_evidence: "More detail needed in ChatGPT",
      cancelled: "Build cancelled",
    };
    $("#status").textContent = downloading
      ? "Downloading STEP…"
      : state.loadingPreview
        ? "Loading model…"
        : ready && !downloadable
          ? "No STEP available · Continue in ChatGPT"
          : statuses[job?.state] ||
            (job ? "Review the model in ChatGPT" : "Waiting for a model");
    $("#status").dataset.state = job?.state || "empty";
    const download = $("#download-step");
    if (downloadable)
      download.setAttribute("href", artifactPath(job.id, "assembly.step"));
    else download.removeAttribute("href");
    download.setAttribute(
      "aria-disabled",
      String(!downloadable || downloading),
    );
    download.setAttribute(
      "tabindex",
      downloadable && !downloading ? "0" : "-1",
    );
    $("#viewer-empty").hidden = parts.children.length > 0;
    $("#viewer-empty").classList.toggle(
      "loading",
      state.loadingPreview || ["queued", "building"].includes(job?.state),
    );
    $("#empty-title").textContent = state.loadingPreview
      ? "Loading your model…"
      : ["queued", "building"].includes(job?.state)
        ? "Your model is taking shape."
        : job?.state === "failed"
          ? "This build needs another look."
          : ready
            ? downloadable
              ? "Preview unavailable."
              : "No STEP generated yet."
            : job
              ? "Continue the design in ChatGPT."
              : "Your model appears here.";
    $("#empty-help").innerHTML = job
      ? downloadable
        ? "The final STEP can be downloaded above.<br>Continue the design conversation in ChatGPT."
        : "Keep the requirements and modeling conversation in ChatGPT.<br>The generated STEP will appear here."
      : "Describe what you want to make in ChatGPT.<br>Continue the design conversation there.";
    $("#parts-panel").hidden = !state.partsOpen;
    $("#open-tree").setAttribute("aria-expanded", String(state.partsOpen));
    $("#open-tree").setAttribute(
      "aria-label",
      state.partsOpen ? "Hide parts" : "Show parts",
    );
    $("#part-count").textContent = String(occurrences.length);
    const partButton = (part) => {
      const definition = definitions.find(
        (item) => item.id === part.definition_id,
      );
      return `<button class="tree-item" data-part-id="${escape(part.id)}" aria-pressed="${part.id === state.selected}" title="${escape(part.id)}">${icon("cube")}<span>${escape(part.label || definition?.label || part.id)}</span></button>`;
    };
    const groups = job?.document?.assembly_groups || [];
    const groupIds = new Set(groups.map((group) => group.id));
    const markup = occurrences.length
      ? groups
          .map((group) => {
            const members = occurrences.filter(
              (part) => part.parent_id === group.id,
            );
            return `<section class="tree-group" aria-label="${escape(group.label)}"><h3>${escape(group.label)} <span>${members.length}</span></h3>${members.map(partButton).join("")}</section>`;
          })
          .join("") +
        occurrences
          .filter((part) => !groupIds.has(part.parent_id))
          .map(partButton)
          .join("")
      : '<p class="parts-empty">Physical parts appear with your model.</p>';
    if (markup !== treeMarkup) {
      $("#tree").innerHTML = markup;
      treeMarkup = markup;
    }
    const selected = occurrences.find((part) => part.id === state.selected);
    $("#selection-label").textContent = selected
      ? selected.label ||
        definitions.find((item) => item.id === selected.definition_id)?.label ||
        selected.id
      : "";
    const stages = state.construction?.stages || [];
    $("#checkpoint-bar").hidden = !stages.length || !state.preview || !ready;
    const stage = state.stageIndex === null ? null : stages[state.stageIndex];
    const label = stage
      ? `Checkpoint ${state.stageIndex + 1} / ${stages.length} · ${stage.label || "Construction"}`
      : "Final model";
    $("#checkpoint-label").textContent = state.loadingStage
      ? "Loading checkpoint…"
      : label;
    $("#checkpoint-label").title = label;
    $("#checkpoint-scrubber").max = stages.length;
    $("#checkpoint-scrubber").value = state.stageIndex ?? stages.length;
    $("#checkpoint-scrubber").setAttribute("aria-valuetext", label);
    $("#checkpoint-bar").setAttribute("aria-busy", String(state.loadingStage));
    $("#checkpoint-play").innerHTML = icon(state.playing ? "pause" : "play");
    $("#checkpoint-play").setAttribute(
      "aria-label",
      state.playing ? "Pause construction" : "Play construction",
    );
    $("#checkpoint-play").title = state.playing
      ? "Pause construction"
      : "Play construction";
    $("#checkpoint-final").disabled =
      state.stageIndex === null && !state.loadingStage;
    applyView();
  }
  function closeExplode() {
    $("#explode-popover").hidden = true;
    $("#explode").setAttribute("aria-expanded", "false");
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".explode-wrap")) closeExplode();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.isComposing) return;
    if (!$("#explode-popover").hidden) {
      closeExplode();
      $("#explode").focus();
    } else if (state.partsOpen) setPartsOpen(false);
    else selectOccurrence(null);
  });
  document.addEventListener("visibilitychange", () => {
    viewer.setVisible(!document.hidden).catch(showError);
  });
  window.addEventListener("assembly:job", (event) =>
    viewer.accept(event.detail).catch(showError),
  );
  window.addEventListener("assembly:error", (event) => showError(event.detail));
  window.addEventListener("assembly:download", (event) => {
    downloading = event.detail.busy;
    render();
  });
  const removeDownloads = installHostDownloads();
  window.addEventListener(
    "pagehide",
    () => {
      viewer.dispose();
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      controls.dispose();
      disposeParts();
      grid.geometry.dispose();
      grid.material.dispose();
      renderer.dispose();
      removeDownloads();
    },
    { once: true },
  );
  render();
  const initialJobId = new URL(window.location.href).searchParams.get("job");
  if (initialJobId) viewer.open(initialJobId).catch(showError);
}
