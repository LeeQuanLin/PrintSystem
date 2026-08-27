// 文件库页：拉取列表、筛选、缩略图网格、下载、删除

const grid = document.getElementById("lib-grid");
const searchInput = document.getElementById("lib-search");
const seg = document.getElementById("source-seg");

const filter = { source: "", q: "" };
const PAGE_SIZE = 24;
let page = 1;           // 当前页（1 起）
let total = 0;          // 当前筛选条件下的总条数
let searchTimer = null;

const SOURCE_LABEL = { upload: "上传", prepress: "印前产物", impose: "排版产物" };

async function load() {
    grid.innerHTML = `<div class="empty">加载中…</div>`;
    const params = new URLSearchParams();
    if (filter.source) params.set("source", filter.source);
    if (filter.q) params.set("q", filter.q);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String((page - 1) * PAGE_SIZE));
    let res;
    try {
        res = await fetch("/api/library?" + params.toString());
    } catch (e) {
        grid.innerHTML = `<div class="empty">网络错误</div>`;
        return;
    }
    const data = await res.json();
    total = data.total ?? data.items?.length ?? 0;
    render(data.items || []);
}

function render(items) {
    if (items.length === 0) {
        grid.innerHTML = `<div class="empty">没有符合条件的文件。</div>`;
        renderPager();
        return;
    }
    grid.innerHTML = items.map(it => renderCard(it)).join("");
    grid.querySelectorAll("[data-del]").forEach(btn => {
        btn.addEventListener("click", () => del(btn.dataset.del));
    });
    renderPager();
}

// 分页栏：上一页 / 页码 / 下一页
function renderPager() {
    let pager = document.getElementById("lib-pager");
    if (!pager) {
        pager = document.createElement("div");
        pager.id = "lib-pager";
        pager.className = "lib-pager";
        grid.parentNode.insertBefore(pager, grid.nextSibling);
    }
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (total === 0) { pager.innerHTML = ""; return; }
    pager.innerHTML = `
        <button class="pager-btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>
        <span class="pager-info">第 ${page} / ${totalPages} 页 · 共 ${total} 条</span>
        <button class="pager-btn" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>下一页</button>`;
    pager.querySelectorAll("[data-page]").forEach(b => {
        if (b.disabled) return;
        b.addEventListener("click", () => {
            const p = parseInt(b.dataset.page, 10);
            if (p >= 1 && p <= totalPages) { page = p; load(); }
        });
    });
}

// 文件库卡片：缩略图 + 四行元信息 + 操作
// 行1 图片名 / 行2 类型标签+格式标签 / 行3 配置类型+尺码（仅印前产物）/ 行4 实际尺寸+文件大小
function renderCard(it) {
    const fmtTag = (it.format || "").toUpperCase();
    const isPrepress = it.source === "prepress";
    // 第3行：仅印前产物展示配置类型 + 尺码
    const refRow = isPrepress ? `
        <div class="lib-row">
            <span class="lib-kv"><span class="lib-k">类型</span><span class="lib-v">${escapeHtml(it.ref_type || "—")}</span></span>
            <span class="lib-kv"><span class="lib-k">尺码</span><span class="lib-v">${escapeHtml(it.ref_size || "—")}</span></span>
        </div>` : "";
    return `
        <div class="lib-card" data-id="${it.id}">
            <div class="lib-thumb" style="background-image:url('/api/library/${it.id}/thumb')"></div>
            <div class="lib-meta">
                <div class="lib-name" title="${escapeHtml(it.original_name)}">${escapeHtml(it.original_name)}</div>
                <div class="lib-row">
                    <span class="lib-tag lib-tag-${it.source}">${SOURCE_LABEL[it.source] || it.source}</span>
                    <span class="lib-tag lib-tag-fmt">${fmtTag || "?"}</span>
                </div>
                ${refRow}
                <div class="lib-row">
                    <span class="lib-kv"><span class="lib-k">尺寸</span><span class="lib-v">${it.width_px || "?"}×${it.height_px || "?"}px</span></span>
                    <span class="lib-kv"><span class="lib-k">大小</span><span class="lib-v">${fmtSize(it.size_bytes)}</span></span>
                </div>
            </div>
            <div class="lib-actions">
                <a class="lib-btn" href="/api/library/${it.id}/download" download>下载</a>
                <button class="lib-btn lib-btn-del" data-del="${it.id}">删除</button>
            </div>
        </div>`;
}

async function del(id) {
    if (!confirm("确认删除该文件？原图与缩略图将一并移除。")) return;
    const res = await fetch(`/api/library/${id}`, { method: "DELETE" });
    if (res.ok) {
        // 删除后若当前页只剩这一条且非首页，回退一页
        const left = grid.querySelectorAll("[data-del]").length;
        if (left <= 1 && page > 1) page--;
        load();
    } else alert("删除失败");
}

function fmtSize(n) {
    if (!n) return "?";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
}

function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

// 来源分段切换
seg.querySelectorAll(".seg-btn").forEach(b => {
    b.addEventListener("click", () => {
        seg.querySelectorAll(".seg-btn").forEach(x => x.classList.remove("is-active"));
        b.classList.add("is-active");
        filter.source = b.dataset.source;
        page = 1;
        load();
    });
});

// 搜索（防抖）
searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        filter.q = searchInput.value.trim();
        page = 1;
        load();
    }, 250);
});

load();
