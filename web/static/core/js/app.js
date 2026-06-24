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

    /* Close any open <details> menu (e.g. .status-menu) on outside click / Escape */
    document.addEventListener("click", function (e) {
        document.querySelectorAll("details.status-menu[open]").forEach(function (d) {
            if (!d.contains(e.target)) d.removeAttribute("open");
        });
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            document.querySelectorAll("details.status-menu[open]").forEach(function (d) {
                d.removeAttribute("open");
            });
        }
    });

    /* ----------------------------------------------------------------
       Styled confirmation dialog (replaces native confirm()).
       Any <form data-confirm ...> intercepts its first submit, shows the
       .modal component populated from data-confirm-* attributes, and only
       submits for real once the user accepts. Falls through to a native
       submit if JS is unavailable, so the action is never silently lost.
       ---------------------------------------------------------------- */
    var CONFIRM_ICONS = {
        danger: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        primary: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
    };

    function buildConfirmModal(opts) {
        var variant = opts.variant === "primary" ? "primary" : "danger";
        var overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.setAttribute("role", "presentation");
        var acceptClass = variant === "primary" ? "btn btn--primary" : "btn btn--danger";
        var modal = document.createElement("div");
        modal.className = "modal";
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", "confirm-title");
        modal.setAttribute("aria-describedby", "confirm-body");
        // Static markup + hardcoded icons only; user-supplied strings are set via
        // textContent below, never interpolated into this innerHTML.
        modal.innerHTML =
            '<div class="modal__head">' +
            '<span class="modal__icon' + (variant === "primary" ? " modal__icon--primary" : "") + '" aria-hidden="true">' + (CONFIRM_ICONS[variant] || "") + '</span>' +
            '<h2 class="modal__title" id="confirm-title"></h2>' +
            '</div>' +
            '<div class="modal__body" id="confirm-body"></div>' +
            '<div class="modal__foot">' +
            '<button type="button" class="btn btn--ghost" data-modal-cancel></button>' +
            '<button type="button" class="' + acceptClass + '" data-modal-accept></button>' +
            '</div>';
        modal.querySelector(".modal__title").textContent = opts.title || "Confirmar";
        modal.querySelector(".modal__body").textContent = opts.body || "";
        modal.querySelector("[data-modal-accept]").textContent = opts.accept || "Confirmar";
        modal.querySelector("[data-modal-cancel]").textContent = "Voltar";
        overlay.appendChild(modal);
        return overlay;
    }

    function openConfirm(form) {
        var overlay = buildConfirmModal({
            title: form.getAttribute("data-confirm-title"),
            body: form.getAttribute("data-confirm-body"),
            accept: form.getAttribute("data-confirm-accept"),
            variant: form.getAttribute("data-confirm-variant")
        });
        var lastFocus = document.activeElement;
        document.body.appendChild(overlay);
        document.body.style.overflow = "hidden";

        var acceptBtn = overlay.querySelector("[data-modal-accept]");
        var cancelBtn = overlay.querySelector("[data-modal-cancel]");
        var focusables = [cancelBtn, acceptBtn];

        function close() {
            overlay.remove();
            document.body.style.overflow = "";
            document.removeEventListener("keydown", onKey, true);
            if (lastFocus && lastFocus.focus) lastFocus.focus();
        }
        function onKey(e) {
            if (e.key === "Escape") {
                e.preventDefault();
                close();
            } else if (e.key === "Tab") {
                // Trap focus between the two dialog buttons.
                e.preventDefault();
                var i = focusables.indexOf(document.activeElement);
                var next = e.shiftKey ? i - 1 : i + 1;
                if (next < 0) next = focusables.length - 1;
                if (next >= focusables.length) next = 0;
                focusables[next].focus();
            }
        }

        cancelBtn.addEventListener("click", close);
        overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
        acceptBtn.addEventListener("click", function () {
            form.setAttribute("data-confirmed", "1");
            close();
            if (form.requestSubmit) form.requestSubmit();
            else form.submit();
        });
        document.addEventListener("keydown", onKey, true);
        acceptBtn.focus();
    }

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (e) {
            if (form.getAttribute("data-confirmed") === "1") {
                form.removeAttribute("data-confirmed");
                return; // already confirmed — let the submit through
            }
            e.preventDefault();
            // Close any open status menu so the modal isn't layered under it.
            var menu = form.closest("details.status-menu[open]");
            if (menu) menu.removeAttribute("open");
            openConfirm(form);
        });
    });
});
