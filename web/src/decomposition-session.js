import {
  assertAnalysisBinding,
  assertProgramBinding,
} from "./decomposition-explanation.js";

export function createDecompositionSession({
  request,
  embedded = false,
  onProject,
  onError,
  onLoading = () => {},
  timers = globalThis,
}) {
  let current = null,
    preview = null,
    program = null,
    activeId = null,
    generation = 0;
  let timer,
    visible = true,
    disposed = false;
  function stopTimer() {
    timers.clearTimeout(timer);
  }
  function schedule() {
    stopTimer();
    if (
      disposed ||
      !visible ||
      !current ||
      activeId !== current.id ||
      current.id === "example"
    )
      return;
    timer = timers.setTimeout(() => refresh(), 2000);
  }
  async function publish(data, ticket) {
    if (disposed || ticket !== generation || data.kind !== "decomposition")
      return false;
    const changed = current?.id !== data.id;
    if (!changed && data.revision < current.revision) return false;
    if (
      !changed &&
      data.revision === current.revision &&
      (data.workflow_revision ?? 0) < (current.workflow_revision ?? 0)
    )
      return false;
    assertAnalysisBinding(data);
    const geometryChanged = changed || current?.revision !== data.revision;
    if (
      !geometryChanged &&
      data.program &&
      (data.program !== current.program ||
        data.artifacts[data.program] !== current.artifacts[current.program])
    )
      throw new Error(
        "Accepted program changed without a new concept revision.",
      );
    const nextProgram = data.program
      ? geometryChanged
        ? await request(
            `/api/decompositions/${data.id}/artifacts/${data.program}`,
          )
        : program
      : null;
    if (disposed || ticket !== generation) return false;
    assertProgramBinding(data, nextProgram);
    const mesh = geometryChanged
      ? data.preview_data ||
        (data.preview
          ? await request(
              `/api/decompositions/${data.id}/artifacts/${data.preview}`,
            )
          : null)
      : preview;
    let reference = data.reference_base64;
    if (changed && embedded && data.source?.kind !== "text" && !reference)
      reference = (await request(`/api/decompositions/${data.id}/reference`))
        .data_base64;
    if (disposed || ticket !== generation) return false;
    current = data;
    preview = mesh;
    program = structuredClone(nextProgram);
    onProject({
      project: data,
      preview: mesh,
      reference,
      changed,
      geometryChanged,
    });
    return true;
  }
  async function open(id) {
    if (!id || disposed) return;
    activeId = id;
    const ticket = ++generation;
    stopTimer();
    onLoading();
    try {
      await publish(
        await request(
          id === "anatomy-example"
            ? "/api/decomposition-anatomy-example"
            : id === "example"
              ? "/api/decomposition-example"
              : `/api/decompositions/${id}`,
        ),
        ticket,
      );
      if (ticket === generation && current) activeId = current.id;
    } catch (error) {
      if (ticket === generation && !disposed) onError(error);
    } finally {
      if (ticket === generation) schedule();
    }
  }
  async function refresh() {
    if (disposed || !visible || !current || activeId !== current.id) return;
    const ticket = generation,
      id = current.id;
    try {
      const data = await request(`/api/decompositions/${id}`);
      if (ticket !== generation || !visible) return;
      if (
        data.revision !== current.revision ||
        data.state !== current.state ||
        data.workflow_revision !== current.workflow_revision
      )
        await publish(data, ticket);
    } catch (error) {
      if (ticket === generation && !disposed) onError(error);
    } finally {
      if (ticket === generation) schedule();
    }
  }
  async function accept(data) {
    if (disposed || data.kind !== "decomposition") return false;
    activeId = data.id;
    const ticket = ++generation;
    stopTimer();
    try {
      return await publish(data, ticket);
    } catch (error) {
      if (ticket === generation && !disposed) onError(error);
      return false;
    } finally {
      if (ticket === generation) schedule();
    }
  }
  return {
    open,
    accept,
    get ownership() {
      return generation;
    },
    setVisible(value) {
      visible = value;
      if (!value) {
        ++generation;
        stopTimer();
      } else {
        if (activeId && (!current || current.id !== activeId)) open(activeId);
        else if (current && current.id !== "example") refresh();
        else schedule();
      }
    },
    dispose() {
      disposed = true;
      ++generation;
      stopTimer();
    },
  };
}
