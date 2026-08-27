// 印前配置页：树 + JSON 编辑器（读写）+ 类型组合框

const tree = document.getElementById("cfg-tree");
const editorPane = document.getElementById("cfg-editor");

let currentType = null, currentSize = null;
let typeList = [];

// 空白尺码模板（最小合法 params）
const BLANK_PARAMS = {
    width_mm: 100, height_mm: 100, bleed_mm: 3, dpi: 150, bitdepth: 8, color_profile: "srgb",
    background: { enabled: true, fill_color: [255, 255, 255] },
    zones: [{ name: "FaceA", type: "image", x_mm: 3, y_mm: 3, width_mm: 94, height_mm: 94, fit_mode: "stretch" }],
    marks: { crop_marks: { enabled: true, color: "black", width_mm: 0.2, length_mm: 5, offset_mm: 3 } },
    output: { formats: ["psd"] },
};

// ---- 印前树 ----
async function loadTree() {
    tree.innerHTML = `<div class="empty">加载中…</div>`;
    typeList = await (await fetch("/api/config/prepress")).json();
    renderTree();
}

function renderTree() {
    if (typeList.length === 0) {
        tree.innerHTML = `<div class="empty">无类型</div>`;
        return;
    }
    tree.innerHTML = typeList.map(t => `
        <div class="cfg-type">
            <div class="cfg-type-head">${escapeHtml(t.name)} <span class="cfg-type-id">${t.id}</span></div>
            <div class="cfg-sizes">
                ${t.sizes.map(s => `
                    <button class="cfg-size ${currentType === t.id && currentSize === s.id ? "is-active" : ""}"
                            data-type="${t.id}" data-size="${s.id}">${escapeHtml(s.name)} <span class="cfg-size-id">${s.id}</span></button>
                `).join("")}
            </div>
        </div>
    `).join("");
    tree.querySelectorAll(".cfg-size").forEach(b => {
        b.addEventListener("click", () => openSize(b.dataset.type, b.dataset.size));
    });
}

async function openSize(typeId, sizeId) {
    currentType = typeId; currentSize = sizeId;
    renderTree();
    editorPane.innerHTML = `
        <div class="cfg-editor-head">
            <span class="cfg-edit-title">${typeId} / ${sizeId}</span>
            <div class="cfg-edit-actions">
                <button class="cfg-link-del" data-del>删除尺码</button>
                <button class="btn btn-primary" id="cfg-save">保存</button>
            </div>
        </div>
        <textarea class="cfg-json" id="cfg-json" spellcheck="false"></textarea>
        <div class="cfg-status" id="cfg-status"></div>
    `;
    const ta = document.getElementById("cfg-json");
    const status = document.getElementById("cfg-status");
    status.textContent = "加载中…";
    try {
        const data = await (await fetch(`/api/config/prepress/${typeId}/${sizeId}`)).json();
        ta.value = JSON.stringify(data, null, 2);
        status.textContent = "";
    } catch (e) {
        status.textContent = "加载失败";
    }
    document.getElementById("cfg-save").addEventListener("click", () => save(typeId, sizeId, ta, status));
    editorPane.querySelector("[data-del]").addEventListener("click", () => delSize(typeId, sizeId));
}

async function save(typeId, sizeId, ta, status) {
    status.className = "cfg-status";
    let data;
    try {
        data = JSON.parse(ta.value);
    } catch (e) {
        status.className = "cfg-status is-err";
        status.textContent = "JSON 语法错误: " + e.message;
        return;
    }
    status.textContent = "保存中…";
    const res = await fetch(`/api/config/prepress/${typeId}/${sizeId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
    if (res.ok) {
        status.className = "cfg-status is-ok";
        status.textContent = "已保存并重载";
        await loadTree();
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
        currentType = currentSize = null;
        editorPane.innerHTML = `<div class="cfg-editor-empty">选择左侧某个尺码，在此查看与编辑其 JSON 配置。</div>`;
        await loadTree();
    } else {
        const d = await res.json().catch(() => ({}));
        alert("删除失败: " + (d.detail || res.status));
    }
}

// ---- 类型组合框（可输入 + 点击弹出已有选项）----
const combo = document.getElementById("cfg-type-combo");
const comboInput = document.getElementById("cfg-new-type");
const comboList = document.getElementById("cfg-type-list");

function renderComboOptions(filter = "") {
    const f = filter.trim().toLowerCase();
    const opts = typeList.filter(t => !f || t.id.toLowerCase().includes(f) || t.name.toLowerCase().includes(f));
    comboList.innerHTML = opts.length === 0
        ? `<div class="combo-empty">无匹配，将新建此类型</div>`
        : opts.map(t => `<div class="combo-opt" data-val="${t.id}">${escapeHtml(t.name)} <span class="cfg-size-id">${t.id}</span></div>`).join("");
    comboList.querySelectorAll(".combo-opt").forEach(o => {
        o.addEventListener("mousedown", e => {
            e.preventDefault();
            comboInput.value = o.dataset.val;
            combo.classList.remove("is-open");
        });
    });
}

comboInput.addEventListener("focus", () => {
    renderComboOptions(comboInput.value);
    combo.classList.add("is-open");
});
comboInput.addEventListener("input", () => {
    renderComboOptions(comboInput.value);
    combo.classList.add("is-open");
});
comboInput.addEventListener("blur", () => setTimeout(() => combo.classList.remove("is-open"), 120));
combo.querySelector(".combo-caret").addEventListener("mousedown", e => {
    e.preventDefault();
    if (combo.classList.contains("is-open")) {
        combo.classList.remove("is-open");
    } else {
        renderComboOptions(comboInput.value);
        combo.classList.add("is-open");
        comboInput.focus();
    }
});

// ---- 新增尺码弹层 ----
// id 允许中文，仅禁路径非法字符与空白
const ID_RE = /^[^/\\:*?"<>|\s]*$/;
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
document.getElementById("cfg-add-btn").addEventListener("click", () => {
    comboInput.value = "";
    sizeInput.value = "";
    document.getElementById("cfg-new-name").value = "";
    typeErr.textContent = "";
    sizeErr.textContent = "";
    modal.hidden = false;
});
document.getElementById("cfg-modal-cancel").addEventListener("click", () => modal.hidden = true);
document.getElementById("cfg-modal-ok").addEventListener("click", async () => {
    const body = {
        type_id: comboInput.value.trim(),
        size_id: document.getElementById("cfg-new-size").value.trim(),
        name: document.getElementById("cfg-new-name").value.trim(),
        params: BLANK_PARAMS,
    };
    if (!body.type_id) { alert("请填类型 ID（可选已有或输入新类型）"); return; }
    if (!body.size_id) { alert("请填尺码 ID"); return; }
    if (!checkIdInput(comboInput, typeErr, "类型") || !checkIdInput(sizeInput, sizeErr, "尺码")) {
        return;  // 实时校验已在输入框下方提示
    }
    if (!body.name) body.name = body.size_id;
    const res = await fetch("/api/config/prepress", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (res.ok) {
        modal.hidden = true;
        await loadTree();
        openSize(body.type_id, body.size_id);
    } else {
        const d = await res.json().catch(() => ({}));
        alert("创建失败: " + (d.detail || res.status));
    }
});

function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

loadTree();
