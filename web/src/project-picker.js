const examples = [
  {
    id: "anatomy-example",
    name: "Inspection rig",
    detail: "Start a new proposed design",
  },
  { id: "example", name: "Desk lamp", detail: "Read-only mesh sample" },
];
export function projectRows(projects, query = "") {
  const term = query.trim().toLocaleLowerCase();
  return [...projects]
    .filter((p) => `${p.name} ${p.id}`.toLocaleLowerCase().includes(term))
    .sort(
      (a, b) =>
        (b.updated_at || "").localeCompare(a.updated_at || "") ||
        a.name.localeCompare(b.name),
    );
}
export function mountProjectPicker({
  button,
  menu,
  search,
  list,
  open,
  current,
}) {
  const projects = new Map();
  function render() {
    list.replaceChildren();
    for (const [label, rows] of [
      ["Saved projects", projectRows(projects.values(), search.value)],
      ["Examples", projectRows(examples, search.value)],
    ]) {
      if (!rows.length) continue;
      const heading = document.createElement("h3");
      heading.textContent = label;
      list.append(heading);
      for (const row of rows) {
        const item = document.createElement("button");
        item.type = "button";
        item.dataset.project = row.id;
        if (row.id === current()?.id) item.setAttribute("aria-current", "true");
        const title = document.createElement("span");
        title.textContent = row.name;
        const detail = document.createElement("small");
        detail.textContent =
          row.detail ||
          `Revision ${row.revision} / ${row.workflow?.cad?.assembly ? "CAD ready" : row.plan ? "Part review" : "Draft"} / ${row.id.slice(0, 6)}`;
        item.append(title, detail);
        list.append(item);
      }
    }
    if (!list.children.length) {
      const p = document.createElement("p");
      p.textContent = "No matching projects.";
      list.append(p);
    }
  }
  function position() {
    const r = button.getBoundingClientRect(),
      width = Math.min(360, innerWidth - 32);
    menu.style.width = `${width}px`;
    menu.style.left = `${Math.max(16, Math.min(r.left, innerWidth - width - 16))}px`;
    menu.style.top = `${r.bottom + 8}px`;
  }
  button.onclick = () => menu.togglePopover();
  menu.addEventListener("toggle", (event) => {
    const shown = event.newState === "open";
    button.setAttribute("aria-expanded", String(shown));
    if (shown) {
      search.value = "";
      render();
      position();
      search.focus();
    }
  });
  search.oninput = render;
  search.onkeydown = (event) => {
    if (event.key === "ArrowDown" || event.key === "Enter") {
      event.preventDefault();
      const first = list.querySelector("button");
      if (event.key === "Enter") first?.click();
      else first?.focus();
    }
  };
  list.onclick = (event) => {
    const target = event.target.closest("[data-project]");
    if (!target) return;
    menu.hidePopover();
    button.focus();
    open(target.dataset.project);
  };
  list.onkeydown = (event) => {
    const items = [...list.querySelectorAll("button")],
      index = items.indexOf(document.activeElement);
    const next =
      event.key === "ArrowDown"
        ? Math.min(items.length - 1, index + 1)
        : event.key === "ArrowUp"
          ? index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : null;
    if (next === null) return;
    event.preventDefault();
    if (next < 0) search.focus();
    else items[next]?.focus();
  };
  window.addEventListener("resize", position);
  return {
    upsert(data) {
      if (data.id !== "example") projects.set(data.id, data);
      const active = current();
      if (active) {
        button.querySelector("span").textContent = active.name;
        button.title = active.name;
        button.setAttribute("aria-label", `Switch project: ${active.name}`);
      }
      render();
    },
    loading(value) {
      button.setAttribute("aria-busy", String(value));
    },
    destroy() {
      window.removeEventListener("resize", position);
    },
  };
}
