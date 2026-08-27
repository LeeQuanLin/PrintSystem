// 印前配置图形编辑器 · 表单模块
// 各模块参数表单渲染 + 字段双向绑定到 state.params。
// 通过全局命名空间 window.cfg 与主控/画布模块通信。

window.cfg = window.cfg || {};

// ---- 颜色转换 ----
function rgbToHex(rgb) {
    if (!rgb || rgb.length < 3) return "#000000";
    return "#" + rgb.slice(0, 3).map(v => Math.max(0, Math.min(255, v|0)).toString(16).padStart(2, "0")).join("");
}
function hexToRgb(hex) {
    const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex || "");
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
}
function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

// ---- 字段控件（返回 HTML 片段，用 data-kind/data-key 标识供绑定）----
function fNum(label, value, key, { step = 1, min, placeholder = "" } = {}) {
    const minA = min !== undefined ? `min="${min}"` : "";
    return `<label class="field"><span class="field-label">${label}</span>
        <input type="number" data-kind="num" data-key="${key}" step="${step}" ${minA}
               value="${value ?? ""}" placeholder="${placeholder}"></label>`;
}
function fText(label, value, key, placeholder = "") {
    return `<label class="field"><span class="field-label">${label}</span>
        <input type="text" data-kind="text" data-key="${key}"
               value="${escapeHtml(value ?? "")}" placeholder="${placeholder}"></label>`;
}
function fSelect(label, value, key, options) {
    const opts = options.map(o => `<option value="${o.v}" ${o.v === value ? "selected" : ""}>${o.t}</option>`).join("");
    return `<label class="field"><span class="field-label">${label}</span>
        <select data-kind="select" data-key="${key}">${opts}</select></label>`;
}
function fSwitch(label, checked, key) {
    return `<label class="cfg-switch-field">
        <span class="field-label">${label}</span>
        <input type="checkbox" data-kind="switch" data-key="${key}" ${checked ? "checked" : ""}>
        <span class="cfg-switch"></span></label>`;
}
function fColor(label, rgb, key) {
    return `<label class="field"><span class="field-label">${label}</span>
        <input type="color" data-kind="color" data-key="${key}" value="${rgbToHex(rgb)}"></label>`;
}

// 通用绑定：遍历容器内 [data-key]，按 kind 解析值写入 obj，change 时回调
function bindAll(container, obj, onChange) {
    container.querySelectorAll("[data-key]").forEach(el => {
        const { kind, key } = el.dataset;
        const fire = () => {
            if (kind === "num") obj[key] = parseFloat(el.value);
            else if (kind === "select") obj[key] = el.value;
            else if (kind === "switch") obj[key] = el.checked;
            else if (kind === "color") obj[key] = hexToRgb(el.value);
            else if (kind === "text") obj[key] = el.value;
            onChange(key);
        };
        el.addEventListener("change", fire);
        if (kind === "text" || kind === "num") el.addEventListener("input", fire);
    });
}

// 标题分隔
function section(title, bodyHtml) {
    return `<div class="cfg-form-section"><div class="cfg-form-title">${title}</div>
        <div class="cfg-form-grid">${bodyHtml}</div></div>`;
}

// ---- 模块表单 ----

function renderCanvas(p) {
    const html = section("画布参数",
        fNum("成品宽 mm", p.width_mm, "width_mm", { step: 1, min: 1 }) +
        fNum("成品高 mm", p.height_mm, "height_mm", { step: 1, min: 1 }) +
        fNum("出血 mm", p.bleed_mm, "bleed_mm", { step: 0.5, min: 0 }) +
        fNum("DPI", p.dpi, "dpi", { step: 1, min: 1 }) +
        fSelect("位深", p.bitdepth, "bitdepth", [{ v: 8, t: "8 位" }, { v: 16, t: "16 位" }]) +
        fText("色彩配置", p.color_profile, "color_profile", "如 srgb"));
    return { html, bind: (c) => bindAll(c, p, () => cfg.canvas.render()) };
}

function renderBackground(p) {
    const bg = p.background || { enabled: true, fill_color: [255, 255, 255] };
    p.background = bg;
    const html = section("背景层",
        fSwitch("启用背景", bg.enabled, "enabled") +
        fColor("填充色 RGB", bg.fill_color, "fill_color"));
    return { html, bind: (c) => bindAll(c, bg, () => cfg.canvas.render()) };
}

function renderSolidLayer(p) {
    // 独立纯色层：整画布基色，手动色或自动取色二选一
    const sl = p.solid_layer || { enabled: false, name: "SolidColor", color: [255, 255, 255] };
    p.solid_layer = sl;
    const hasAuto = !!sl.auto_color;
    const imgNames = p.zones.filter(x => x.type === "image").map(x => x.name);
    if (!hasAuto && !sl.color) sl.color = [255, 255, 255];
    if (hasAuto && !sl.auto_color.source && imgNames.length) sl.auto_color.source = imgNames[0];

    const colorFields = `
        <div class="cfg-form-row">
            <label class="cfg-radio"><input type="radio" name="slmode" ${!hasAuto ? "checked" : ""}>
                <span>手动 color</span></label>
            <label class="cfg-radio"><input type="radio" name="slmode" ${hasAuto ? "checked" : ""}>
                <span>自动主色 auto_color</span></label>
        </div>
        <div class="cfg-color-wrap" data-mode="manual" ${hasAuto ? "hidden" : ""}>
            ${fColor("填充色", sl.color || [255, 255, 255], "color")}</div>
        <div class="cfg-color-wrap" data-mode="auto" ${hasAuto ? "" : "hidden"}>
            ${fSelect("取色来源", sl.auto_color?.source || "", "ac_source", imgNames.map(n => ({ v: n, t: n })))}
            ${fSelect("取色方法", sl.auto_color?.method || "dominant", "ac_method",
                [{ v: "dominant", t: "dominant 主色" }, { v: "average", t: "average 均色" }])}</div>`;

    const html = section("独立纯色层",
        fSwitch("启用纯色层", sl.enabled, "enabled") +
        fText("图层名 (ASCII)", sl.name, "name", "SolidColor") +
        colorFields);
    return { html, bind: (c) => bindSolidLayer(c, p, sl) };
}

function bindSolidLayer(container, p, sl) {
    // 顶层 enabled / name
    ["enabled", "name"].forEach(key => {
        const el = container.querySelector(`[data-key="${key}"]`);
        if (!el) return;
        const kind = el.dataset.kind;
        const fire = () => {
            if (kind === "switch") sl[key] = el.checked;
            else if (kind === "text") sl[key] = el.value;
            cfg.canvas.render();
        };
        el.addEventListener("change", fire);
        if (kind === "text") el.addEventListener("input", fire);
    });
    // 手动/自动切换
    container.querySelectorAll('input[name="slmode"]').forEach((r, i) => {
        r.addEventListener("change", () => {
            const useAuto = i === 1;
            if (useAuto) {
                const imgNames = p.zones.filter(x => x.type === "image").map(x => x.name);
                sl.auto_color = { source: imgNames[0] || "", method: "dominant" };
                delete sl.color;
            } else {
                sl.color = [255, 255, 255];
                delete sl.auto_color;
            }
            cfg.forms.render("solid_layer");
            cfg.canvas.render();
        });
    });
    // color 值
    const colorEl = container.querySelector('[data-key="color"]');
    if (colorEl) colorEl.addEventListener("change", () => { sl.color = hexToRgb(colorEl.value); cfg.canvas.render(); });
    // auto_color 子字段
    const acSrc = container.querySelector('[data-key="ac_source"]');
    const acMth = container.querySelector('[data-key="ac_method"]');
    if (acSrc) acSrc.addEventListener("change", () => { sl.auto_color.source = acSrc.value; });
    if (acMth) acMth.addEventListener("change", () => { sl.auto_color.method = acMth.value; });
}

function renderZone(p, idx) {
    const z = p.zones[idx];
    const isImg = z.type === "image";
    let typeFields = "";
    if (isImg) {
        typeFields = fSelect("适配模式", z.fit_mode || "stretch", "fit_mode",
            [{ v: "stretch", t: "stretch 拉伸" }, { v: "contain", t: "contain 留白" }, { v: "cover", t: "cover 裁切" }]);
    } else {
        // 纯色区：color 或 auto_color 二选一
        const hasAuto = !!z.auto_color;
        const imgNames = p.zones.filter(x => x.type === "image").map(x => x.name);
        typeFields = `<div class="cfg-form-row">
            <label class="cfg-radio"><input type="radio" name="colormode${idx}" ${!hasAuto ? "checked" : ""}>
                <span>手动 color</span></label>
            <label class="cfg-radio"><input type="radio" name="colormode${idx}" ${hasAuto ? "checked" : ""}>
                <span>自动主色 auto_color</span></label></div>`;
        if (!hasAuto && !z.color) z.color = [255, 255, 255];
        if (hasAuto && !z.auto_color.source && imgNames.length) z.auto_color.source = imgNames[0];
        typeFields += `<div class="cfg-color-wrap" data-mode="manual">
            ${fColor("填充色", z.color || [255,255,255], "color")}</div>`;
        typeFields += `<div class="cfg-color-wrap" data-mode="auto" ${hasAuto ? "" : "hidden"}>
            ${fSelect("取色来源", z.auto_color?.source || "", "ac_source", imgNames.map(n => ({ v: n, t: n })))}
            ${fSelect("取色方法", z.auto_color?.method || "dominant", "ac_method",
                [{ v: "dominant", t: "dominant 主色" }, { v: "average", t: "average 均色" }])}</div>`;
    }
    // 四角裁剪
    const cc = z.corner_crop;
    const ccHtml = `<div class="cfg-form-row cc-wrap">
        ${fSwitch("四角裁剪", !!cc, "cc_enabled")}
        <div class="cc-detail" ${cc ? "" : "hidden"}>
            ${fSelect("样式", cc?.style || "square", "cc_style",
                [{ v: "square", t: "square 直角" }, { v: "rounded", t: "rounded 圆角" }, { v: "chamfer", t: "chamfer 倒角" }])}
            ${fNum("圆角半径 mm", cc?.radius_mm || 0, "cc_radius", { step: 0.5, min: 0 })}
            ${fNum("倒角 mm", cc?.chamfer_mm || 0, "cc_chamfer", { step: 0.5, min: 0 })}
        </div></div>`;

    const html =
        section("区域位置与尺寸",
            fText("区名 (ASCII)", z.name, "name", "如 FaceA") +
            fSelect("类型", z.type, "type", [{ v: "image", t: "image 图片区" }, { v: "color", t: "color 纯色区" }]) +
            fNum("X mm", z.x_mm, "x_mm", { step: 1 }) +
            fNum("Y mm", z.y_mm, "y_mm", { step: 1 }) +
            fNum("宽 mm", z.width_mm, "width_mm", { step: 1, min: 0 }) +
            fNum("高 mm", z.height_mm, "height_mm", { step: 1, min: 0 })) +
        section("适配 / 颜色", typeFields) +
        section("四角裁剪", ccHtml) +
        section("微调",
            fNum("偏移 X mm", z.offset_x_mm || 0, "offset_x_mm", { step: 1 }) +
            fNum("偏移 Y mm", z.offset_y_mm || 0, "offset_y_mm", { step: 1 }) +
            fNum("缩放", z.scale || 1, "scale", { step: 0.05, min: 0 }) +
            fNum("旋转°", z.rotation || 0, "rotation", { step: 1 }));

    return { html, bind: (container) => bindZone(container, p, z, idx) };
}

function bindZone(container, p, z, idx) {
    // 顶层字段
    const topKeys = ["name", "type", "x_mm", "y_mm", "width_mm", "height_mm",
        "fit_mode", "offset_x_mm", "offset_y_mm", "scale", "rotation"];
    container.querySelectorAll("[data-key]").forEach(el => {
        if (!topKeys.includes(el.dataset.key)) return;
        const { kind, key } = el.dataset;
        const fire = () => {
            if (key === "type") {
                z.type = el.value;
                if (z.type === "image") { delete z.color; delete z.auto_color; z.fit_mode = z.fit_mode || "stretch"; }
                else { delete z.fit_mode; if (!z.auto_color) z.color = [255, 255, 255]; }
                cfg.forms.render("zone");   // 重渲染整个 zone 表单（字段集变化）
                cfg.nav.render();           // 左栏 zone 列表类型标识刷新
                cfg.canvas.render();
                return;
            }
            if (kind === "num") z[key] = parseFloat(el.value);
            else if (kind === "text") z[key] = el.value;
            else if (kind === "select") z[key] = el.value;
            cfg.canvas.render();
            if (key === "name") cfg.nav.render();
        };
        el.addEventListener("change", fire);
        if (kind === "text" || kind === "num") el.addEventListener("input", fire);
    });

    // 纯色区 color/auto_color 切换
    const radios = container.querySelectorAll(`input[name="colormode${idx}"]`);
    radios.forEach((r, i) => r.addEventListener("change", () => {
        const useAuto = i === 1;
        if (useAuto) {
            const imgNames = p.zones.filter(x => x.type === "image").map(x => x.name);
            z.auto_color = { source: imgNames[0] || "", method: "dominant" };
            delete z.color;
        } else {
            z.color = [255, 255, 255];
            delete z.auto_color;
        }
        cfg.forms.render("zone");
        cfg.canvas.render();
    }));
    // color 值绑定
    const colorEl = container.querySelector('[data-key="color"]');
    if (colorEl) colorEl.addEventListener("change", () => { z.color = hexToRgb(colorEl.value); cfg.canvas.render(); });
    // auto_color 子字段
    const acSrc = container.querySelector('[data-key="ac_source"]');
    const acMth = container.querySelector('[data-key="ac_method"]');
    if (acSrc) acSrc.addEventListener("change", () => { z.auto_color.source = acSrc.value; });
    if (acMth) acMth.addEventListener("change", () => { z.auto_color.method = acMth.value; });

    // 四角裁剪开关与子字段
    bindCornerCrop(container, z);
}

function bindCornerCrop(container, z) {
    const sw = container.querySelector('[data-key="cc_enabled"]');
    const detail = container.querySelector(".cc-detail");
    if (!sw || !detail) return;
    sw.addEventListener("change", () => {
        if (sw.checked) {
            z.corner_crop = { style: "square", radius_mm: 0, chamfer_mm: 0 };
            detail.hidden = false;
            cfg.forms.render("zone");
        } else {
            z.corner_crop = null;
            detail.hidden = true;
        }
        cfg.canvas.render();
    });
    const styleEl = container.querySelector('[data-key="cc_style"]');
    const radEl = container.querySelector('[data-key="cc_radius"]');
    const chamEl = container.querySelector('[data-key="cc_chamfer"]');
    if (styleEl) styleEl.addEventListener("change", () => { z.corner_crop.style = styleEl.value; });
    if (radEl) radEl.addEventListener("change", () => { z.corner_crop.radius_mm = parseFloat(radEl.value); });
    if (chamEl) chamEl.addEventListener("change", () => { z.corner_crop.chamfer_mm = parseFloat(chamEl.value); });
}

// ---- 标记层 ----

function renderCropMarks(p) {
    const m = p.marks.crop_marks;
    const html = section("裁剪线（沿像素包围盒内描边）",
        `<p class="cfg-form-hint">沿实际非透明像素包围盒内侧描绘一圈矩形边线，非传统四角角标。</p>` +
        fSwitch("启用", m.enabled, "enabled") +
        fText("颜色", m.color, "color", "black") +
        fNum("线粗 mm", m.width_mm, "width_mm", { step: 0.1, min: 0 }) +
        fSwitch("虚线", m.dashed, "dashed") +
        fNum("虚线段 mm", m.dash_length_mm, "dash_length_mm", { step: 0.5, min: 0 }) +
        fNum("间隙 mm", m.gap_length_mm, "gap_length_mm", { step: 0.5, min: 0 }));
    return { html, bind: c => bindAll(c, m, () => cfg.canvas.render()) };
}

function renderZipperMarks(p) {
    const m = p.marks.zipper_marks;
    const html = section("拉链标记",
        fSwitch("启用", m.enabled, "enabled") +
        fSelect("边", m.side, "side", ["top", "bottom", "left", "right"].map(s => ({ v: s, t: s }))) +
        fNum("跨度 mm", m.span_mm, "span_mm", { step: 1, min: 0 }) +
        fNum("间距 mm", m.pitch_mm, "pitch_mm", { step: 1, min: 0 }) +
        fNum("线粗 mm", m.line_width_mm, "line_width_mm", { step: 0.1, min: 0 }) +
        fSelect("对齐", m.alignment, "alignment",
            ["start", "center", "end", "distribute"].map(s => ({ v: s, t: s }))) +
        fNum("偏移 mm", m.offset_mm, "offset_mm", { step: 0.5, min: 0 }) +
        fNum("线长 mm", m.length_mm, "length_mm", { step: 0.5, min: 0 }) +
        fText("颜色", m.color, "color", "black"));
    return { html, bind: c => bindAll(c, m, () => {}) };
}

function renderTextMarks(p) {
    const m = p.marks.text_marks;
    let itemsHtml = `<div class="cfg-text-items">`;
    (m.items || []).forEach((it, i) => {
        itemsHtml += `<div class="cfg-text-item" data-idx="${i}">
            ${fText("文字", it.text, "text", "%(name)s")}<button type="button" class="cfg-mini-del" data-del="${i}">×</button>
            ${fNum("X mm", it.x_mm, "x_mm", { step: 1 })}
            ${fNum("Y mm", it.y_mm, "y_mm", { step: 1 })}
            ${fNum("旋转°", it.rotation || 0, "rotation", { step: 1 })}</div>`;
    });
    itemsHtml += `</div><button type="button" class="cfg-add-item" id="cfg-text-add">+ 新增文字</button>`;
    const html = section("文字标记",
        fSwitch("启用", m.enabled, "enabled") +
        fText("颜色", m.color, "color", "black") +
        fNum("字号 pt", m.font_size_pt, "font_size_pt", { step: 1, min: 1 }) +
        itemsHtml);
    return { html, bind: c => bindTextItems(c, m) };
}

function bindTextItems(container, m) {
    // 仅绑定 text_marks 顶层字段（enabled/color/font_size_pt）。
    // 不能用 bindAll 扫全容器：item 内输入框也有 data-key="text"/"x_mm" 等，
    // 会被误写到 m 顶层，保存时触发 Pydantic extra_forbidden。
    ["enabled", "color", "font_size_pt"].forEach(key => {
        const el = container.querySelector(`[data-key="${key}"]`);
        if (!el) return;
        const kind = el.dataset.kind;
        const fire = () => {
            if (kind === "switch") m[key] = el.checked;
            else if (kind === "text") m[key] = el.value;
            else if (kind === "num") m[key] = parseFloat(el.value);
        };
        el.addEventListener("change", fire);
        if (kind === "text" || kind === "num") el.addEventListener("input", fire);
    });
    // 各 item 字段（data-key 重复，按 idx 容器隔离绑定到对应 item）
    container.querySelectorAll(".cfg-text-item").forEach(itemEl => {
        const idx = +itemEl.dataset.idx;
        const it = m.items[idx];
        if (!it) return;
        itemEl.querySelectorAll("[data-key]").forEach(el => {
            const { kind, key } = el.dataset;
            const fire = () => {
                if (kind === "num") it[key] = parseFloat(el.value);
                else if (kind === "text") it[key] = el.value;
            };
            el.addEventListener("change", fire);
            if (kind === "text" || kind === "num") el.addEventListener("input", fire);
        });
        itemEl.querySelector("[data-del]")?.addEventListener("click", () => {
            m.items.splice(idx, 1);
            cfg.forms.render("text_marks");
        });
    });
    container.querySelector("#cfg-text-add")?.addEventListener("click", () => {
        m.items.push({ text: "", x_mm: 0, y_mm: 0, rotation: 0 });
        cfg.forms.render("text_marks");
    });
}

function renderBorderMarks(p) {
    // 边框标记：支持多个，每个一个独立虚线矩形图层（仿 text_marks 的 items 列表）
    const list = p.marks.border_marks || [];
    p.marks.border_marks = list;
    let itemsHtml = `<div class="cfg-text-items">`;
    list.forEach((m, i) => {
        itemsHtml += `<div class="cfg-text-item" data-idx="${i}">
            <button type="button" class="cfg-mini-del" data-del="${i}">×</button>
            ${fText("图层名 (ASCII)", m.name || `Border${i+1}`, "name", "BorderMarks")}
            ${fSwitch("启用", m.enabled, "enabled")}
            ${fText("颜色", m.color, "color", "black")}
            ${fNum("X mm", m.x_mm, "x_mm", { step: 1 })}
            ${fNum("Y mm", m.y_mm, "y_mm", { step: 1 })}
            ${fNum("宽 mm", m.width_mm, "width_mm", { step: 1, min: 0 })}
            ${fNum("高 mm", m.height_mm, "height_mm", { step: 1, min: 0 })}
            ${fNum("线粗 mm", m.width_mm_line, "width_mm_line", { step: 0.05, min: 0 })}
            ${fNum("虚线段 mm", m.dash_length_mm, "dash_length_mm", { step: 0.5, min: 0 })}
            ${fNum("间隙 mm", m.gap_length_mm, "gap_length_mm", { step: 0.5, min: 0 })}</div>`;
    });
    itemsHtml += `</div><button type="button" class="cfg-add-item" id="cfg-border-add">+ 新增边框</button>`;
    const html = section("边框标记（可多个）", itemsHtml);
    return { html, bind: c => bindBorderItems(c, list) };
}

function bindBorderItems(container, list) {
    container.querySelectorAll(".cfg-text-item").forEach(itemEl => {
        const idx = +itemEl.dataset.idx;
        const m = list[idx];
        if (!m) return;
        // 该边框的字段绑定（data-key 在 item 容器内隔离）
        itemEl.querySelectorAll("[data-key]").forEach(el => {
            const { kind, key } = el.dataset;
            const fire = () => {
                if (kind === "switch") m[key] = el.checked;
                else if (kind === "text") m[key] = el.value;
                else if (kind === "num") m[key] = parseFloat(el.value);
                cfg.canvas.render();
            };
            el.addEventListener("change", fire);
            if (kind === "text" || kind === "num") el.addEventListener("input", fire);
        });
        itemEl.querySelector("[data-del]")?.addEventListener("click", () => {
            list.splice(idx, 1);
            cfg.forms.render("border_marks");
            cfg.canvas.render();
        });
    });
    container.querySelector("#cfg-border-add")?.addEventListener("click", () => {
        list.push({ enabled: true, name: `Border${list.length + 1}`, color: "black",
            x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 100,
            width_mm_line: 0.17, dash_length_mm: 2, gap_length_mm: 2 });
        cfg.forms.render("border_marks");
        cfg.canvas.render();
    });
}

function renderOutput(p) {
    const formats = p.output.formats || [];
    const fmtHtml = ["psd", "tif", "png"].map(f =>
        `<label class="cfg-check"><input type="checkbox" data-kind="fmt" data-fmt="${f}" ${formats.includes(f) ? "checked" : ""}>${f.toUpperCase()}</label>`).join("");
    const html = section("输出",
        `<label class="field"><span class="field-label">导出格式</span><div class="cfg-form-row">${fmtHtml}</div></label>` +
        fText("保存名（含占位符）", p.output.save_name, "save_name", "%(type)s_%(size)s"));
    return { html, bind: c => bindOutput(c, p.output) };
}

function bindOutput(container, out) {
    container.querySelectorAll('[data-kind="fmt"]').forEach(el => {
        el.addEventListener("change", () => {
            const fmt = el.dataset.fmt;
            out.formats = out.formats || [];
            const i = out.formats.indexOf(fmt);
            if (el.checked && i < 0) out.formats.push(fmt);
            if (!el.checked && i >= 0) out.formats.splice(i, 1);
        });
    });
    const sn = container.querySelector('[data-key="save_name"]');
    if (sn) sn.addEventListener("change", () => { out.save_name = sn.value; });
}

// ---- 入口 ----

cfg.forms = {
    render(moduleKey) {
        const st = cfg.state;
        if (!st || !st.params) return;
        const p = st.params;
        let r;
        if (moduleKey === "canvas") r = renderCanvas(p);
        else if (moduleKey === "background") r = renderBackground(p);
        else if (moduleKey === "solid_layer") r = renderSolidLayer(p);
        else if (moduleKey === "zone") {
            const idx = st.selectedZoneIdx;
            if (idx == null || !p.zones[idx]) { cfg.nav.select("canvas"); return; }
            r = renderZone(p, idx);
        } else if (moduleKey === "crop_marks") r = renderCropMarks(p);
        else if (moduleKey === "zipper_marks") r = renderZipperMarks(p);
        else if (moduleKey === "text_marks") r = renderTextMarks(p);
        else if (moduleKey === "border_marks") r = renderBorderMarks(p);
        else if (moduleKey === "output") r = renderOutput(p);
        if (!r) return;
        cfg.dom.right.innerHTML = `<div class="cfg-form">${r.html}</div>`;
        r.bind(cfg.dom.right);
    },
};
