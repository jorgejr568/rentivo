document.addEventListener("DOMContentLoaded", function () {
    /* Mobile topbar toggle */
    var toggler = document.querySelector(".topbar-toggle");
    if (toggler) {
        toggler.addEventListener("click", function () {
            var menu = document.querySelector(".topbar-menu");
            if (menu) menu.classList.toggle("open");
        });
    }

    /* Account dropdown toggle */
    document.querySelectorAll(".topbar-dropdown-toggle").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            var dropdown = btn.closest(".topbar-dropdown");
            var isOpen = dropdown.classList.contains("open");
            document.querySelectorAll(".topbar-dropdown.open").forEach(function (d) {
                d.classList.remove("open");
            });
            if (!isOpen) dropdown.classList.add("open");
            btn.setAttribute("aria-expanded", !isOpen);
        });
    });

    /* Button dropdowns (e.g. bill action bar "Enviar comunicação") */
    document.querySelectorAll(".btn-dropdown-toggle").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            var dropdown = btn.closest(".btn-dropdown");
            var isOpen = dropdown.classList.contains("open");
            document.querySelectorAll(".btn-dropdown.open").forEach(function (d) {
                d.classList.remove("open");
            });
            if (!isOpen) dropdown.classList.add("open");
            btn.setAttribute("aria-expanded", !isOpen);
        });
    });

    /* Close dropdowns on outside click */
    document.addEventListener("click", function () {
        document.querySelectorAll(".topbar-dropdown.open, .btn-dropdown.open").forEach(function (d) {
            d.classList.remove("open");
            var btn = d.querySelector(".topbar-dropdown-toggle, .btn-dropdown-toggle");
            if (btn) btn.setAttribute("aria-expanded", "false");
        });
    });

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
