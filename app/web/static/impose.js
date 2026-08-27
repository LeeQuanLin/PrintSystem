// 排版拼版页（自由配置）：左图件列表 + 中预览画布 + 右内联配置 + 任务队列
// 图件按顺序行优先填入网格；列数驱动，行数 = ceil(n/cols) 自动。
// 预览：前端 Canvas 实时按比例绘制网格+图件缩略图+边距/间隔线+透明区棋盘格。

const state = {
    images: [],   // {image_id, path, previewUrl, name, rotation, _img?: HTMLImageElement}
};

// ---- DOM ----
const imgList = document.getElementById("img-list");
const imgCount = document.getElementById("img-count");
const fileInput = document.getElementById("img-file-input");
const imposeBtn = document.getElementById("impose-btn");
const canvas = document.getElementById("preview-canvas");
const ctx = canvas.getContext("2d");
const previewEmpty = document.getElementById("preview-empty");
const previewScale = document.getElementById("preview-scale");
const previewWrap = document.getElementById("preview-wrap");

// ---- 配置读取 ----

function readConfig() {
    return {
        width_mm: parseFloat(document.getElementById("cfg-width").value) || 0,
        height_mm: parseFloat(document.getElementById("cfg-height").value) || 0,
        dpi: parseInt(document.getElementById("cfg-dpi").value, 10) || 0,
    };
}

// ---- 图件列表渲染 ----

function renderImgList() {
    imgCount.textContent = `${state.images.length} 张`;
    if (state.images.length === 0) {
        imgList.innerHTML = `<div class="empty">添加图片后可调整顺序与旋转。</div>`;
    } else {
        imgList.innerHTML = state.images.map((im, i) => `
            <div class="img-item" data-idx="${i}">
                <div class="img-thumb" style="background-image:url('${im.previewUrl}')"></div>
                <div class="img-meta">
                    <div class="img-name" title="${escapeHtml(im.name)}">${escapeHtml(im.name)}</div>
                    <div class="img-rot">
                        <span>旋转</span>
                        <select data-idx="${i}" data-act="rotation">
                            <option value="0" ${im.rotation===0?"selected":""}>0°</option>
                            <option value="90" ${im.rotation===90?"selected":""}>90°</option>
                            <option value="180" ${im.rotation===180?"selected":""}>180°</option>
                            <option value="270" ${im.rotation===270?"selected":""}>270°</option>
                        </select>
                    </div>
                </div>
                <div class="img-ops">
                    <button type="button" data-idx="${i}" data-act="up" ${i===0?"disabled":""} aria-label="上移">↑</button>
                    <button type="button" data-idx="${i}" data-act="down" ${i===state.images.length-1?"disabled":""} aria-label="下移">↓</button>
                    <button type="button" data-idx="${i}" data-act="del" class="img-del" aria-label="删除">×</button>
                </div>
            </div>`).join("");
        imgList.querySelectorAll("button[data-act]").forEach(b => {
            b.addEventListener("click", () => onImgOp(b.dataset.act, parseInt(b.dataset.idx, 10)));
        });
        imgList.querySelectorAll('select[data-act="rotation"]').forEach(sel => {
            sel.addEventListener("change", () => {
                state.images[parseInt(sel.dataset.idx, 10)].rotation = parseInt(sel.value, 10);
                renderPreview();
            });
        });
    }
    updateSubmitBtn();
    renderPreview();
}

function onImgOp(act, i) {
    if (act === "up" && i > 0) {
        [state.images[i - 1], state.images[i]] = [state.images[i], state.images[i - 1]];
    } else if (act === "down" && i < state.images.length - 1) {
        [state.images[i + 1], state.images[i]] = [state.images[i], state.images[i + 1]];
    } else if (act === "del") {
        state.images.splice(i, 1);
    }
    renderImgList();
}

function updateSubmitBtn() {
    imposeBtn.disabled = state.images.length === 0;
}

// ---- 预加载图件缩略图为 Image 对象（Canvas 绘制用）----

function ensureImgLoaded(im) {
    if (im._img) return Promise.resolve(im._img);
    return new Promise(resolve => {
        const img = new Image();
        img.onload = () => { im._img = img; resolve(img); };
        img.onerror = () => { im._img = null; resolve(null); };
        img.src = im.previewUrl;
    });
}

async function ensureAllLoaded() {
    await Promise.all(state.images.map(ensureImgLoaded));
}

// ---- Canvas 预览 ----

function drawCheckerboard(x, y, w, h, cell) {
    // 棋盘格底（表示透明区）
    const c = Math.max(4, cell);
    for (let yy = 0; yy < h; yy += c) {
        for (let xx = 0; xx < w; xx += c) {
            const odd = (Math.floor(xx / c) + Math.floor(yy / c)) % 2;
            ctx.fillStyle = odd ? "#e8e8ec" : "#f6f6f8";
            ctx.fillRect(x + xx, y + yy, Math.min(c, w - xx), Math.min(c, h - yy));
        }
    }
}

// 计算图件旋转后的有效宽高（px，用原图实际尺寸而非缩略图尺寸）
function rotatedSize(im) {
    let w = im.w || 0, h = im.h || 0;
    if (im.rotation === 90 || im.rotation === 270) [w, h] = [h, w];
    return [w, h];
}

// 流式布局：按图件实际像素（旋转后）行优先铺排，从 (0,0) 起，换行看画布像素宽
function flowLayout(canvasWPx, canvasHPx) {
    const placements = [];
    let x = 0, y = 0, rowH = 0;
    for (let i = 0; i < state.images.length; i++) {
        const [w, h] = rotatedSize(state.images[i]);
        if (w <= 0) continue;
        if (x + w > canvasWPx && x > 0) { y += rowH; x = 0; rowH = 0; }
        placements.push({ i, x, y, w, h });
        x += w;
        rowH = Math.max(rowH, h);
    }
    return placements;
}

function renderPreview() {
    const cfg = readConfig();
    const n = state.images.length;

    if (n === 0 || cfg.width_mm <= 0 || cfg.height_mm <= 0) {
        canvas.hidden = true;
        previewEmpty.hidden = false;
        previewScale.textContent = "—";
        return;
    }
    canvas.hidden = false;
    previewEmpty.hidden = true;

    // 画布像素
    const canvasWPx = cfg.width_mm * cfg.dpi / 25.4;
    const canvasHPx = cfg.height_mm * cfg.dpi / 25.4;

    // Canvas 尺寸：按画布宽高比，限制最大 600×500
    const maxW = 600, maxH = 500;
    const ratio = cfg.width_mm / cfg.height_mm;
    let cw, ch;
    if (ratio > maxW / maxH) { cw = maxW; ch = maxW / ratio; }
    else { ch = maxH; cw = maxH * ratio; }
    canvas.width = Math.round(cw);
    canvas.height = Math.round(ch);
    const scale = cw / canvasWPx;  // 画布像素 → Canvas 像素

    previewScale.textContent = `1:${Math.round(1 / scale)} · ${cfg.width_mm}×${cfg.height_mm}mm`;

    ensureAllLoaded().then(() => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        // 棋盘格底（透明区）
        drawCheckerboard(0, 0, canvas.width, canvas.height, 10);

        const placements = flowLayout(canvasWPx, canvasHPx);
        for (const p of placements) {
            const im = state.images[p.i];
            const img = im._img;
            if (!img) continue;
            const dx = p.x * scale;
            const dy = p.y * scale;
            const dw = p.w * scale;
            const dh = p.h * scale;
            // 旋转：以绘制区中心为轴
            ctx.save();
            ctx.translate(dx + dw / 2, dy + dh / 2);
            ctx.rotate(im.rotation * Math.PI / 180);
            ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
            ctx.restore();
        }
    });
}

// 配置输入变化即时重绘
["cfg-width", "cfg-height", "cfg-dpi"].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener("input", renderPreview);
    el.addEventListener("change", renderPreview);
});

// ---- 添加图片：上传 ----

document.getElementById("add-upload").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files || []);
    if (files.length === 0) return;
    for (const file of files) {
        await uploadOne(file);
    }
    fileInput.value = "";
    renderImgList();
});

async function uploadOne(file) {
    const previewUrl = URL.createObjectURL(file);
    const fd = new FormData();
    fd.append("file", file);
    try {
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "上传失败");
        state.images.push({
            image_id: data.image_id,
            path: data.path,
            previewUrl,
            name: file.name,
            rotation: 0,
            w: data.width || 0,
            h: data.height || 0,
        });
    } catch (e) {
        alert(`上传失败 ${file.name}: ${e.message}`);
    }
}

// ---- 添加图片：文件库多选 ----

let pickerModal = null;
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
                <h2>从文件库选择（可多选）</h2>
                <button type="button" class="modal-close" aria-label="关闭">×</button>
            </div>
            <div class="modal-body">
                <input type="text" class="picker-search" placeholder="搜索文件名…">
                <div class="picker-grid lib-grid"></div>
            </div>
            <div class="modal-foot">
                <span class="picker-sel-count">已选 0 张</span>
                <button type="button" class="btn btn-primary picker-confirm" disabled>加入图件列表</button>
            </div>
        </div>`;
    document.body.appendChild(pickerModal);
    pickerModal.querySelector(".modal-close").addEventListener("click", closePicker);
    pickerModal.addEventListener("click", e => { if (e.target === pickerModal) closePicker(); });
    pickerModal.querySelector(".picker-search").addEventListener("input", e => {
        clearTimeout(pickerSearchTimer);
        pickerSearchTimer = setTimeout(() => loadPickerList(e.target.value.trim()), 250);
    });
    pickerModal.querySelector(".picker-confirm").addEventListener("click", confirmPicker);
    return pickerModal;
}

function openPicker() {
    ensurePicker();
    pickerModal._selected = new Set();
    pickerModal.hidden = false;
    pickerModal.querySelector(".picker-search").value = "";
    pickerModal.querySelector(".picker-confirm").disabled = true;
    pickerModal.querySelector(".picker-sel-count").textContent = "已选 0 张";
    loadPickerList("");
}

function closePicker() {
    if (pickerModal) pickerModal.hidden = true;
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
    pickerModal._itemsCache = items;
    if (items.length === 0) {
        grid.innerHTML = `<div class="empty">没有符合条件的文件。</div>`;
        return;
    }
    grid.innerHTML = items.map(it => `
        <div class="lib-card picker-card ${pickerModal._selected.has(it.id) ? "is-selected" : ""}" data-id="${it.id}">
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
            const id = card.dataset.id;
            if (pickerModal._selected.has(id)) {
                pickerModal._selected.delete(id);
                card.classList.remove("is-selected");
            } else {
                pickerModal._selected.add(id);
                card.classList.add("is-selected");
            }
            const n = pickerModal._selected.size;
            pickerModal.querySelector(".picker-sel-count").textContent = `已选 ${n} 张`;
            pickerModal.querySelector(".picker-confirm").disabled = n === 0;
        });
    });
}

function confirmPicker() {
    const items = pickerModal._itemsCache || [];
    for (const id of pickerModal._selected) {
        const it = items.find(x => x.id === id);
        if (!it) continue;
        state.images.push({
            image_id: it.id,
            path: it.path,
            previewUrl: `/api/library/${it.id}/thumb`,
            name: it.original_name,
            rotation: 0,
            w: it.width_px || 0,
            h: it.height_px || 0,
        });
    }
    closePicker();
    renderImgList();
}

document.getElementById("add-pick").addEventListener("click", openPicker);

// ---- 提交 ----

async function submit() {
    if (state.images.length === 0) return;
    const body = {
        canvas: {
            width_mm: parseFloat(document.getElementById("cfg-width").value),
            height_mm: parseFloat(document.getElementById("cfg-height").value),
            dpi: parseInt(document.getElementById("cfg-dpi").value, 10),
        },
        output: { format: "tif", compression: "deflate" },
        save_name: document.getElementById("cfg-save-name").value.trim() || undefined,
        slots: state.images.map(im => ({ image_id: im.image_id, rotation: im.rotation })),
    };

    imposeBtn.disabled = true;
    const res = await fetch("/api/impose/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    imposeBtn.disabled = false;
    if (!res.ok) {
        alert("提交失败: " + (data.detail || res.status));
        return;
    }
    // 清空图件列表准备下次
    state.images = [];
    renderImgList();
}

imposeBtn.addEventListener("click", submit);

// ---- 初始化 ----
renderImgList();
