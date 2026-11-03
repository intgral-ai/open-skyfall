import { App } from "@modelcontextprotocol/ext-apps";

let client = null;
const embedded = window.parent !== window;
const ready = embedded
  ? (async () => {
      client = new App({ name: "Open Assembly CAD", version: "0.1.0" });
      client.ontoolresult = (result) => {
        const data = result.structuredContent;
        if (data?.id || data?.job?.id)
          window.dispatchEvent(
            new CustomEvent("assembly:job", { detail: data }),
          );
      };
      await client.connect();
      return client;
    })()
  : Promise.resolve(null);
// Report connection failure even when the host opens the viewer without a job.
ready.catch((error) => {
  window.dispatchEvent(new CustomEvent("assembly:error", { detail: error }));
});

export async function hostRequest(path, options = {}) {
  if (options.method && options.method !== "GET")
    throw new Error("The viewer only reads generated models.");
  if (!embedded) return null;
  await ready;
  const result = await client.callServerTool({
    name: "workspace_request",
    arguments: { method: "GET", path, payload: {} },
  });
  if (result.isError)
    throw new Error(
      result.content?.find((item) => item.type === "text")?.text ||
        "Workspace request failed",
    );
  return (
    result.structuredContent ||
    JSON.parse(result.content.find((item) => item.type === "text").text)
  );
}

export async function hostWorkflowAction(path, payload) {
  if (
    !/^\/api\/decompositions(?:\/[a-zA-Z0-9_-]+\/workflow\/(?:proposal|approve-proposal|decompose-example|request|approve|build|check-context|check))?$/.test(
      path,
    )
  )
    throw new Error("Unsupported decomposition workflow action.");
  if (!embedded) return null;
  await ready;
  const result = await client.callServerTool({
    name: "workspace_request",
    arguments: { method: "POST", path, payload },
  });
  if (result.isError)
    throw new Error(
      result.content?.find((item) => item.type === "text")?.text ||
        "Workflow action failed",
    );
  return (
    result.structuredContent ||
    JSON.parse(result.content.find((item) => item.type === "text").text)
  );
}

export async function hostIterationMessage(text) {
  if (!embedded) return false;
  await ready;
  const result = await client.sendMessage({
    role: "user",
    content: [{ type: "text", text }],
  });
  if (result.isError)
    throw new Error(
      "The host could not accept the message. Copy it into Codex instead.",
    );
  return true;
}

export function installHostDownloads() {
  if (!embedded) return () => {};
  const click = async (event) => {
    const link = event.target.closest?.("a[download]");
    const path = link?.getAttribute("href");
    if (
      !path ||
      !/^\/api\/jobs\/[^/?#]+\/artifacts\/assembly\.step$/.test(path)
    )
      return;
    event.preventDefault();
    if (link.getAttribute("aria-disabled") === "true") return;
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("aria-busy", "true");
    window.dispatchEvent(
      new CustomEvent("assembly:download", { detail: { busy: true } }),
    );
    let url;
    try {
      const result = await hostRequest(path);
      if (!result?.data_base64) throw new Error("The STEP download was empty.");
      const bytes = Uint8Array.from(atob(result.data_base64), (c) =>
        c.charCodeAt(0),
      );
      url = URL.createObjectURL(new Blob([bytes], { type: result.mime_type }));
      const download = document.createElement("a");
      download.href = url;
      download.download = result.filename || "assembly.step";
      download.click();
    } catch (error) {
      window.dispatchEvent(
        new CustomEvent("assembly:error", { detail: error }),
      );
    } finally {
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
      link.removeAttribute("aria-disabled");
      link.removeAttribute("aria-busy");
      window.dispatchEvent(
        new CustomEvent("assembly:download", { detail: { busy: false } }),
      );
    }
  };
  document.addEventListener("click", click);
  return () => document.removeEventListener("click", click);
}
