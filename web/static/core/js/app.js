document.addEventListener("DOMContentLoaded", function () {
    /* Mobile topbar toggle */
    var toggler = document.querySelector(".topbar-toggle");
    if (toggler) {
        toggler.addEventListener("click", function () {
            var menu = document.querySelector(".topbar-menu");
            if (menu) menu.classList.toggle("open");
        });
    }

    /* Toast dismiss */
    document.querySelectorAll(".toast[data-dismissible] .toast-close").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var toast = btn.closest(".toast");
            if (toast) {
                toast.style.transition = "opacity 0.15s, transform 0.15s";
                toast.style.opacity = "0";
                toast.style.transform = "translateX(20px)";
                setTimeout(function () { toast.remove(); }, 150);
            }
        });
    });
});
