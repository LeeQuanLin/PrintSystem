// 全站导航：移动端抽屉菜单 + 配置子菜单折叠 + 当前页高亮展开

(function () {
    // 移动端抽屉
    const menuToggle = document.getElementById("menu-toggle");
    const scrim = document.getElementById("scrim");
    function setMenu(open) { document.body.dataset.menu = open ? "open" : "closed"; }
    menuToggle?.addEventListener("click", () => setMenu(document.body.dataset.menu !== "open"));
    scrim?.addEventListener("click", () => setMenu(false));

    // 配置子菜单折叠
    const group = document.getElementById("cfg-nav-group");
    const parent = group?.querySelector(".nav-parent");
    // 当前页若是配置子页，默认展开
    const page = document.body.dataset.page;
    if (group && page && page.startsWith("config-")) {
        group.classList.add("is-open");
    }
    parent?.addEventListener("click", () => group?.classList.toggle("is-open"));
})();
