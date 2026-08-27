// 文件库页：拉取列表、筛选、缩略图网格、下载、删除

const grid = document.getElementById("lib-grid");
const searchInput = document.getElementById("lib-search");
const seg = document.getElementById("source-seg");

const filter = { source: "", q: "" };
let searchTimer = null;

const SOURCE_LABEL = { upload: "上传", prepress: "印前产物", impose: "排版产物" };

async function load() {
    grid.innerHTML = `<div class="empty">加载中…</div>`;
    const params = new URLSearchParams();
    if (filter.source) params.set("source", filter.source);
    if (filter.q) params.set("q", filter.q);
    params.set("limit", "200");
    let res;
    try {
        res = await fetch("/api/library?" + params.toString());
    } catch (e) {
        grid.innerHTML = `<div class="empty">网络错误</div>`;
        return;
    }
    const data = await res.json();
    render(data.items || []);
}

function render(items) {
    if (items.length === 0) {
        grid.innerHTML = `<div class="empty">没有符合条件的文件。</div>`;
        return;
    }
    grid.innerHTML = items.map(it => `
        <div class="lib-card" data-id="${it.id}">
            <div class="lib-thumb" style="background-image:url('/api/library/${it.id}/thumb')"></div>
            <div class="lib-meta">
                <div class="lib-name" title="${escapeHtml(it.original_name)}">${escapeHtml(it.original_name)}</div>
                <div class="lib-info">
                    <span class="lib-tag lib-tag-${it.source}">${SOURCE_LABEL[it.source] || it.source}</span>
                    <span class="lib-spec">${it.width_px || "?"}×${it.height_px || "?"} · ${fmtSize(it.size_bytes)} · ${it.format.toUpperCase()}</span>
                </div>
            </div>
            <div class="lib-actions">
                <a class="lib-btn" href="/api/library/${it.id}/download" download>下载</a>
                <button class="lib-btn lib-btn-del" data-del="${it.id}">删除</button>
            </div>
        </div>
    `).join("");

    grid.querySelectorAll("[data-del]").forEach(btn => {
        btn.addEventListener("click", () => del(btn.dataset.del));
    });
}

async function del(id) {
    if (!confirm("确认删除该文件？原图与缩略图将一并移除。")) return;
    const res = await fetch(`/api/library/${id}`, { method: "DELETE" });
    if (res.ok) load();
    else alert("删除失败");
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
        load();
    });
});

// 搜索（防抖）
searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        filter.q = searchInput.value.trim();
        load();
    }, 250);
});

load();
