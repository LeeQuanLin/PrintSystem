// 全站任务徽标 + 顶栏下拉任务面板。
// 连接 WS 维护任务表，顶栏显示总数/进行中/成功/失败，点击展开任务列表。
// 各页不再自带任务队列卡片，统一在此处展示。

window.taskStore = (function () {
    const tasks = {};            // task_id -> task dict
    const listeners = [];        // 任务变化订阅者（接收任务数组）

    function notify() {
        const list = Object.values(tasks);
        renderBadge(list);
        renderPanel(list);
        listeners.forEach(fn => fn(list));
    }

    // ---- 徽标统计 ----
    function renderBadge(list) {
        const wrap = document.getElementById("task-badge");
        if (!wrap) return;
        const total = list.length;
        const running = list.filter(t => t.status === "running" || t.status === "pending").length;
        const ok = list.filter(t => t.status === "succeeded").length;
        const fail = list.filter(t => t.status === "failed").length;
        wrap.querySelector(".bd-total").textContent = total;
        wrap.querySelector(".bd-running").textContent = running;
        wrap.querySelector(".bd-ok").textContent = ok;
        wrap.querySelector(".bd-fail").textContent = fail;
        wrap.classList.toggle("has-active", running > 0);
        wrap.classList.toggle("has-fail", fail > 0);
    }

    // ---- 下拉面板 ----
    let panel = null;
    let panelOpen = false;

    function ensurePanel() {
        if (panel) return panel;
        panel = document.createElement("div");
        panel.className = "task-panel";
        panel.hidden = true;
        panel.innerHTML = `
            <div class="task-panel-head">
                <span>任务队列</span>
                <button type="button" class="task-panel-clear" aria-label="清空已完成">清空已完成</button>
            </div>
            <div class="task-panel-list"></div>`;
        document.body.appendChild(panel);
        panel.querySelector(".task-panel-clear").addEventListener("click", clearFinished);
        return panel;
    }

    function renderPanel(list) {
        if (!panel) return;  // 面板未初始化时不渲染
        const ORDER = { pending: 0, running: 1, succeeded: 2, failed: 2 };
        const sorted = list.slice().sort((a, b) => {
            const d = (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9);
            if (d !== 0) return d;
            return (b.task_id || "").localeCompare(a.task_id || "");
        });
        const body = panel.querySelector(".task-panel-list");
        if (sorted.length === 0) {
            body.innerHTML = `<div class="empty">暂无任务。</div>`;
            return;
        }
        body.innerHTML = sorted.map(t => `
            <div class="task-card ${t.status}">
                <div class="task-head">
                    <span class="task-id">${(t.task_id || "").slice(0, 8)}</span>
                    <span class="task-status">${statusLabel(t.status)}</span>
                </div>
                <div class="progress-bar"><div class="progress-fill" style="width:${t.progress || 0}%"></div></div>
                <div class="stage">${escapeHtml(t.stage || "")} ${escapeHtml(t.message || "")}</div>
                ${t.status === "succeeded" ? renderDownloads(t) : ""}
                ${t.status === "failed" ? `<div class="error">${escapeHtml(t.error || "")}</div>` : ""}
            </div>`).join("");
    }

    function statusLabel(s) {
        return ({ pending: "等待", running: "处理中", succeeded: "完成", failed: "失败" })[s] || s;
    }
    function renderDownloads(t) {
        const links = (t.outputs || []).map(o =>
            `<a href="/api/tasks/${t.task_id}/download/${o.format}" download>${(o.format || "").toUpperCase()}</a>`
        ).join("");
        const thumb = t.thumb_path
            ? `<a href="/api/tasks/${t.task_id}/thumb" target="_blank">缩略图</a>` : "";
        return `<div class="downloads">${links}${thumb}</div>`;
    }
    function escapeHtml(s) {
        return (s || "").replace(/[&<>"']/g, c => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    function togglePanel() {
        ensurePanel();
        panelOpen = !panelOpen;
        panel.hidden = !panelOpen;
        const badge = document.getElementById("task-badge");
        badge?.classList.toggle("is-open", panelOpen);
        if (panelOpen) {
            positionPanel();
            renderPanel(Object.values(tasks));
        }
    }

    function positionPanel() {
        if (!panel) return;
        const badge = document.getElementById("task-badge");
        if (!badge) return;
        const r = badge.getBoundingClientRect();
        panel.style.top = `${r.bottom + 8}px`;
        panel.style.right = `${window.innerWidth - r.right}px`;
    }

    function clearFinished() {
        for (const id of Object.keys(tasks)) {
            const st = tasks[id].status;
            if (st === "succeeded" || st === "failed") delete tasks[id];
        }
        notify();
    }

    // ---- 绑定徽标按钮 ----
    function bindBadge() {
        const badge = document.getElementById("task-badge");
        if (!badge) {
            // 元素尚未就绪，稍后重试
            setTimeout(bindBadge, 50);
            return;
        }
        if (badge.dataset.bound === "1") return;
        badge.dataset.bound = "1";
        badge.addEventListener("click", e => {
            e.stopPropagation();
            togglePanel();
        });
        // 点击外部收起
        document.addEventListener("click", e => {
            if (!panelOpen) return;
            if (panel && panel.contains(e.target)) return;
            if (badge && badge.contains(e.target)) return;
            panelOpen = false;
            panel.hidden = true;
            badge.classList.remove("is-open");
        });
        // 窗口缩放重新定位
        window.addEventListener("resize", () => { if (panelOpen) positionPanel(); });
    }

    function connectWS() {
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${location.host}/ws`);
        ws.onmessage = e => {
            const msg = JSON.parse(e.data);
            tasks[msg.task_id] = msg;
            notify();
        };
        ws.onclose = () => setTimeout(connectWS, 2000);
        ws.onerror = () => ws.close();
    }

    // 绑定徽标（脚本在 body 末尾，元素已存在；兜底重试）
    bindBadge();
    connectWS();

    return {
        subscribe(fn) { listeners.push(fn); fn(Object.values(tasks)); },
        all() { return Object.values(tasks); },
    };
})();
