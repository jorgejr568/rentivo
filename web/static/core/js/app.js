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
       Unified confirm dialog (REN-37) — single source of truth for
       destructive/consequential action confirmation. Supersedes both
       the REN-12 shared dialog and the status-confirmation dialog.

       Progressive enhancement: add data-confirm to a <form> (or a
       standalone action element). Without JS the action submits
       natively, so it is never silently lost.

       Attribute contract (superset — both legacy spellings accepted):
         data-confirm           enable; its value is the message
                                (fallback when data-confirm-body absent)
         data-confirm-title     dialog heading
         data-confirm-body      message body (wins over data-confirm value)
         data-confirm-accept    accept-button text   (alias: data-confirm-label)
         data-confirm-cancel    cancel-button text
         data-confirm-variant   "danger" (default) | "primary" | "default"
                                ("default" renders as primary)

       Accessibility (REN-20 proven): role="alertdialog", aria-modal,
       labelled/described, full focus trap, Escape + overlay-click to
       cancel, focus returns to the trigger.
       ============================================================ */
    var FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
    var CONFIRM_ICONS = {
        // Warning triangle — destructive/backward moves.
        danger: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>',
        // Check circle — positive/expected moves (mark paid, reopen).
        primary: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
    };
    var activeDialog = null;

    function closeConfirm() {
        if (!activeDialog) return;
        var overlay = activeDialog.overlay;
        var trigger = activeDialog.trigger;
        document.removeEventListener("keydown", activeDialog.onKeydown, true);
        overlay.remove();
        document.body.style.overflow = "";
        activeDialog = null;
        if (trigger && typeof trigger.focus === "function") trigger.focus();
    }

    function openConfirm(opts) {
        if (activeDialog) closeConfirm();

        var titleId = "confirm-dialog-title";
        var bodyId = "confirm-dialog-body";
        // "default" is REN-12's positive value; treat it as primary styling.
        var variant = (opts.variant === "primary" || opts.variant === "default") ? "primary" : "danger";

        var overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.setAttribute("role", "presentation");

        var modal = document.createElement("div");
        modal.className = "modal";
        modal.setAttribute("role", "alertdialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", titleId);
        modal.setAttribute("aria-describedby", bodyId);

        var head = document.createElement("div");
        head.className = "modal__head";
        var icon = document.createElement("div");
        icon.className = "modal__icon" + (variant === "primary" ? " modal__icon--primary" : "");
        icon.setAttribute("aria-hidden", "true");
        // Static, hardcoded glyph — never user-supplied markup.
        icon.innerHTML = CONFIRM_ICONS[variant] || CONFIRM_ICONS.danger;
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
        okBtn.className = "btn btn--sm " + (variant === "primary" ? "btn--primary" : "btn--danger");
        okBtn.textContent = opts.confirmLabel;
        foot.appendChild(cancelBtn);
        foot.appendChild(okBtn);

        modal.appendChild(head);
        modal.appendChild(body);
        modal.appendChild(foot);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        document.body.style.overflow = "hidden";

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
            // data-confirm-body wins; fall back to the data-confirm value.
            message: el.getAttribute("data-confirm-body") || el.getAttribute("data-confirm") || "Tem certeza?",
            title: el.getAttribute("data-confirm-title") || "Confirmar ação",
            // data-confirm-accept canonical; data-confirm-label legacy alias.
            confirmLabel: el.getAttribute("data-confirm-accept") || el.getAttribute("data-confirm-label") || "Confirmar",
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
            // Close any enclosing open status menu so the modal isn't layered under it.
            var menu = form.closest("details.status-menu[open]");
            if (menu) menu.removeAttribute("open");
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

    /* Close any open <details.status-menu> on outside click / Escape */
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
});
