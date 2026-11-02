export function geometryIdentity(job) {
  return JSON.stringify([
    job.id,
    job.revision,
    job.artifacts?.["assembly.step"]?.sha256 || null,
  ]);
}

export function artifactPath(jobId, name) {
  return `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${name}`;
}

export function createViewer({
  read,
  changed = () => {},
  draw = () => {},
  reset = () => {},
  error = () => {},
  remember = () => {},
  setTimer = setTimeout,
  clearTimer = clearTimeout,
  visible = true,
}) {
  const state = {
    job: null,
    preview: null,
    displayedPreview: null,
    selected: null,
    isolate: false,
    explode: 0,
    partsOpen: false,
    construction: null,
    stageIndex: null,
    loadingPreview: false,
    loadingStage: false,
    playing: false,
    visible,
  };
  let epoch = 0;
  let geometryToken = 0;
  let stageToken = 0;
  let playbackToken = 0;
  let openToken = 0;
  let pollTimer = null;
  let playTimer = null;
  let pollInFlight = false;
  let geometryLoad = null;
  let disposed = false;

  const notify = () => changed(state);
  const current = (token, identity) =>
    !disposed &&
    token === geometryToken &&
    state.job &&
    identity === geometryIdentity(state.job);

  function pause() {
    ++playbackToken;
    clearTimer(playTimer);
    playTimer = null;
    state.playing = false;
  }

  function schedulePoll() {
    clearTimer(pollTimer);
    pollTimer = null;
    if (!disposed && state.visible && state.job && !pollInFlight)
      pollTimer = setTimer(poll, 2000);
  }

  async function poll() {
    pollTimer = null;
    if (disposed || !state.visible || !state.job || pollInFlight) return;
    const token = epoch;
    const id = state.job.id;
    pollInFlight = true;
    try {
      const job = await read(`/api/jobs/${encodeURIComponent(id)}`);
      if (!disposed && state.visible && token === epoch && state.job?.id === id)
        await accept(job, { epoch: token });
    } catch (cause) {
      if (!disposed && state.visible && token === epoch)
        error(new Error(`Could not refresh the model. ${cause.message}`));
    } finally {
      pollInFlight = false;
      schedulePoll();
    }
  }

  async function loadGeometry() {
    if (disposed || !state.visible || state.job?.state !== "ready") return;
    const identity = geometryIdentity(state.job);
    if (geometryLoad?.identity === identity) return geometryLoad.promise;
    if (state.preview) return;
    const job = state.job;
    const token = geometryToken;
    state.loadingPreview = true;
    notify();
    const load = { identity, promise: null };
    geometryLoad = load;
    load.promise = (async () => {
      const preview = read(artifactPath(job.id, "preview.json"));
      const construction =
        job.document?.backend === "smlibpy"
          ? read(artifactPath(job.id, "construction.json"))
          : Promise.resolve(null);
      const [previewResult, constructionResult] = await Promise.allSettled([
        preview,
        construction,
      ]);
      if (!current(token, identity) || !state.visible) return;
      if (previewResult.status === "fulfilled") {
        state.preview = previewResult.value;
        state.displayedPreview = previewResult.value;
        draw(previewResult.value);
      } else {
        error(
          new Error(`Preview unavailable. ${previewResult.reason.message}`),
        );
      }
      if (constructionResult.status === "fulfilled")
        state.construction = constructionResult.value;
      else
        error(
          new Error(
            `Construction checkpoints unavailable. ${constructionResult.reason.message}`,
          ),
        );
    })().finally(() => {
      if (geometryLoad === load) geometryLoad = null;
      if (current(token, identity)) {
        state.loadingPreview = false;
        notify();
      }
    });
    return load.promise;
  }

  async function accept(snapshot, expected = null) {
    if (disposed || (expected && expected.epoch !== epoch)) return;
    const job = snapshot?.job || snapshot;
    if (!job?.id) return;
    const previous = state.job;
    if (previous?.id === job.id) {
      if (Number(previous.revision) > Number(job.revision)) return;
      if (
        previous.revision === job.revision &&
        previous.updated_at &&
        job.updated_at &&
        previous.updated_at > job.updated_at
      )
        return;
    }
    const newJob = previous?.id !== job.id;
    const newGeometry =
      !previous || geometryIdentity(previous) !== geometryIdentity(job);
    if (newJob) {
      ++epoch;
      ++openToken;
      state.selected = null;
    }
    state.job = job;
    remember(job.id);
    if (newGeometry) {
      ++geometryToken;
      ++stageToken;
      pause();
      geometryLoad = null;
      state.preview = null;
      state.displayedPreview = null;
      state.construction = null;
      state.stageIndex = null;
      state.loadingStage = false;
      state.loadingPreview = false;
      state.isolate = false;
      state.explode = 0;
      if (
        !job.document?.occurrences?.some((part) => part.id === state.selected)
      )
        state.selected = null;
      reset();
    }
    notify();
    schedulePoll();
    await loadGeometry();
  }

  async function open(id) {
    const token = ++openToken;
    const job = await read(`/api/jobs/${encodeURIComponent(id)}`);
    if (!disposed && token === openToken) await accept(job);
  }

  async function selectStage(index, fromPlayback = false) {
    const stage = index === null ? null : state.construction?.stages?.[index];
    if (
      !state.visible ||
      state.job?.state !== "ready" ||
      !state.preview ||
      (index !== null && !stage)
    )
      return false;
    if (!fromPlayback) pause();
    const identity = geometryIdentity(state.job);
    const token = geometryToken;
    const stageRequest = ++stageToken;
    state.loadingStage = true;
    notify();
    try {
      const preview = stage
        ? await read(artifactPath(state.job.id, stage.preview_artifact))
        : state.preview;
      if (
        !current(token, identity) ||
        stageRequest !== stageToken ||
        !state.visible
      )
        return false;
      state.stageIndex = index;
      state.displayedPreview = preview;
      draw(preview);
      return true;
    } catch (cause) {
      if (current(token, identity) && stageRequest === stageToken)
        error(new Error(`Checkpoint unavailable. ${cause.message}`));
      return false;
    } finally {
      if (current(token, identity) && stageRequest === stageToken) {
        state.loadingStage = false;
        notify();
      }
    }
  }

  async function play() {
    if (state.playing) {
      pause();
      notify();
      return;
    }
    const count = state.construction?.stages?.length || 0;
    if (!count || !state.visible || !state.preview) return;
    state.playing = true;
    const token = ++playbackToken;
    let index = state.stageIndex === null ? 0 : state.stageIndex + 1;
    const advance = async () => {
      if (
        disposed ||
        !state.visible ||
        !state.playing ||
        token !== playbackToken
      )
        return;
      const final = index >= count;
      const success = await selectStage(final ? null : index, true);
      if (token !== playbackToken) return;
      if (!success || final) {
        pause();
        notify();
        return;
      }
      index++;
      playTimer = setTimer(advance, 1200);
    };
    notify();
    await advance();
  }

  function select(id) {
    state.selected = state.job?.document?.occurrences?.some(
      (part) => part.id === id,
    )
      ? id
      : null;
    if (!state.selected) state.isolate = false;
    notify();
  }

  async function setVisible(value) {
    state.visible = value;
    if (!value) {
      clearTimer(pollTimer);
      pollTimer = null;
      pause();
      ++stageToken;
      state.loadingStage = false;
      notify();
    } else {
      await poll();
      await loadGeometry();
    }
  }

  function dispose() {
    disposed = true;
    ++epoch;
    ++geometryToken;
    ++stageToken;
    ++openToken;
    pause();
    clearTimer(pollTimer);
  }

  return {
    state,
    accept,
    open,
    poll,
    select,
    selectStage,
    play,
    pause,
    setVisible,
    dispose,
  };
}
