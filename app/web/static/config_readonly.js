// 排版 / 存储配置只读页（由 script[data-target] 指定加载哪个）

const target = document.currentScript.dataset.target;
const escapeHtml = s => (s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

async function loadImpose() {
    const pane = document.getElementById("cfg-impose");
    const d = await (await fetch("/api/config/impose")).json();
    pane.innerHTML = (d.presets || []).map(p => `
        <div class="ro-row">
            <div class="ro-row-head">${escapeHtml(p.name)} <span class="cfg-size-id">${p.id}</span></div>
            <div class="ro-row-sub">画布 ${p.canvas.width_mm}×${p.canvas.height_mm}mm @${p.canvas.dpi}dpi · 输出 ${p.output.format.toUpperCase()}</div>
            <div class="ro-row-sub">间距 水平 ${p.gutters.horizontal_mm}mm / 垂直 ${p.gutters.vertical_mm}mm / 边距 ${p.gutters.margin_mm}mm</div>
        </div>
    `).join("") || `<div class="empty">无预设</div>`;
}

async function loadStorage() {
    const pane = document.getElementById("cfg-storage");
    const d = await (await fetch("/api/config/storage")).json();
    pane.innerHTML = `
        <div class="ro-row"><div class="ro-row-head">文件库</div>
            <div class="ro-row-sub">${d.library.path} / ${d.library.db_filename}</div></div>
        <div class="ro-row"><div class="ro-row-head">缩略图</div>
            <div class="ro-row-sub">${d.thumbnail.format.toUpperCase()} ${d.thumbnail.max_size_px}px · 质量 ${d.thumbnail.quality}</div></div>
        <div class="ro-row">
            <div class="ro-row-head">任务并发上限</div>
            <div class="ro-row-sub">并行运行任务数（排队中的任务等空位）</div>
            <div class="ro-concurrency">
                <input type="number" id="cfg-max-concurrency" min="1" value="${d.tasks.max_concurrency}">
                <button type="button" id="cfg-save-concurrency">保存</button>
                <span class="ro-conc-msg" id="cfg-conc-msg"></span>
            </div>
        </div>
    `;
    document.getElementById("cfg-save-concurrency").addEventListener("click", saveConcurrency);
}

async function saveConcurrency() {
    const input = document.getElementById("cfg-max-concurrency");
    const msg = document.getElementById("cfg-conc-msg");
    const val = parseInt(input.value, 10);
    if (!Number.isFinite(val) || val < 1) {
        msg.textContent = "须为 ≥1 的整数";
        msg.className = "ro-conc-msg err";
        return;
    }
    msg.textContent = "保存中…";
    msg.className = "ro-conc-msg";
    try {
        const r = await fetch("/api/config/storage/tasks", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ max_concurrency: val }),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || "保存失败");
        input.value = d.max_concurrency;
        msg.textContent = "已保存";
        msg.className = "ro-conc-msg ok";
    } catch (e) {
        msg.textContent = e.message;
        msg.className = "ro-conc-msg err";
    }
}

if (target === "impose") loadImpose();
else if (target === "storage") loadStorage();
