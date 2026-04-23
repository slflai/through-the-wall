// Through the Wall — frontend logic.
// Talks to Python via window.pywebview.api.*

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  items: [],
  sourceTitle: "",
  categoryTree: [],
  recent: [],
  libraryPath: "",
  librarySelected: new Set(),  // abs_paths of selected files
  libraryLastClicked: null,     // abs_path, for shift+click range
  libraryLastItems: [],          // array of {abs_path, name} in display order
};

// ---------- Tab switching ----------
$$(".tab").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});
function switchView(name) {
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach(v => v.classList.toggle("active", v.dataset.view === name));
  if (name === "library") loadLibrary(state.libraryPath);
  if (name === "settings") loadSettings();
}

// ---------- Toast ----------
let toastTimer = null;
function toast(msg, kind = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast " + kind;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3000);
}

// ---------- Wait for pywebview ready ----------
function whenReady(fn) {
  if (window.pywebview && window.pywebview.api) return fn();
  window.addEventListener("pywebviewready", fn, { once: true });
}

// ---------- Fetch preview ----------
$("#fetch-btn").addEventListener("click", doFetch);
$("#url-input").addEventListener("keydown", e => { if (e.key === "Enter") doFetch(); });

async function doFetch() {
  const url = $("#url-input").value.trim();
  if (!url) return;

  const statusEl = $("#fetch-status");
  statusEl.classList.remove("hidden", "error");
  statusEl.textContent = "解析中…（第一次可能會慢，需要讀 Chrome cookie）";
  $("#preview-panel").classList.add("hidden");

  try {
    const res = await window.pywebview.api.fetch_preview(url);
    if (!res.items || res.items.length === 0) {
      statusEl.classList.add("error");
      statusEl.textContent = "抓取失敗：" + (res.error || "unknown");
      return;
    }
    statusEl.classList.add("hidden");
    state.items = res.items.map((it, i) => ({
      ...it,
      _id: `item-${i}`,
      selected: true,
      filename: it.suggested_filename || `item_${i + 1}`,
    }));
    state.sourceTitle = res.source_title || "";
    renderPreview();
    await refreshCategories();
  } catch (e) {
    statusEl.classList.add("error");
    statusEl.textContent = "例外：" + e;
  }
}

function renderPreview() {
  $("#preview-panel").classList.remove("hidden");
  $("#source-title").textContent = state.sourceTitle;
  $("#select-all").checked = state.items.every(i => i.selected);

  const container = $("#items");
  container.innerHTML = "";
  state.items.forEach(it => container.appendChild(renderItem(it)));
  updateCount();
}

function renderItem(item) {
  const el = document.createElement("div");
  el.className = "item" + (item.selected ? " selected" : "");
  el.dataset.id = item._id;

  el.innerHTML = `
    <div class="thumb-wrap">
      <div class="check-overlay">
        <input type="checkbox" ${item.selected ? "checked" : ""} />
      </div>
      <div class="kind-badge">${item.kind}</div>
      <div class="placeholder">載入中…</div>
    </div>
    <div class="filename-row">
      <input type="text" value="${escapeAttr(item.filename)}" />
      <span class="ext-label">.${item.ext}</span>
    </div>
  `;

  const thumbWrap = $(".thumb-wrap", el);
  loadThumbnail(item).then(dataUrl => {
    if (!dataUrl) { $(".placeholder", thumbWrap).textContent = "無預覽"; return; }
    $(".placeholder", thumbWrap)?.remove();
    const tag = item.kind === "video" ? document.createElement("video") : document.createElement("img");
    tag.src = dataUrl;
    if (tag.tagName === "VIDEO") { tag.muted = true; tag.loop = true; tag.playsInline = true; tag.autoplay = true; }
    thumbWrap.insertBefore(tag, $(".kind-badge", thumbWrap));
  });

  const setSelected = (val) => {
    item.selected = val;
    el.classList.toggle("selected", val);
    $(".check-overlay input", el).checked = val;
    $("#select-all").checked = state.items.every(i => i.selected);
    updateCount();
  };

  // Click anywhere on the card toggles selection, except on the filename input
  el.addEventListener("click", e => {
    if (e.target.closest(".filename-row")) return;
    if (e.target.matches('.check-overlay input')) return;  // let checkbox fire its own change
    setSelected(!item.selected);
  });

  $(".check-overlay input", el).addEventListener("change", e => {
    e.stopPropagation();
    setSelected(e.target.checked);
  });
  $(".filename-row input", el).addEventListener("input", e => { item.filename = e.target.value; });
  $(".filename-row input", el).addEventListener("click", e => e.stopPropagation());

  return el;
}

async function loadThumbnail(item) {
  const url = item.thumbnail || item.url;
  if (!url) return null;
  if (item.kind === "video" && url === item.url) return null;
  try {
    const res = await window.pywebview.api.proxy_image(url);
    return res.ok ? res.data_url : null;
  } catch { return null; }
}

function updateCount() {
  const n = state.items.filter(i => i.selected).length;
  $("#item-count").textContent = `${n} / ${state.items.length} 選中`;
  $("#save-btn").disabled = n === 0;
  $("#save-btn").textContent = `儲存 (${n})`;
}

$("#select-all").addEventListener("change", e => {
  state.items.forEach(i => i.selected = e.target.checked);
  renderPreview();
});

// ---------- Categories ----------
async function refreshCategories() {
  const res = await window.pywebview.api.list_categories();
  state.categoryTree = res.tree || [];
  state.recent = res.recent || [];
  renderRecentChips();
}

function flattenTree(tree) {
  const out = [];
  const walk = nodes => {
    for (const n of nodes) {
      out.push(n.path);
      if (n.children?.length) walk(n.children);
    }
  };
  walk(tree);
  return out;
}

function renderRecentChips() {
  const row = $("#recent-chips");
  row.innerHTML = "";
  state.recent.slice(0, 6).forEach(c => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `<span class="chip-label">${escapeHtml(c)}</span><button class="chip-x" title="從最近移除">×</button>`;
    $(".chip-label", chip).addEventListener("click", () => { $("#category-input").value = c; });
    $(".chip-x", chip).addEventListener("click", async e => {
      e.stopPropagation();
      await window.pywebview.api.forget_category(c);
      await refreshCategories();
    });
    row.appendChild(chip);
  });
}

const catInput = $("#category-input");
const catSugs = $("#category-suggestions");

catInput.addEventListener("input", updateSuggestions);
catInput.addEventListener("focus", updateSuggestions);
catInput.addEventListener("blur", () => setTimeout(() => catSugs.classList.add("hidden"), 150));

function updateSuggestions() {
  const q = catInput.value.trim().toLowerCase();
  const all = flattenTree(state.categoryTree);
  const matches = q ? all.filter(p => p.toLowerCase().includes(q)) : all.slice(0, 20);
  catSugs.innerHTML = "";
  matches.slice(0, 20).forEach(p => {
    const el = document.createElement("div");
    el.className = "sug";
    el.innerHTML = `<span>${escapeHtml(p)}</span>`;
    el.addEventListener("mousedown", () => { catInput.value = p; catSugs.classList.add("hidden"); });
    catSugs.appendChild(el);
  });
  if (q && !all.some(p => p.toLowerCase() === q)) {
    const el = document.createElement("div");
    el.className = "sug";
    el.innerHTML = `<span>${escapeHtml(q)}</span><span class="create-mark">+ 新增</span>`;
    el.addEventListener("mousedown", () => { catInput.value = q; catSugs.classList.add("hidden"); });
    catSugs.appendChild(el);
  }
  catSugs.classList.toggle("hidden", catSugs.children.length === 0);
}

// ---------- Save ----------
$("#save-btn").addEventListener("click", doSave);

async function doSave() {
  const category = catInput.value.trim();
  const selected = state.items.filter(i => i.selected);
  if (selected.length === 0) return;

  const saveBtn = $("#save-btn");
  saveBtn.disabled = true;
  saveBtn.textContent = "儲存中…";

  const payload = selected.map(i => ({
    url: i.url,
    ext: i.ext,
    kind: i.kind,
    filename: i.filename,
    suggested_filename: i.suggested_filename,
    _source: i._source,
    _yt_url: i._yt_url,
    _referer: i._referer,
  }));

  try {
    const res = await window.pywebview.api.download_many(payload, category);
    if (category) await window.pywebview.api.remember_category(category);
    if (res.failed > 0) {
      toast(`${res.ok} 成功 · ${res.failed} 失敗`, "error");
      console.warn("Failures:", res.results.filter(r => !r.ok));
    } else {
      toast(`已儲存 ${res.ok} 個檔案 到 ${category || "(根目錄)"}`, "ok");
    }
    await refreshCategories();
  } catch (e) {
    toast("儲存失敗：" + e, "error");
  } finally {
    saveBtn.disabled = false;
    updateCount();
  }
}

// ---------- Library view ----------
async function loadLibrary(path) {
  state.libraryPath = path;
  renderBreadcrumb(path);
  const treeRes = await window.pywebview.api.list_categories();
  state.categoryTree = treeRes.tree || [];
  renderTree(state.categoryTree);
  const data = await window.pywebview.api.list_library(path);
  renderGrid(data);
}

function renderBreadcrumb(path) {
  const el = $("#breadcrumb");
  el.innerHTML = "";
  const root = document.createElement("span");
  root.className = "bc";
  root.textContent = "根目錄";
  root.addEventListener("click", () => loadLibrary(""));
  el.appendChild(root);
  if (path) {
    const parts = path.split("/");
    let accum = "";
    parts.forEach(p => {
      accum = accum ? `${accum}/${p}` : p;
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "›";
      el.appendChild(sep);
      const node = document.createElement("span");
      node.className = "bc";
      node.textContent = p;
      const target = accum;
      node.addEventListener("click", () => loadLibrary(target));
      el.appendChild(node);
    });
  }
}

function renderTree(tree) {
  const el = $("#category-tree");
  el.innerHTML = "";
  const rootEl = document.createElement("div");
  rootEl.className = "tree-node" + (state.libraryPath === "" ? " active" : "");
  rootEl.textContent = "全部";
  rootEl.dataset.path = "";
  rootEl.addEventListener("click", () => loadLibrary(""));
  addDropTarget(rootEl, "");
  el.appendChild(rootEl);
  el.appendChild(buildTreeDom(tree));
}

function buildTreeDom(nodes) {
  const wrap = document.createElement("div");
  for (const n of nodes) {
    const node = document.createElement("div");
    node.className = "tree-node" + (state.libraryPath === n.path ? " active" : "");
    node.textContent = "📁 " + n.name;
    node.dataset.path = n.path;
    node.addEventListener("click", () => loadLibrary(n.path));
    node.addEventListener("contextmenu", e => {
      e.preventDefault();
      showFolderMenu(e, n);
    });
    addDropTarget(node, n.path);
    wrap.appendChild(node);
    if (n.children?.length) {
      const kids = document.createElement("div");
      kids.className = "tree-children";
      kids.appendChild(buildTreeDom(n.children));
      wrap.appendChild(kids);
    }
  }
  return wrap;
}

function renderGrid(data) {
  const grid = $("#library-grid");
  grid.innerHTML = "";

  // Clear selection when navigating to a new folder
  state.librarySelected.clear();
  state.libraryLastClicked = null;
  state.libraryLastItems = (data.items || []).map(f => ({ abs_path: f.abs_path, name: f.name }));
  updateSelectionBar();

  for (const f of data.subfolders || []) {
    const el = document.createElement("div");
    el.className = "lib-item folder";
    el.innerHTML = `<div class="thumb">📁</div><div class="name">${escapeHtml(f.name)}</div>`;
    el.addEventListener("click", () => loadLibrary(f.path));
    el.addEventListener("contextmenu", e => { e.preventDefault(); showFolderMenu(e, f); });
    addDropTarget(el, f.path);
    grid.appendChild(el);
  }

  for (const f of data.items || []) {
    const el = document.createElement("div");
    el.className = "lib-item";
    el.draggable = true;
    el.dataset.absPath = f.abs_path;
    el.innerHTML = `<div class="thumb">🖼️</div><div class="name">${escapeHtml(f.name)}</div>`;

    el.addEventListener("click", e => handleFileClick(e, f, el));
    el.addEventListener("dblclick", () => window.pywebview.api.reveal_in_finder(f.abs_path));
    el.addEventListener("contextmenu", e => {
      e.preventDefault();
      // If right-clicking an unselected item, select it first (clearing others)
      if (!state.librarySelected.has(f.abs_path)) {
        state.librarySelected.clear();
        state.librarySelected.add(f.abs_path);
        applySelectionClasses();
      }
      if (state.librarySelected.size > 1) showBatchFileMenu(e);
      else showFileMenu(e, f);
    });
    el.addEventListener("dragstart", e => {
      // If dragging an unselected item, drag just that one; if selected, drag the whole set
      if (!state.librarySelected.has(f.abs_path)) {
        state.librarySelected.clear();
        state.librarySelected.add(f.abs_path);
        applySelectionClasses();
      }
      el.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", JSON.stringify({
        type: "files",
        abs_paths: [...state.librarySelected],
      }));
    });
    el.addEventListener("dragend", () => el.classList.remove("dragging"));

    const thumb = $(".thumb", el);
    loadLocalThumb(f.abs_path, f.name).then(dataUrl => {
      if (!dataUrl) return;
      thumb.innerHTML = "";
      const lower = f.name.toLowerCase();
      const isVid = lower.endsWith(".mp4") || lower.endsWith(".mov") || lower.endsWith(".webm");
      const tag = isVid ? document.createElement("video") : document.createElement("img");
      tag.src = dataUrl;
      if (isVid) { tag.muted = true; tag.playsInline = true; }
      thumb.appendChild(tag);
    });

    grid.appendChild(el);
  }

  if (!grid.children.length) {
    grid.innerHTML = '<div class="empty-state">這個分類還沒有東西</div>';
  }
}

function handleFileClick(e, file, el) {
  const cmd = e.metaKey || e.ctrlKey;
  if (e.shiftKey && state.libraryLastClicked) {
    // Range selection
    const items = state.libraryLastItems;
    const a = items.findIndex(i => i.abs_path === state.libraryLastClicked);
    const b = items.findIndex(i => i.abs_path === file.abs_path);
    if (a !== -1 && b !== -1) {
      const [from, to] = a < b ? [a, b] : [b, a];
      for (let i = from; i <= to; i++) state.librarySelected.add(items[i].abs_path);
    }
  } else if (cmd) {
    // Toggle
    if (state.librarySelected.has(file.abs_path)) state.librarySelected.delete(file.abs_path);
    else state.librarySelected.add(file.abs_path);
    state.libraryLastClicked = file.abs_path;
  } else {
    // Single select
    state.librarySelected.clear();
    state.librarySelected.add(file.abs_path);
    state.libraryLastClicked = file.abs_path;
  }
  applySelectionClasses();
}

function applySelectionClasses() {
  $$(".lib-item", $("#library-grid")).forEach(el => {
    const abs = el.dataset.absPath;
    if (!abs) return;
    el.classList.toggle("selected", state.librarySelected.has(abs));
  });
  updateSelectionBar();
}

function updateSelectionBar() {
  const bar = $("#selection-bar");
  const n = state.librarySelected.size;
  if (n === 0) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  $("#selection-count").textContent = `已選取 ${n} 個檔案`;
}

$("#batch-clear-btn").addEventListener("click", () => {
  state.librarySelected.clear();
  applySelectionClasses();
});
$("#batch-delete-btn").addEventListener("click", batchDelete);
$("#batch-move-btn").addEventListener("click", batchMove);

async function batchDelete() {
  const paths = [...state.librarySelected];
  if (!paths.length) return;
  if (!confirm(`確定刪除這 ${paths.length} 個檔案？`)) return;
  let ok = 0, fail = 0;
  for (const p of paths) {
    const r = await window.pywebview.api.delete_file(p);
    r.ok ? ok++ : fail++;
  }
  toast(`刪除 ${ok} 個${fail ? `，${fail} 個失敗` : ""}`, fail ? "error" : "ok");
  state.librarySelected.clear();
  loadLibrary(state.libraryPath);
}

async function batchMove() {
  const paths = [...state.librarySelected];
  if (!paths.length) return;
  const picked = await pickFolder(`移動 ${paths.length} 個檔案到…`, null);
  if (picked === null) return;
  let ok = 0, fail = 0;
  for (const p of paths) {
    const r = await window.pywebview.api.move_file(p, picked);
    r.ok ? ok++ : fail++;
  }
  toast(`移動 ${ok} 個${fail ? `，${fail} 個失敗` : ""}`, fail ? "error" : "ok");
  state.librarySelected.clear();
  loadLibrary(state.libraryPath);
}

function showBatchFileMenu(e) {
  const n = state.librarySelected.size;
  showContextMenu(e.clientX, e.clientY, [
    { label: `移動 ${n} 個到…`, action: batchMove },
    { sep: true },
    { label: `刪除 ${n} 個`, danger: true, action: batchDelete },
  ]);
}

async function loadLocalThumb(abs_path) {
  try {
    const res = await window.pywebview.api.read_file_as_data_url(abs_path);
    return res.ok ? res.data_url : null;
  } catch { return null; }
}

// Drag-drop: drop file(s) onto folder → move them to that category
function addDropTarget(el, targetPath) {
  el.addEventListener("dragover", e => {
    if (!e.dataTransfer.types.includes("text/plain")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    el.classList.add("drop-target");
  });
  el.addEventListener("dragleave", () => el.classList.remove("drop-target"));
  el.addEventListener("drop", async e => {
    e.preventDefault();
    el.classList.remove("drop-target");
    try {
      const data = JSON.parse(e.dataTransfer.getData("text/plain"));
      const paths = data.abs_paths || (data.abs_path ? [data.abs_path] : []);
      if (!paths.length) return;
      let ok = 0, fail = 0;
      for (const p of paths) {
        const res = await window.pywebview.api.move_file(p, targetPath);
        res.ok ? ok++ : fail++;
      }
      toast(`移動 ${ok} 個${fail ? `，${fail} 個失敗` : ""}`, fail ? "error" : "ok");
      state.librarySelected.clear();
      loadLibrary(state.libraryPath);
    } catch {}
  });
}

// ---------- Library marquee (drag-to-select rectangle) ----------
(() => {
  const grid = $("#library-grid");
  let start = null;       // { x, y } in viewport coords
  let rectEl = null;
  let baseSelection = new Set();  // selection before drag (to additive-merge with marquee)
  let additive = false;

  grid.addEventListener("mousedown", e => {
    // Only start marquee when clicking empty grid space (not an item)
    if (e.target.closest(".lib-item")) return;
    if (e.button !== 0) return;
    start = { x: e.clientX, y: e.clientY };
    additive = e.metaKey || e.ctrlKey || e.shiftKey;
    baseSelection = additive ? new Set(state.librarySelected) : new Set();
    e.preventDefault();
  });

  document.addEventListener("mousemove", e => {
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (!rectEl && Math.hypot(dx, dy) < 4) return;  // too small — not a drag yet
    if (!rectEl) {
      rectEl = document.createElement("div");
      rectEl.className = "marquee-rect";
      document.body.appendChild(rectEl);
    }
    const x = Math.min(start.x, e.clientX);
    const y = Math.min(start.y, e.clientY);
    const w = Math.abs(dx);
    const h = Math.abs(dy);
    Object.assign(rectEl.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });

    // Live-update selection based on intersection
    const next = new Set(baseSelection);
    $$(".lib-item[data-abs-path]", grid).forEach(item => {
      const r = item.getBoundingClientRect();
      const hit = !(r.right < x || r.left > x + w || r.bottom < y || r.top > y + h);
      if (hit) next.add(item.dataset.absPath);
    });
    state.librarySelected = next;
    applySelectionClasses();
  });

  document.addEventListener("mouseup", () => {
    if (!start) return;
    start = null;
    if (rectEl) { rectEl.remove(); rectEl = null; }
    else {
      // No actual drag — treat as a click on empty space → deselect
      if (!additive) {
        state.librarySelected.clear();
        applySelectionClasses();
      }
    }
  });
})();

// ---------- Context menu ----------
const ctxMenu = $("#ctx-menu");

function showContextMenu(x, y, items) {
  ctxMenu.innerHTML = "";
  for (const it of items) {
    if (it.sep) {
      const sep = document.createElement("div");
      sep.className = "ctx-sep";
      ctxMenu.appendChild(sep);
      continue;
    }
    const el = document.createElement("div");
    el.className = "ctx-item" + (it.danger ? " danger" : "");
    el.textContent = it.label;
    el.addEventListener("click", () => { hideContextMenu(); it.action(); });
    ctxMenu.appendChild(el);
  }
  ctxMenu.classList.remove("hidden");
  const rect = ctxMenu.getBoundingClientRect();
  const finalX = Math.min(x, window.innerWidth - rect.width - 8);
  const finalY = Math.min(y, window.innerHeight - rect.height - 8);
  ctxMenu.style.left = finalX + "px";
  ctxMenu.style.top = finalY + "px";
}
function hideContextMenu() { ctxMenu.classList.add("hidden"); }
document.addEventListener("click", e => { if (!ctxMenu.contains(e.target)) hideContextMenu(); });
document.addEventListener("scroll", hideContextMenu, true);
window.addEventListener("blur", hideContextMenu);

function showFileMenu(e, file) {
  showContextMenu(e.clientX, e.clientY, [
    { label: "在 Finder 顯示", action: () => window.pywebview.api.reveal_in_finder(file.abs_path) },
    { label: "重新命名…", action: () => renameFileFlow(file) },
    { label: "移動到…", action: () => moveFileFlow(file) },
    { sep: true },
    { label: "刪除", danger: true, action: () => deleteFileFlow(file) },
  ]);
}

function showFolderMenu(e, folder) {
  showContextMenu(e.clientX, e.clientY, [
    { label: "進入", action: () => loadLibrary(folder.path) },
    { label: "新增子分類…", action: () => newSubfolderFlow(folder) },
    { label: "重新命名…", action: () => renameFolderFlow(folder) },
    { label: "移動到…", action: () => moveFolderFlow(folder) },
    { sep: true },
    { label: "刪除", danger: true, action: () => deleteFolderFlow(folder) },
  ]);
}

async function renameFileFlow(file) {
  const newName = prompt("新檔名（含副檔名）：", file.name);
  if (!newName || newName === file.name) return;
  const res = await window.pywebview.api.rename_file(file.abs_path, newName);
  if (res.ok) { toast("已重新命名", "ok"); loadLibrary(state.libraryPath); }
  else toast("重新命名失敗：" + res.error, "error");
}

async function deleteFileFlow(file) {
  if (!confirm(`確定刪除 ${file.name}？`)) return;
  const res = await window.pywebview.api.delete_file(file.abs_path);
  if (res.ok) { toast("已刪除", "ok"); loadLibrary(state.libraryPath); }
  else toast("刪除失敗：" + res.error, "error");
}

async function moveFileFlow(file) {
  const picked = await pickFolder(`移動「${file.name}」到…`, null);
  if (picked === null) return;
  const res = await window.pywebview.api.move_file(file.abs_path, picked);
  if (res.ok) { toast("已移動", "ok"); loadLibrary(state.libraryPath); }
  else toast("移動失敗：" + res.error, "error");
}

async function renameFolderFlow(folder) {
  const currentName = folder.name || folder.path.split("/").pop();
  const newName = prompt("新分類名稱：", currentName);
  if (!newName || newName === currentName) return;
  const res = await window.pywebview.api.rename_folder(folder.path, newName);
  if (res.ok) { toast("已重新命名", "ok"); loadLibrary(state.libraryPath); }
  else toast("重新命名失敗：" + res.error, "error");
}

async function deleteFolderFlow(folder) {
  if (!confirm(`確定刪除分類「${folder.path}」？`)) return;
  let res = await window.pywebview.api.delete_folder(folder.path, false);
  if (!res.ok && res.not_empty) {
    if (!confirm("這個資料夾裡還有檔案，確定要連同內容一起刪除？")) return;
    res = await window.pywebview.api.delete_folder(folder.path, true);
  }
  if (res.ok) {
    toast("已刪除", "ok");
    const parent = folder.path.includes("/") ? folder.path.split("/").slice(0, -1).join("/") : "";
    loadLibrary(state.libraryPath.startsWith(folder.path) ? parent : state.libraryPath);
  } else {
    toast("刪除失敗：" + res.error, "error");
  }
}

async function moveFolderFlow(folder) {
  const picked = await pickFolder(`移動「${folder.name || folder.path}」到…`, folder.path);
  if (picked === null) return;
  const res = await window.pywebview.api.move_folder(folder.path, picked);
  if (res.ok) { toast("已移動", "ok"); loadLibrary(state.libraryPath); }
  else toast("移動失敗：" + res.error, "error");
}

async function newSubfolderFlow(folder) {
  const name = prompt("新子分類名稱：");
  if (!name) return;
  const path = folder.path ? `${folder.path}/${name}` : name;
  const res = await window.pywebview.api.create_category(path);
  if (res.ok) { toast("已新增", "ok"); loadLibrary(state.libraryPath); }
  else toast("新增失敗：" + res.error, "error");
}

$("#new-root-folder-btn").addEventListener("click", async () => {
  const name = prompt("新分類名稱：");
  if (!name) return;
  const res = await window.pywebview.api.create_category(name);
  if (res.ok) { toast("已新增", "ok"); loadLibrary(state.libraryPath); }
  else toast("新增失敗：" + res.error, "error");
});

// ---------- Folder picker modal ----------
const modal = $("#modal");
let modalResolver = null;
let modalPicked = null;

function pickFolder(title, excludePath) {
  return new Promise(async resolve => {
    modalResolver = resolve;
    modalPicked = "";
    $("#modal-title").textContent = title;

    const res = await window.pywebview.api.list_categories();
    const body = $("#modal-body");
    body.innerHTML = "";

    const rootRow = document.createElement("div");
    rootRow.className = "picker-row selected";
    rootRow.textContent = "📁 (根目錄)";
    rootRow.addEventListener("click", () => selectPicker(rootRow, ""));
    body.appendChild(rootRow);

    const flat = [];
    const walk = (nodes, depth) => {
      for (const n of nodes) {
        flat.push({ path: n.path, name: n.name, depth });
        if (n.children?.length) walk(n.children, depth + 1);
      }
    };
    walk(res.tree || [], 0);

    for (const n of flat) {
      if (excludePath && (n.path === excludePath || n.path.startsWith(excludePath + "/"))) continue;
      const row = document.createElement("div");
      row.className = "picker-row";
      row.style.paddingLeft = (12 + n.depth * 18) + "px";
      row.textContent = "📁 " + n.path;
      row.addEventListener("click", () => selectPicker(row, n.path));
      body.appendChild(row);
    }

    modal.classList.remove("hidden");
  });
}

function selectPicker(row, path) {
  $$(".picker-row", modal).forEach(r => r.classList.remove("selected"));
  row.classList.add("selected");
  modalPicked = path;
}

function closeModal(result) {
  modal.classList.add("hidden");
  if (modalResolver) { modalResolver(result); modalResolver = null; }
}
$("#modal-cancel").addEventListener("click", () => closeModal(null));
$("#modal-close").addEventListener("click", () => closeModal(null));
$("#modal-confirm").addEventListener("click", () => closeModal(modalPicked));
modal.addEventListener("click", e => { if (e.target === modal) closeModal(null); });

// ---------- Settings ----------
async function loadSettings() {
  const cfg = await window.pywebview.api.get_config();
  $("#save-path-input").value = cfg.save_path || "";
}
$("#save-path-btn").addEventListener("click", async () => {
  const path = $("#save-path-input").value.trim();
  const res = await window.pywebview.api.set_save_path(path);
  if (res.ok) toast("儲存位置已更新", "ok");
  else toast("更新失敗：" + res.error, "error");
});

// ---------- Helpers ----------
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/"/g, "&quot;"); }

// ---------- Init ----------
whenReady(() => {
  refreshCategories().catch(() => {});
});
