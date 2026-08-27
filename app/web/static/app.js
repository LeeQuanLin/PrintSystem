// 印前生成页前端逻辑：拉配置、动态上传区、提交生成、WS 进度展示、下载

const state = {
    types: [],
    sizes: [],
    params: null,
    placeholders: [],     // 占位符变量名列表
    imagePaths: {},       // zone_name -> uploaded image_path
    tasks: {},            // task_id -> task dict
};

// ---- DOM ----
const typeSelect = document.getElementById("type-select");
const sizeSelect = document.getElementById("size-select");
const zonesContainer = document.getElementById("zones-container");
const varsContainer = document.getElementById("vars-container");
const generateBtn = document.getElementById("generate-btn");
const taskList = document.getElementById("task-list");

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
    updateGenerateBtn();
}

// ---- 上传 ----

async function handleUpload(input) {
    const zoneName = input.dataset.zone;
    const file = input.files[0];
    if (!file) return;
    const card = input.closest(".zone-upload");
    const dz = card.querySelector(".dropzone");
    const info = card.querySelector(".file-info");

    // 即时本地预览 + 上传中态
    const previewUrl = URL.createObjectURL(file);
    dz.classList.add("is-loading");
    dz.querySelector(".dropzone-hint").textContent = "上传中…";
    info.textContent = `${file.name} (${(file.size/1024/1024).toFixed(1)}MB)`;

    const fd = new FormData();
    fd.append("file", file);
    try {
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "上传失败");
        state.imagePaths[zoneName] = data.path;
        card.classList.add("has-file");
        dz.classList.remove("is-loading");
        dz.classList.add("has-preview");
        // 替换为预览背景图
        dz.style.setProperty("--preview", `url("${previewUrl}")`);
        dz.querySelector(".dropzone-hint").textContent = file.name;
        dz.querySelector(".dropzone-sub").textContent = `${(file.size/1024/1024).toFixed(1)} MB · 点击更换`;
    } catch (e) {
        dz.classList.remove("is-loading");
        dz.querySelector(".dropzone-hint").textContent = "点击选择或拖入图片";
        dz.querySelector(".dropzone-sub").textContent = "支持 PNG / JPG / TIF";
        info.textContent = "上传失败";
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

// ---- WebSocket 进度 ----

function connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = e => {
        const msg = JSON.parse(e.data);
        state.tasks[msg.task_id] = msg;
        renderTaskList();
    };
    ws.onclose = () => setTimeout(connectWS, 2000);  // 断线重连
    ws.onerror = () => ws.close();
}

function renderTaskList() {
    const tasks = Object.values(state.tasks).sort((a, b) => (b.task_id || "").localeCompare(a.task_id || ""));
    const summary = document.getElementById("task-summary");
    const countEl = document.getElementById("task-count");
    if (summary) summary.textContent = `${tasks.length} 条`;
    if (countEl) countEl.textContent = tasks.length;

    if (tasks.length === 0) {
        taskList.innerHTML = `<div class="empty">提交生成后，任务进度将在此实时呈现。</div>`;
        return;
    }
    taskList.innerHTML = tasks.map(t => `
        <div class="task-card ${t.status}">
            <div class="task-head">
                <span class="task-id">${t.task_id?.slice(0, 8)}</span>
                <span class="task-status">${statusLabel(t.status)}</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width:${t.progress}%"></div>
            </div>
            <div class="stage">${t.stage || ""} ${t.message || ""}</div>
            ${t.status === "succeeded" ? renderDownloads(t) : ""}
            ${t.status === "failed" ? `<div class="error">${t.error || ""}</div>` : ""}
        </div>
    `).join("");
}

function statusLabel(s) {
    return ({ pending: "等待", running: "处理中", succeeded: "完成", failed: "失败" })[s] || s;
}

function renderDownloads(t) {
    const links = (t.outputs || []).map(o =>
        `<a href="/api/tasks/${t.task_id}/download/${o.format}" download>${o.format.toUpperCase()}</a>`
    ).join("");
    const thumb = t.thumb_path
        ? `<a href="/api/tasks/${t.task_id}/thumb" target="_blank">缩略图</a>` : "";
    return `<div class="downloads">${links}${thumb}</div>`;
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
connectWS();
renderTaskList();
