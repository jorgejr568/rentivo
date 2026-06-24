document.addEventListener("DOMContentLoaded", function () {
    /* Mobile topbar toggle — keeps aria-expanded in sync with the menu state */
    var toggler = document.querySelector(".topbar-toggle");
    var topbarMenu = document.querySelector(".topbar-menu");
    if (toggler && topbarMenu) {
        toggler.addEventListener("click", function () {
            var isOpen = topbarMenu.classList.toggle("open");
            toggler.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });
        /* Escape closes the mobile menu and returns focus to the toggle */
        topbarMenu.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && topbarMenu.classList.contains("open")) {
                topbarMenu.classList.remove("open");
                toggler.setAttribute("aria-expanded", "false");
                toggler.focus();
            }
        });
    }

    /* Account dropdown — disclosure pattern with keyboard support */
    function closeDropdown(dropdown, returnFocus) {
        dropdown.classList.remove("open");
        var btn = dropdown.querySelector(".topbar-dropdown-toggle");
        if (btn) {
            btn.setAttribute("aria-expanded", "false");
            if (returnFocus) btn.focus();
        }
    }

    document.querySelectorAll(".topbar-dropdown-toggle").forEach(function (btn) {
        var dropdown = btn.closest(".topbar-dropdown");
        if (!dropdown) return;

        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            var isOpen = dropdown.classList.contains("open");
            document.querySelectorAll(".topbar-dropdown.open").forEach(function (d) {
                closeDropdown(d, false);
            });
            if (!isOpen) {
                dropdown.classList.add("open");
                btn.setAttribute("aria-expanded", "true");
            }
        });

        /* Keyboard: Escape closes + returns focus to the trigger */
        dropdown.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && dropdown.classList.contains("open")) {
                e.stopPropagation();
                closeDropdown(dropdown, true);
            }
        });
    });

    /* Close any open dropdown on outside click */
    document.addEventListener("click", function () {
        document.querySelectorAll(".topbar-dropdown.open").forEach(function (d) {
            closeDropdown(d, false);
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

    /* ============================================================
       Shared confirm dialog — replaces native confirm() for
       destructive actions. Progressive enhancement: add
       data-confirm="message" to a <form> or action element.
       Optional: data-confirm-title, data-confirm-label (confirm
       button text), data-confirm-cancel, data-confirm-variant
       ("danger" default | "default").
       Accessible: role="alertdialog", labelled/described, focus
       trap, Escape to cancel, focus returns to the trigger.
       ============================================================ */
    var FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
    var activeDialog = null;

    function closeConfirm() {
        if (!activeDialog) return;
        var overlay = activeDialog.overlay;
        var trigger = activeDialog.trigger;
        document.removeEventListener("keydown", activeDialog.onKeydown, true);
        overlay.remove();
        activeDialog = null;
        if (trigger && typeof trigger.focus === "function") trigger.focus();
    }

    function openConfirm(opts) {
        if (activeDialog) closeConfirm();

        var titleId = "confirm-dialog-title";
        var bodyId = "confirm-dialog-body";
        var variant = opts.variant === "default" ? "default" : "danger";

        var overlay = document.createElement("div");
        overlay.className = "modal-overlay";

        var modal = document.createElement("div");
        modal.className = "modal";
        modal.setAttribute("role", "alertdialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", titleId);
        modal.setAttribute("aria-describedby", bodyId);

        var head = document.createElement("div");
        head.className = "modal__head";
        var icon = document.createElement("div");
        icon.className = "modal__icon";
        icon.setAttribute("aria-hidden", "true");
        // Static, hardcoded warning glyph — no user-supplied markup.
        icon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>';
        var title = document.createElement("h2");
        title.className = "modal__title";
        title.id = titleId;
        title.textContent = opts.title;
        head.appendChild(icon);
        head.appendChild(title);

        var body = document.createElement("div");
        body.className = "modal__body";
        body.id = bodyId;
        body.textContent = opts.message;

        var foot = document.createElement("div");
        foot.className = "modal__foot";
        var cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "btn btn--ghost btn--sm";
        cancelBtn.textContent = opts.cancelLabel;
        var okBtn = document.createElement("button");
        okBtn.type = "button";
        okBtn.className = "btn btn--sm " + (variant === "danger" ? "btn--danger" : "btn--primary");
        okBtn.textContent = opts.confirmLabel;
        foot.appendChild(cancelBtn);
        foot.appendChild(okBtn);

        modal.appendChild(head);
        modal.appendChild(body);
        modal.appendChild(foot);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        function onKeydown(e) {
            if (e.key === "Escape") {
                e.preventDefault();
                closeConfirm();
                return;
            }
            if (e.key === "Tab") {
                /* Focus trap inside the modal */
                var focusables = Array.prototype.slice.call(modal.querySelectorAll(FOCUSABLE));
                if (!focusables.length) return;
                var first = focusables[0];
                var last = focusables[focusables.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        }

        activeDialog = { overlay: overlay, trigger: opts.trigger, onKeydown: onKeydown };
        document.addEventListener("keydown", onKeydown, true);

        cancelBtn.addEventListener("click", closeConfirm);
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) closeConfirm();
        });
        okBtn.addEventListener("click", function () {
            var cb = opts.onConfirm;
            closeConfirm();
            if (cb) cb();
        });

        okBtn.focus();
    }

    function readOpts(el, trigger, onConfirm) {
        return {
            message: el.getAttribute("data-confirm") || "Tem certeza?",
            title: el.getAttribute("data-confirm-title") || "Confirmar ação",
            confirmLabel: el.getAttribute("data-confirm-label") || "Confirmar",
            cancelLabel: el.getAttribute("data-confirm-cancel") || "Cancelar",
            variant: el.getAttribute("data-confirm-variant") || "danger",
            trigger: trigger,
            onConfirm: onConfirm
        };
    }

    /* Forms: intercept submit, confirm, then submit programmatically */
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        var confirmed = false;
        form.addEventListener("submit", function (e) {
            if (confirmed) { confirmed = false; return; }
            e.preventDefault();
            var trigger = document.activeElement && form.contains(document.activeElement)
                ? document.activeElement : form;
            openConfirm(readOpts(form, trigger, function () {
                confirmed = true;
                if (typeof form.requestSubmit === "function") form.requestSubmit();
                else form.submit();
            }));
        });
    });

    /* Standalone action buttons/links with data-confirm (not driving a form submit) */
    document.querySelectorAll("[data-confirm]:not(form)").forEach(function (el) {
        if (el.type === "submit" || el.closest("form[data-confirm]")) return;
        el.addEventListener("click", function (e) {
            e.preventDefault();
            openConfirm(readOpts(el, el, function () {
                if (el.tagName === "A" && el.getAttribute("href")) window.location.href = el.href;
                else if (el.form && typeof el.form.requestSubmit === "function") el.form.requestSubmit();
            }));
        });
    });
});
