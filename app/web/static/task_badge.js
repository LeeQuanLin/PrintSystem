// 全站任务徽标：连接 WS 维护任务表，更新顶栏 #task-count，供页面订阅任务变化。
// 印前生成页 app.js 订阅本表渲染任务列表；其他页面仅显示徽标数字。
window.taskStore = (function () {
    const tasks = {};            // task_id -> task dict
    const listeners = [];        // 任务变化订阅者（接收任务数组）

    function notify() {
        const list = Object.values(tasks);
        // 顶栏徽标：任务总数
        const el = document.getElementById("task-count");
        if (el) el.textContent = list.length;
        listeners.forEach(fn => fn(list));
    }

    function connectWS() {
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${location.host}/ws`);
        ws.onmessage = e => {
            const msg = JSON.parse(e.data);
            tasks[msg.task_id] = msg;
            notify();
        };
        ws.onclose = () => setTimeout(connectWS, 2000);  // 断线重连
        ws.onerror = () => ws.close();
    }

    connectWS();

    return {
        /** 订阅任务变化，立即用当前任务数组回调一次。 */
        subscribe(fn) { listeners.push(fn); fn(Object.values(tasks)); },
        /** 当前全部任务（数组副本）。 */
        all() { return Object.values(tasks); },
    };
})();
