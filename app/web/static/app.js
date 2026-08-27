// 印前生成页前端逻辑：拉配置、动态上传区、提交生成、WS 进度展示、下载

const state = {
    types: [],
    sizes: [],
    params: null,
    placeholders: [],     // 占位符变量名列表
    imagePaths: {},       // zone_name -> uploaded image_path
};

// ---- DOM ----
const typeSelect = document.getElementById("type-select");
const sizeSelect = document.getElementById("size-select");
const zonesContainer = document.getElementById("zones-container");
const varsContainer = document.getElementById("vars-container");
const generateBtn = document.getElementById("generate-btn");

// ---- 自定义下拉框 ----
// 把原生 <select> 隐藏，渲染一个按钮 + 弹出列表；选中同步写回 <select> 并触发 change。

function initSelect(selectEl, placeholder) {
    if (selectEl.dataset.ready === "1") return;
    selectEl.dataset.ready = "1";
    selectEl.classList.add("sel-native");

    const wrap = document.createElement("div");
    wrap.className = "sel";
    wrap.dataset.id = selectEl.id;
    selectEl.parentNode.insertBefore(wrap, selectEl);
    wrap.appendChild(selectEl);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sel-btn";
    btn.innerHTML = `<span class="sel-val">${placeholder}</span><svg class="sel-caret" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

    const menu = document.createElement("div");
    menu.className = "sel-menu";
    menu.setAttribute("role", "listbox");

    wrap.appendChild(btn);
    wrap.appendChild(menu);

    btn.addEventListener("click", e => {
        e.stopPropagation();
        const open = wrap.classList.contains("is-open");
        closeAllSelects();
        if (!open) {
            rebuildSelectMenu(selectEl, menu);
            wrap.classList.add("is-open");
            menu.scrollTop = menu.querySelector(".is-selected")?.offsetTop - 40 || 0;
        }
    });
    selectEl.addEventListener("change", () => syncSelectBtn(selectEl, btn, placeholder));
    document.addEventListener("click", () => closeAllSelects());
}

function rebuildSelectMenu(selectEl, menu) {
    menu.innerHTML = "";
    Array.from(selectEl.options).forEach(opt => {
        const item = document.createElement("div");
        item.className = "sel-opt" + (opt.selected ? " is-selected" : "");
        item.setAttribute("role", "option");
        item.textContent = opt.textContent;
        item.dataset.value = opt.value;
        item.addEventListener("click", e => {
            e.stopPropagation();
            selectEl.value = opt.value;
            selectEl.dispatchEvent(new Event("change"));
            closeAllSelects();
        });
        menu.appendChild(item);
    });
}

function syncSelectBtn(selectEl, btn, placeholder) {
    const opt = selectEl.options[selectEl.selectedIndex];
    btn.querySelector(".sel-val").textContent = opt && opt.value ? opt.textContent : placeholder;
    btn.classList.toggle("has-value", !!(opt && opt.value));
}

function closeAllSelects() {
    document.querySelectorAll(".sel.is-open").forEach(w => w.classList.remove("is-open"));
}

// ---- 配置加载 ----

async function loadTypes() {
    const res = await fetch("/api/types");
    state.types = await res.json();
    typeSelect.innerHTML = '<option value="">-- 选择 --</option>' +
        state.types.map(t => `<option value="${t.id}">${t.name}</option>`).join("");
    initSelect(typeSelect, "选择类型");
    syncSelectBtn(typeSelect, typeSelect.closest(".sel").querySelector(".sel-btn"), "选择类型");
}

async function loadSizes(typeId) {
    const res = await fetch(`/api/sizes/${typeId}`);
    state.sizes = await res.json();
    sizeSelect.innerHTML = '<option value="">-- 选择 --</option>' +
        state.sizes.map(s => `<option value="${s.id}">${s.name}</option>`).join("");
    sizeSelect.disabled = false;
    initSelect(sizeSelect, "选择尺码");
    // 选类型切换后重置尺码按钮
    const wrap = sizeSelect.closest(".sel");
    if (wrap) {
        wrap.classList.toggle("is-disabled", false);
        syncSelectBtn(sizeSelect, wrap.querySelector(".sel-btn"), "选择尺码");
    }
}

async function loadParams(typeId, sizeId) {
    const res = await fetch(`/api/params/${typeId}/${sizeId}`);
    const data = await res.json();
    state.params = data.params;
    state.placeholders = data.placeholders || [];
    renderZones();
    renderVars();
}

function renderVars() {
    // 按占位符变量名渲染独立输入框；无占位符则隐藏
    if (state.placeholders.length === 0) {
        varsContainer.innerHTML = "";
        return;
    }
    varsContainer.innerHTML = `<div class="block-label">命名变量</div><div class="form-row">` +
        state.placeholders.map(name => `
            <label class="field">
                <span class="field-label">${name}</span>
                <input type="text" data-var="${name}" placeholder="${name}">
            </label>
        `).join("") + `</div>`;
}

function renderZones() {
    // 只渲染图片区（type=image）
    const imageZones = (state.params?.zones || []).filter(z => z.type === "image");
    if (imageZones.length === 0) {
        zonesContainer.innerHTML = `<div class="empty">该尺码配置无图片区。</div>`;
        updateGenerateBtn();
        return;
    }
    zonesContainer.innerHTML = imageZones.map(z => `
        <div class="zone-upload" data-zone="${z.name}">
            <div class="zone-name">${z.name}</div>
            <label class="dropzone">
                <input type="file" accept="image/*" data-zone="${z.name}" hidden>
                <svg class="dropzone-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 16V4M12 4l-4 4M12 4l4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
                <span class="dropzone-hint">点击选择或拖入图片</span>
                <span class="dropzone-sub">支持 PNG / JPG / TIF</span>
            </label>
            <button type="button" class="zone-pick" data-zone="${z.name}">从文件库选择</button>
            <div class="file-info">未选择文件</div>
        </div>
    `).join("");
    // 绑定上传 + 拖拽
    zonesContainer.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener("change", e => handleUpload(e.target));
        const dz = input.closest(".dropzone");
        dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("is-drag"); });
        dz.addEventListener("dragleave", () => dz.classList.remove("is-drag"));
        dz.addEventListener("drop", e => {
            e.preventDefault();
            dz.classList.remove("is-drag");
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                handleUpload(input);
            }
        });
    });
    // 绑定"从文件库选择"
    zonesContainer.querySelectorAll(".zone-pick").forEach(btn => {
        btn.addEventListener("click", () => openPicker(btn.dataset.zone));
    });
    updateGenerateBtn();
}

// ---- 上传 ----

// 把已入库的图应用到某个 zone（上传成功 / 文件库选择共用）
function applyImageToZone(zoneName, { path, previewUrl, name, sub }) {
    const card = zonesContainer.querySelector(`.zone-upload[data-zone="${zoneName}"]`);
    if (!card) return;
    const dz = card.querySelector(".dropzone");
    state.imagePaths[zoneName] = path;
    card.classList.add("has-file");
    dz.classList.remove("is-loading");
    dz.classList.add("has-preview");
    dz.style.setProperty("--preview", `url("${previewUrl}")`);
    dz.querySelector(".dropzone-hint").textContent = name;
    dz.querySelector(".dropzone-sub").textContent = sub;
    card.querySelector(".file-info").textContent = name;
    updateGenerateBtn();
}

async function handleUpload(input) {
    const zoneName = input.dataset.zone;
    const file = input.files[0];
    if (!file) return;
    const card = input.closest(".zone-upload");
    const dz = card.querySelector(".dropzone");

    // 即时本地预览 + 上传中态
    const previewUrl = URL.createObjectURL(file);
    dz.classList.add("is-loading");
    dz.querySelector(".dropzone-hint").textContent = "上传中…";
    card.querySelector(".file-info").textContent = `${file.name} (${(file.size/1024/1024).toFixed(1)}MB)`;

    const fd = new FormData();
    fd.append("file", file);
    try {
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "上传失败");
        applyImageToZone(zoneName, {
            path: data.path,
            previewUrl,
            name: file.name,
            sub: `${(file.size/1024/1024).toFixed(1)} MB · 点击更换`,
        });
    } catch (e) {
        dz.classList.remove("is-loading");
        dz.querySelector(".dropzone-hint").textContent = "点击选择或拖入图片";
        dz.querySelector(".dropzone-sub").textContent = "支持 PNG / JPG / TIF";
        card.querySelector(".file-info").textContent = "上传失败";
        alert("上传失败: " + e.message);
    }
    updateGenerateBtn();
}

function updateGenerateBtn() {
    const imageZones = (state.params?.zones || []).filter(z => z.type === "image");
    const allUploaded = imageZones.length > 0 &&
        imageZones.every(z => state.imagePaths[z.name]);
    generateBtn.disabled = !allUploaded;
}

// ---- 文件库选择器 ----

let pickerModal = null;
let pickerZone = "";
let pickerSearchTimer = null;

function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}
function fmtLibSize(n) {
    if (!n) return "?";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
}

function ensurePicker() {
    if (pickerModal) return pickerModal;
    pickerModal = document.createElement("div");
    pickerModal.className = "modal picker-modal";
    pickerModal.hidden = true;
    pickerModal.innerHTML = `
        <div class="modal-card modal-card--wide">
            <div class="card-head">
                <h2>从文件库选择</h2>
                <button type="button" class="modal-close" aria-label="关闭">×</button>
            </div>
            <div class="modal-body">
                <input type="text" class="picker-search" placeholder="搜索文件名…">
                <div class="picker-grid lib-grid"></div>
            </div>
        </div>`;
    document.body.appendChild(pickerModal);
    pickerModal.querySelector(".modal-close").addEventListener("click", closePicker);
    pickerModal.addEventListener("click", e => { if (e.target === pickerModal) closePicker(); });
    pickerModal.querySelector(".picker-search").addEventListener("input", e => {
        clearTimeout(pickerSearchTimer);
        pickerSearchTimer = setTimeout(() => loadPickerList(e.target.value.trim()), 250);
    });
    return pickerModal;
}

function openPicker(zoneName) {
    pickerZone = zoneName;
    ensurePicker();
    pickerModal.hidden = false;
    pickerModal.querySelector(".picker-search").value = "";
    loadPickerList("");
}

function closePicker() {
    if (pickerModal) pickerModal.hidden = true;
    pickerZone = "";
}

async function loadPickerList(q) {
    const grid = pickerModal.querySelector(".picker-grid");
    grid.innerHTML = `<div class="empty">加载中…</div>`;
    const params = new URLSearchParams({ limit: "200" });
    if (q) params.set("q", q);
    let res;
    try {
        res = await fetch("/api/library?" + params.toString());
    } catch {
        grid.innerHTML = `<div class="empty">网络错误</div>`;
        return;
    }
    const data = await res.json();
    const items = data.items || [];
    if (items.length === 0) {
        grid.innerHTML = `<div class="empty">没有符合条件的文件。</div>`;
        return;
    }
    grid.innerHTML = items.map(it => `
        <div class="lib-card picker-card" data-id="${it.id}">
            <div class="lib-thumb" style="background-image:url('/api/library/${it.id}/thumb')"></div>
            <div class="lib-meta">
                <div class="lib-name" title="${escapeHtml(it.original_name)}">${escapeHtml(it.original_name)}</div>
                <div class="lib-row">
                    <span class="lib-tag lib-tag-${it.source}">${({upload:"上传",prepress:"印前产物",impose:"排版产物"})[it.source] || it.source}</span>
                    <span class="lib-tag lib-tag-fmt">${(it.format || "").toUpperCase() || "?"}</span>
                </div>
                <div class="lib-row">
                    <span class="lib-kv"><span class="lib-k">尺寸</span><span class="lib-v">${it.width_px || "?"}×${it.height_px || "?"}px</span></span>
                    <span class="lib-kv"><span class="lib-k">大小</span><span class="lib-v">${fmtLibSize(it.size_bytes)}</span></span>
                </div>
            </div>
        </div>`).join("");
    grid.querySelectorAll(".picker-card").forEach(card => {
        card.addEventListener("click", () => {
            const it = items.find(x => x.id === card.dataset.id);
            if (!it) return;
            applyImageToZone(pickerZone, {
                path: it.path,
                previewUrl: `/api/library/${it.id}/thumb`,
                name: it.original_name,
                sub: `${it.width_px || "?"}×${it.height_px || "?"} · 点击更换`,
            });
            closePicker();
        });
    });
}

// ---- 生成 ----

function collectVars() {
    const out = {};
    varsContainer.querySelectorAll('input[data-var]').forEach(input => {
        const name = input.dataset.var;
        const val = input.value.trim();
        if (val) out[name] = val;
    });
    return out;
}

async function generate() {
    const typeId = typeSelect.value;
    const sizeId = sizeSelect.value;
    if (!typeId || !sizeId) return;
    const imageZones = (state.params?.zones || []).filter(z => z.type === "image");
    // 本期单图片区：取第一个图片区的图
    const imagePath = state.imagePaths[imageZones[0].name];

    const body = {
        type_id: typeId,
        size_id: sizeId,
        image_path: imagePath,
        vars: collectVars(),
    };

    generateBtn.disabled = true;
    const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    generateBtn.disabled = false;
    if (!res.ok) {
        alert("生成失败: " + (data.detail || res.status));
        return;
    }
    // task_id 由 WS 推送更新，这里只清空上传区准备下次
    state.imagePaths = {};
    zonesContainer.querySelectorAll(".zone-upload").forEach(c => {
        c.classList.remove("has-file");
        const dz = c.querySelector(".dropzone");
        dz.classList.remove("has-preview", "is-loading");
        dz.style.removeProperty("--preview");
        dz.querySelector(".dropzone-hint").textContent = "点击选择或拖入图片";
        dz.querySelector(".dropzone-sub").textContent = "支持 PNG / JPG / TIF";
        c.querySelector(".file-info").textContent = "未选择文件";
        c.querySelector('input[type="file"]').value = "";
    });
    updateGenerateBtn();
}

// ---- 事件绑定 ----

typeSelect.addEventListener("change", () => {
    if (typeSelect.value) loadSizes(typeSelect.value);
});
sizeSelect.addEventListener("change", () => {
    if (typeSelect.value && sizeSelect.value) loadParams(typeSelect.value, sizeSelect.value);
});
generateBtn.addEventListener("click", generate);

// ---- 初始化 ----
loadTypes();
