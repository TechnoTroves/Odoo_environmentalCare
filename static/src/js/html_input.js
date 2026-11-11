/** @odoo-module **/
/**
 * Reusable rich-text (HTML) input for Environmental Care website forms.
 * Markup comes from the QWeb template `environmental_care.html_input`.
 *
 * - The editable area's HTML is copied into a hidden <input> so it is
 *   posted with the form. The server (Odoo Html field) sanitizes it.
 * - Like Word, toolbar buttons light up (".active") for the formatting
 *   at the cursor / selection: bold, italic, list, heading, link...
 * - The toolbar only shows while the field is focused, and sticks to the
 *   top of the screen while scrolling through a long text
 *   (see static/src/scss/html_input.scss).
 */
import publicWidget from "@web/legacy/js/public/public_widget";

// Commands whose on/off state the browser can report directly
const STATE_COMMANDS = [
    "bold",
    "italic",
    "underline",
    "strikeThrough",
    "insertUnorderedList",
    "insertOrderedList",
];

publicWidget.registry.EnvcareHtmlInput = publicWidget.Widget.extend({
    selector: ".o_envcare_html_input",
    events: {
        "mousedown .o_ehi_toolbar button": "_onToolbarMousedown",
        "click .o_ehi_toolbar button": "_onToolbarClick",
        "input .o_ehi_editable": "_onInput",
        "blur .o_ehi_editable": "_sync",
        "focus .o_ehi_editable": "_onFocus",
        "keyup .o_ehi_editable": "_updateToolbarState",
        "mouseup .o_ehi_editable": "_updateToolbarState",
        "paste .o_ehi_editable": "_onPaste",
    },

    start() {
        this.editable = this.el.querySelector(".o_ehi_editable");
        this.hidden = this.el.querySelector(".o_ehi_value");
        this.toolbar = this.el.querySelector(".o_ehi_toolbar");
        this.form = this.el.closest("form");

        this._onSubmit = this._onSubmit.bind(this);
        this._onSelectionChange = this._onSelectionChange.bind(this);
        if (this.form) {
            this.form.addEventListener("submit", this._onSubmit);
        }
        document.addEventListener("selectionchange", this._onSelectionChange);
        try {
            document.execCommand("defaultParagraphSeparator", false, "p");
        } catch {
            // not supported: browser default is fine
        }
        return this._super(...arguments);
    },

    destroy() {
        if (this.form) {
            this.form.removeEventListener("submit", this._onSubmit);
        }
        document.removeEventListener("selectionchange", this._onSelectionChange);
        this._super(...arguments);
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------
    _isEmpty() {
        return !this.editable.textContent.trim() && !this.editable.querySelector("img");
    },

    _sync() {
        this.hidden.value = this._isEmpty() ? "" : this.editable.innerHTML;
        if (!this._isEmpty()) {
            this.el.classList.remove("is-invalid");
        }
    },

    _selectionIsInside() {
        const selection = document.getSelection();
        return !!(selection && selection.rangeCount && this.editable.contains(selection.anchorNode));
    },

    _closestInEditor(tagNames) {
        const selection = document.getSelection();
        let node = selection && selection.anchorNode;
        while (node && node !== this.editable) {
            if (node.nodeType === 1 && tagNames.includes(node.nodeName)) {
                return node;
            }
            node = node.parentNode;
        }
        return null;
    },

    /**
     * Word-like "pressed" buttons for the formatting at the cursor.
     */
    _updateToolbarState() {
        if (!this.toolbar) {
            return;
        }
        const inside = this._selectionIsInside();
        const block = inside ? this._closestInEditor(["P", "H2", "H3", "BLOCKQUOTE"]) : null;
        const inLink = inside && !!this._closestInEditor(["A"]);

        for (const button of this.toolbar.querySelectorAll("button[data-cmd]")) {
            const cmd = button.dataset.cmd;
            let active = false;
            if (inside) {
                if (STATE_COMMANDS.includes(cmd)) {
                    try {
                        active = document.queryCommandState(cmd);
                    } catch {
                        active = false;
                    }
                } else if (cmd === "formatBlock") {
                    active = !!block && block.nodeName === button.dataset.value;
                } else if (cmd === "createLink") {
                    active = inLink;
                }
            }
            button.classList.toggle("active", active);
            if (cmd !== "unlink" && cmd !== "removeFormat") {
                button.setAttribute("aria-pressed", String(active));
            }
        }
    },

    /**
     * Keep the sticky toolbar below the website header when that header
     * is fixed / sticky at the top of the screen.
     */
    _updateStickyOffset() {
        let top = 0;
        const header = document.querySelector("header#top");
        if (header) {
            const position = getComputedStyle(header).position;
            const rect = header.getBoundingClientRect();
            if ((position === "fixed" || position === "sticky") && rect.bottom > 0) {
                top = Math.round(rect.bottom);
            }
        }
        this.el.style.setProperty("--o-ehi-sticky-top", `${top}px`);
    },

    // ------------------------------------------------------------------
    // Handlers
    // ------------------------------------------------------------------
    _onFocus() {
        this._updateStickyOffset();
        this._updateToolbarState();
    },

    _onInput() {
        this._sync();
        this._updateToolbarState();
    },

    _onSelectionChange() {
        if (this._selectionIsInside()) {
            this._updateToolbarState();
        }
    },

    _onToolbarMousedown(ev) {
        // keep the focus + text selection inside the editor
        ev.preventDefault();
    },

    _onToolbarClick(ev) {
        const button = ev.currentTarget;
        const cmd = button.dataset.cmd;
        let value = button.dataset.value || null;
        this.editable.focus();
        if (cmd === "createLink") {
            value = window.prompt("Link URL", "https://");
            if (!value || value === "https://") {
                return;
            }
        }
        if (cmd === "formatBlock" && value) {
            value = `<${value}>`;
        }
        document.execCommand(cmd, false, value);
        this._sync();
        this._updateToolbarState();
    },

    _onPaste(ev) {
        // paste as plain text so outside styles are not copied in
        ev.preventDefault();
        const text = (ev.clipboardData || window.clipboardData).getData("text/plain");
        document.execCommand("insertText", false, text);
        this._sync();
    },

    _onSubmit(ev) {
        this._sync();
        if (this.el.dataset.required && this._isEmpty()) {
            ev.preventDefault();
            ev.stopPropagation();
            this.el.classList.add("is-invalid");
            this.editable.focus();
        }
    },
});

export default publicWidget.registry.EnvcareHtmlInput;