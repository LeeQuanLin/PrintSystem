// 印前配置图形编辑器 · 画布模块
// SVG 按 mm 比例渲染：出血区、成品区、zones 矩形、选中高亮、边框标记。
// 通过 window.cfg 命名空间与主控/表单模块通信。

window.cfg = window.cfg || {};

cfg.canvas = {
    /**
     * 渲染中栏画布 SVG。
     * 画布尺寸 = 成品 + 2×出血。viewBox 用 mm 值，SVG 自适应容器宽度。
     */
    render() {
        const st = cfg.state;
        if (!st || !st.params) return;
        const p = st.params;
        const bleed = p.bleed_mm || 0;
        const cw = (p.width_mm || 0) + 2 * bleed;
        const ch = (p.height_mm || 0) + 2 * bleed;
        if (cw <= 0 || ch <= 0) {
            cfg.dom.canvas.innerHTML = `<div class="empty">画布尺寸无效，请先设置成品宽高。</div>`;
            return;
        }

        const parts = [];
        // 出血区（外框虚线）
        parts.push(rect(0, 0, cw, ch, "cfg-cv-bleed"));
        // 成品区（内框实线，位于出血内）
        parts.push(rect(bleed, bleed, p.width_mm, p.height_mm, "cfg-cv-product"));
        // 成品尺寸标注
        parts.push(text(p.width_mm + "×" + p.height_mm + " mm", bleed + p.width_mm / 2, bleed + p.height_mm / 2, "cfg-cv-dim"));

        // zones
        (p.zones || []).forEach((z, i) => {
            const sel = i === st.selectedZoneIdx;
            const cls = (z.type === "color") ? "cfg-cv-zone-color" : "cfg-cv-zone-image";
            parts.push(rect(z.x_mm || 0, z.y_mm || 0, z.width_mm || 0, z.height_mm || 0,
                "cfg-cv-zone " + cls + (sel ? " is-selected" : ""), i));
            // 区名标注（左上角）
            parts.push(text(z.name || "", (z.x_mm || 0) + 2, (z.y_mm || 0) + 10, "cfg-cv-zonename"));
            // 纯色区填充色块示意
            if (z.type === "color" && z.color) {
                parts.push(`<rect x="${z.x_mm || 0}" y="${z.y_mm || 0}" width="${z.width_mm || 0}" height="${z.height_mm || 0}"
                    fill="rgb(${z.color.join(",")})" opacity="0.5" pointer-events="none"/>`);
            }
        });

        // 边框标记（虚线矩形，支持多个）
        const borders = p.marks?.border_marks || [];
        borders.forEach(bm => {
            if (!bm.enabled) return;
            const dash = `${bm.dash_length_mm || 2} ${(bm.gap_length_mm || 2)}`;
            parts.push(`<rect x="${bm.x_mm || 0}" y="${bm.y_mm || 0}" width="${bm.width_mm || 0}" height="${bm.height_mm || 0}"
                fill="none" stroke="${escapeHtml(bm.color || "black")}" stroke-width="${bm.width_mm_line || 0.17}"
                stroke-dasharray="${dash}" pointer-events="none" class="cfg-cv-border"/>`);
        });

        const svg = `<svg class="cfg-cv-svg" viewBox="0 0 ${cw} ${ch}" preserveAspectRatio="xMidYMid meet">
            ${parts.join("")}</svg>`;
        cfg.dom.canvas.innerHTML = `<div class="cfg-cv-wrap">${svg}
            <div class="cfg-cv-hint">画布 ${cw}×${ch} mm（含出血 ${bleed} mm）· 点击区域选中</div></div>`;

        // 点击 zone 选中
        cfg.dom.canvas.querySelectorAll(".cfg-cv-zone").forEach(el => {
            el.addEventListener("click", () => {
                st.selectedZoneIdx = +el.dataset.idx;
                cfg.nav.select("zone");
                cfg.canvas.render();
            });
        });
    },
};

// ---- SVG 片段辅助 ----
function rect(x, y, w, h, cls, idx) {
    const idxAttr = idx !== undefined ? `data-idx="${idx}"` : "";
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" class="${cls}" ${idxAttr}/>`;
}
function text(content, x, y, cls) {
    return `<text x="${x}" y="${y}" class="${cls}" text-anchor="middle">${escapeHtml(content)}</text>`;
}
function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}
