// 印前配置图形编辑器 · 主控
// 职责：类型/尺码树、tab 切换、state.params 持有、保存/删除、JSON 双向同步、左栏模块导航。
// 表单渲染委托 cfg.forms，画布渲染委托 cfg.canvas。

window.cfg = window.cfg || {};

// 空白尺码模板（最小合法 params）
const BLANK_PARAMS = {
    width_mm: 100, height_mm: 100, bleed_mm: 3, dpi: 150, bitdepth: 8, color_profile: "srgb",
    background: { enabled: true, fill_color: [255, 255, 255] },
    zones: [{ name: "FaceA", type: "image", x_mm: 3, y_mm: 3, width_mm: 94, height_mm: 94, fit_mode: "stretch" }],
    marks: { crop_marks: { enabled: true, color: "black", width_mm: 0.2, dashed: false, dash_length_mm: 2, gap_length_mm: 2 },
             zipper_marks: { enabled: false, side: "left", span_mm: null, pitch_mm: null, line_width_mm: 0.5, alignment: "center", offset_mm: 5, length_mm: 10, color: "black" },
             text_marks: { enabled: false, color: "black", font_size_pt: 12, items: [] } },
    output: { formats: ["psd"], save_name: "" },
};

// ---- 全局状态 ----
const state = {
    typeList: [],
    currentType: null,
    currentSize: null,
    sizeName: "",
    params: null,           // 当前编辑的 params（与后端 Params 同构）
    selectedModule: "canvas",
    selectedZoneIdx: null,
    activeTab: "graphic",   // graphic | json
    copySource: null,       // 复制副本时来源 {type, size}，null 表示新建模式
};
cfg.state = state;

// DOM 引用（openSize 时填充）
cfg.dom = { right: null, canvas: null, nav: null };

// ---- 工具 ----
function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}
const ID_RE = /^[^/\\:*?"<>|\s]*$/;

// ---- 类型/尺码树 ----
async function loadTree() {
    const tree = document.getElementById("cfg-tree");
    tree.innerHTML = `<div class="empty">加载中…</div>`;
    state.typeList = await (await fetch("/api/config/prepress")).json();
    renderTree();
}

function renderTree() {
    const tree = document.getElementById("cfg-tree");
    if (state.typeList.length === 0) {
        tree.innerHTML = `<div class="empty">无类型</div>`;
        return;
    }
    tree.innerHTML = state.typeList.map(t => `
        <div class="cfg-type">
            <div class="cfg-type-head">${escapeHtml(t.name)} <span class="cfg-type-id">${t.id}</span></div>
            <div class="cfg-sizes">
                ${t.sizes.map(s => `
                    <div class="cfg-size-row ${state.currentType === t.id && state.currentSize === s.id ? "is-active" : ""}">
                        <button class="cfg-size" data-type="${t.id}" data-size="${s.id}">${escapeHtml(s.name)} <span class="cfg-size-id">${s.id}</span></button>
                        <button class="cfg-copy" title="复制副本" data-copy-type="${t.id}" data-copy-size="${s.id}" aria-label="复制">⎘</button>
                    </div>
                `).join("")}
            </div>
        </div>`).join("");
    tree.querySelectorAll(".cfg-size").forEach(b => {
        b.addEventListener("click", () => openSize(b.dataset.type, b.dataset.size));
    });
    tree.querySelectorAll(".cfg-copy").forEach(b => {
        b.addEventListener("click", () => openCopyModal(b.dataset.copyType, b.dataset.copySize));
    });
}

// ---- 打开尺码：加载并渲染三栏 ----
async function openSize(typeId, sizeId) {
    state.origType = typeId;           // 保存时的原始 id（判断是否改了 id）
    state.origSize = sizeId;
    state.currentType = typeId;
    state.currentSize = sizeId;
    state.selectedModule = "canvas";
    state.selectedZoneIdx = null;
    state.activeTab = "graphic";
    renderTree();

    const editor = document.getElementById("cfg-editor");
    editor.innerHTML = editorSkeleton();
    cfg.dom.nav = document.getElementById("cfg-nav");
    cfg.dom.canvas = document.getElementById("cfg-canvas");
    cfg.dom.right = document.getElementById("cfg-right");

    const status = document.getElementById("cfg-status");
    status.textContent = "加载中…";
    try {
        const data = await (await fetch(`/api/config/prepress/${typeId}/${sizeId}`)).json();
        state.sizeName = data.name || sizeId;
        state.params = data.params;
        // 填充顶部标识输入框
        document.getElementById("cfg-id-type").value = state.currentType;
        document.getElementById("cfg-id-size").value = state.currentSize;
        document.getElementById("cfg-id-name").value = state.sizeName;
        renderNav();
        cfg.canvas.render();
        cfg.forms.render(state.selectedModule);
        status.textContent = "";
    } catch (e) {
        status.textContent = "加载失败";
    }
    bindEditorActions();
}

// 编辑区骨架：顶部标识行 + tab + 三栏
function editorSkeleton() {
    return `
        <div class="cfg-id-bar">
            <label class="cfg-id-field"><span class="cfg-id-label">类型</span>
                <input type="text" id="cfg-id-type" spellcheck="false" autocomplete="off"></label>
            <label class="cfg-id-field"><span class="cfg-id-label">尺码</span>
                <input type="text" id="cfg-id-size" spellcheck="false" autocomplete="off"></label>
            <label class="cfg-id-field cfg-id-field-name"><span class="cfg-id-label">显示名</span>
                <input type="text" id="cfg-id-name" spellcheck="false" autocomplete="off"></label>
        </div>
        <div class="cfg-edit-bar">
            <div class="cfg-tabs">
                <button class="cfg-tab is-active" data-tab="graphic">图形编辑</button>
                <button class="cfg-tab" data-tab="json">JSON 源码</button>
            </div>
            <div class="cfg-edit-actions">
                <span class="cfg-status" id="cfg-status"></span>
                <button class="cfg-link-del" data-del>删除尺码</button>
                <button class="btn btn-primary" id="cfg-save">保存</button>
            </div>
        </div>
        <div class="cfg-edit-layout">
            <div class="cfg-edit-nav" id="cfg-nav"></div>
            <div class="cfg-edit-canvas" id="cfg-canvas"></div>
            <div class="cfg-edit-right" id="cfg-right"></div>
        </div>
        <div class="cfg-json-pane" id="cfg-json-pane" hidden>
            <textarea class="cfg-json" id="cfg-json" spellcheck="false"></textarea>
        </div>`;
}

// ---- 左栏模块导航 ----
const MODULES = [
    { key: "canvas", label: "画布" },
    { key: "background", label: "背景" },
    { key: "solid_layer", label: "纯色层" },
    { key: "zones", label: "区域", isGroup: true },
    { key: "crop_marks", label: "裁剪线" },
    { key: "zipper_marks", label: "拉链标记" },
    { key: "text_marks", label: "文字标记" },
    { key: "border_marks", label: "边框标记" },
    { key: "output", label: "输出" },
];

function renderNav() {
    const nav = cfg.dom.nav;
    if (!nav || !state.params) return;
    const zones = state.params.zones || [];
    const items = MODULES.map(m => {
        if (m.isGroup) {
            const zoneItems = zones.map((z, i) => `
                <button class="cfg-nav-item cfg-nav-zone ${state.selectedModule === "zone" && state.selectedZoneIdx === i ? "is-active" : ""}"
                        data-zone="${i}">
                    <span class="cfg-nav-dot ${z.type === "color" ? "dot-color" : "dot-image"}"></span>
                    ${escapeHtml(z.name || "(未命名)")}
                    <span class="cfg-nav-ztype">${z.type}</span>
                </button>`).join("");
            return `<div class="cfg-nav-group">
                <div class="cfg-nav-label">${m.label}</div>
                <div class="cfg-nav-zones">${zoneItems}</div>
                <button class="cfg-nav-add" data-add-zone>+ 新增区域</button>
            </div>`;
        }
        const active = state.selectedModule === m.key ? "is-active" : "";
        return `<button class="cfg-nav-item ${active}" data-module="${m.key}">${m.label}</button>`;
    }).join("");

    nav.innerHTML = items;
    nav.querySelectorAll("[data-module]").forEach(b => {
        b.addEventListener("click", () => cfg.nav.select(b.dataset.module));
    });
    nav.querySelectorAll("[data-zone]").forEach(b => {
        b.addEventListener("click", () => {
            state.selectedZoneIdx = +b.dataset.zone;
            cfg.nav.select("zone");
        });
    });
    nav.querySelector("[data-add-zone]")?.addEventListener("click", addZone);
}

cfg.nav = {
    select(moduleKey) {
        state.selectedModule = moduleKey;
        if (moduleKey !== "zone") state.selectedZoneIdx = null;
        renderNav();
        cfg.forms.render(moduleKey);
        cfg.canvas.render();
    },
    render: renderNav,
};

function addZone() {
    const p = state.params;
    const n = p.zones.length + 1;
    p.zones.push({ name: `Zone${n}`, type: "image", x_mm: 3, y_mm: 3, width_mm: 50, height_mm: 50, fit_mode: "stretch" });
    state.selectedZoneIdx = p.zones.length - 1;
    cfg.nav.select("zone");
}

// ---- tab 切换 + JSON 双向同步 ----
function bindEditorActions() {
    document.querySelectorAll(".cfg-tab").forEach(t => {
        t.addEventListener("click", () => switchTab(t.dataset.tab));
    });
    document.getElementById("cfg-save").addEventListener("click", save);
    document.querySelector("[data-del]")?.addEventListener("click", () => delSize(state.currentType, state.currentSize));
}

function switchTab(tab) {
    if (tab === state.activeTab) return;
    if (tab === "json") {
        // 图形 → JSON：序列化当前 params
        document.getElementById("cfg-json").value = JSON.stringify(state.params, null, 2);
    } else {
        // JSON → 图形：解析回内存
        const ta = document.getElementById("cfg-json");
        try {
            state.params = JSON.parse(ta.value);
        } catch (e) {
            alert("JSON 语法错误，无法切换到图形编辑: " + e.message);
            return;
        }
        renderNav();
        cfg.canvas.render();
        cfg.forms.render(state.selectedModule);
    }
    state.activeTab = tab;
    document.querySelectorAll(".cfg-tab").forEach(t => t.classList.toggle("is-active", t.dataset.tab === tab));
    document.getElementById("cfg-json-pane").hidden = (tab !== "json");
    document.querySelector(".cfg-edit-layout").hidden = (tab === "json");
}

// ---- 保存 ----
async function save() {
    const status = document.getElementById("cfg-status");
    status.className = "cfg-status";
    // 若在 JSON tab，先把 textarea 解析进 state.params
    if (state.activeTab === "json") {
        try { state.params = JSON.parse(document.getElementById("cfg-json").value); }
        catch (e) { status.className = "cfg-status is-err"; status.textContent = "JSON 语法错误: " + e.message; return; }
    }
    // 读取顶部标识输入框（可能改了 type/size/name）
    const newType = document.getElementById("cfg-id-type").value.trim();
    const newSize = document.getElementById("cfg-id-size").value.trim();
    const newName = document.getElementById("cfg-id-name").value.trim() || newSize;
    if (!newType || !newSize) {
        status.className = "cfg-status is-err";
        status.textContent = "类型 / 尺码 id 不能为空";
        return;
    }
    const idChanged = (newType !== state.origType || newSize !== state.origSize);
    const nameChanged = (newName !== state.sizeName);

    status.textContent = "保存中…";

    // 1) 若改了 type/size id，先调 rename（改文件名 + 文件内 type/size/name 字段）
    if (idChanged) {
        const rRes = await fetch("/api/config/prepress/rename", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                old_type: state.origType, old_size: state.origSize,
                new_type: newType, new_size: newSize, new_name: newName,
            }),
        });
        if (!rRes.ok) {
            const d = await rRes.json().catch(() => ({}));
            status.className = "cfg-status is-err";
            status.textContent = "重命名失败: " + (d.detail || rRes.status);
            return;
        }
        state.origType = newType; state.origSize = newSize;
        state.currentType = newType; state.currentSize = newSize;
        state.sizeName = newName;
    } else if (nameChanged) {
        // 2) 只改 name：随 PUT 的 body.name 一起保存即可，无需单独 rename
        state.sizeName = newName;
    }

    // 3) 保存 params（body 的 type/size 须与 URL 一致）
    const body = { type: state.currentType, size: state.currentSize, name: state.sizeName, params: state.params };
    const res = await fetch(`/api/config/prepress/${state.currentType}/${state.currentSize}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (res.ok) {
        status.className = "cfg-status is-ok";
        status.textContent = "已保存并重载";
        await loadTree();
        // 若改了 id，左栏已重新渲染；同步选中新 id
        if (idChanged) {
            state.currentType = newType; state.currentSize = newSize;
            state.origType = newType; state.origSize = newSize;
        }
    } else {
        const d = await res.json().catch(() => ({}));
        status.className = "cfg-status is-err";
        status.textContent = "校验失败: " + (d.detail || res.status);
    }
}

async function delSize(typeId, sizeId) {
    if (!confirm(`确认删除尺码 ${typeId}/${sizeId}？`)) return;
    const res = await fetch(`/api/config/prepress/${typeId}/${sizeId}`, { method: "DELETE" });
    if (res.ok) {
        state.currentType = state.currentSize = null;
        state.params = null;
        document.getElementById("cfg-editor").innerHTML = `<div class="cfg-editor-empty">选择左侧某个尺码，在此图形化编辑或查看 JSON。</div>`;
        await loadTree();
    } else {
        const d = await res.json().catch(() => ({}));
        alert("删除失败: " + (d.detail || res.status));
    }
}

// ---- 类型组合框 + 新增尺码弹层（沿用原逻辑）----
function initAddSizeModal() {
    const combo = document.getElementById("cfg-type-combo");
    const comboInput = document.getElementById("cfg-new-type");
    const comboList = document.getElementById("cfg-type-list");

    function renderComboOptions(filter = "") {
        const f = filter.trim().toLowerCase();
        const opts = state.typeList.filter(t => !f || t.id.toLowerCase().includes(f) || t.name.toLowerCase().includes(f));
        comboList.innerHTML = opts.length === 0
            ? `<div class="combo-empty">无匹配，将新建此类型</div>`
            : opts.map(t => `<div class="combo-opt" data-val="${t.id}">${escapeHtml(t.name)} <span class="cfg-size-id">${t.id}</span></div>`).join("");
        comboList.querySelectorAll(".combo-opt").forEach(o => {
            o.addEventListener("mousedown", e => { e.preventDefault(); comboInput.value = o.dataset.val; combo.classList.remove("is-open"); });
        });
    }
    comboInput.addEventListener("focus", () => { renderComboOptions(comboInput.value); combo.classList.add("is-open"); });
    comboInput.addEventListener("input", () => { renderComboOptions(comboInput.value); combo.classList.add("is-open"); });
    comboInput.addEventListener("blur", () => setTimeout(() => combo.classList.remove("is-open"), 120));
    combo.querySelector(".combo-caret").addEventListener("mousedown", e => {
        e.preventDefault();
        if (combo.classList.contains("is-open")) combo.classList.remove("is-open");
        else { renderComboOptions(comboInput.value); combo.classList.add("is-open"); comboInput.focus(); }
    });

    const sizeInput = document.getElementById("cfg-new-size");
    const typeErr = document.getElementById("cfg-new-type-err");
    const sizeErr = document.getElementById("cfg-new-size-err");
    function checkIdInput(el, errEl, label) {
        const v = el.value;
        if (v && !ID_RE.test(v)) {
            const bad = [...v].find(c => !/[^/\\:*?"<>|\s]/.test(c));
            errEl.textContent = `${label}含非法字符「${bad}」（禁 / \\ : * ? " < > | 及空格）`;
            return false;
        }
        errEl.textContent = "";
        return true;
    }
    comboInput.addEventListener("input", () => checkIdInput(comboInput, typeErr, "类型"));
    sizeInput.addEventListener("input", () => checkIdInput(sizeInput, sizeErr, "尺码"));

    const modal = document.getElementById("cfg-modal");
    const modalTitle = modal.querySelector(".card-head h2");
    const modalHint = modal.querySelector(".modal-hint");

    // 新建尺码
    document.getElementById("cfg-add-btn").addEventListener("click", () => {
        state.copySource = null;
        modalTitle.textContent = "新增尺码";
        modalHint.innerHTML = "将以空白模板创建。类型/尺码 ID 允许中文，仅禁 <code>/ \\ : * ? \" &lt; &gt; |</code> 及空格。";
        comboInput.value = ""; sizeInput.value = "";
        document.getElementById("cfg-new-name").value = "";
        typeErr.textContent = ""; sizeErr.textContent = "";
        modal.hidden = false;
    });
    document.getElementById("cfg-modal-cancel").addEventListener("click", () => modal.hidden = true);
    document.getElementById("cfg-modal-ok").addEventListener("click", async () => {
        const typeId = comboInput.value.trim();
        const sizeId = sizeInput.value.trim();
        const name = document.getElementById("cfg-new-name").value.trim();
        if (!typeId) { alert("请填类型 ID"); return; }
        if (!sizeId) { alert("请填尺码 ID"); return; }
        if (!checkIdInput(comboInput, typeErr, "类型") || !checkIdInput(sizeInput, sizeErr, "尺码")) return;
        const finalName = name || sizeId;

        // 复制模式：先读源尺码 params，再用源 params 创建新尺码
        let params = BLANK_PARAMS;
        if (state.copySource) {
            try {
                const src = await (await fetch(`/api/config/prepress/${state.copySource.type}/${state.copySource.size}`)).json();
                params = src.params;
            } catch (e) {
                alert("读取源配置失败: " + e.message);
                return;
            }
        }

        const body = { type_id: typeId, size_id: sizeId, name: finalName, params };
        const res = await fetch("/api/config/prepress", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        if (res.ok) {
            modal.hidden = true;
            state.copySource = null;
            await loadTree();
            openSize(typeId, sizeId);
        } else {
            const d = await res.json().catch(() => ({}));
            alert("创建失败: " + (d.detail || res.status));
        }
    });
}

// 复制副本：打开 modal，预填来源类型，标记 copy 模式
function openCopyModal(srcType, srcSize) {
    state.copySource = { type: srcType, size: srcSize };
    const modal = document.getElementById("cfg-modal");
    modal.querySelector(".card-head h2").textContent = "复制副本";
    modal.querySelector(".modal-hint").innerHTML = `将复制 <b>${escapeHtml(srcType)}/${escapeHtml(srcSize)}</b> 的全部配置到新尺码，复制后可在此基础上修改。ID 允许中文，仅禁 <code>/ \\ : * ? \" &lt; &gt; |</code> 及空格。`;
    // 预填：类型默认同源类型，尺码/名称留空待填
    document.getElementById("cfg-new-type").value = srcType;
    document.getElementById("cfg-new-size").value = "";
    document.getElementById("cfg-new-name").value = "";
    document.getElementById("cfg-new-type-err").textContent = "";
    document.getElementById("cfg-new-size-err").textContent = "";
    modal.hidden = false;
}

// ---- 初始化 ----
loadTree();
initAddSizeModal();
