/** @odoo-module **/
/**
 * Reusable table search for Environmental Care website pages.
 * Markup comes from the QWeb template `environmental_care.table_search`.
 * Each searchable <td> carries data-ets-col="<key>" and, optionally,
 * data-ets-value="<raw value>" (used instead of the visible text).
 */
import publicWidget from "@web/legacy/js/public/public_widget";

const NUMBER_OPS = {
    eq: (a, b) => a === b,
    ne: (a, b) => a !== b,
    gt: (a, b) => a > b,
    lt: (a, b) => a < b,
};

publicWidget.registry.EnvcareTableSearch = publicWidget.Widget.extend({
    selector: ".o_envcare_table_search",
    events: {
        "change .o_ets_column": "_onColumnChange",
        "input .o_ets_text": "_applyFilter",
        "input .o_ets_number": "_applyFilter",
        "change .o_ets_num_op": "_applyFilter",
        "change .o_ets_sel_op": "_applyFilter",
        "change .o_ets_values": "_applyFilter",
        "click .o_ets_ignore_ws": "_onToggleIgnoreSpaces",
        "click .o_ets_clear": "_onClear",
    },

    start() {
        this.table = document.getElementById(this.el.dataset.table);
        this.ignoreSpaces = false;
        this._onColumnChange();
        return this._super(...arguments);
    },

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------
    _$(selector) {
        return this.el.querySelector(selector);
    },

    _currentColumn() {
        const option = this._$(".o_ets_column").selectedOptions[0];
        return { key: option.value, type: option.dataset.type || "text" };
    },

    _rows() {
        if (!this.table || !this.table.tBodies[0]) {
            return [];
        }
        // Only rows that have searchable cells (skips "no records" rows)
        return [...this.table.tBodies[0].rows].filter(
            (row) => row.querySelector("[data-ets-col]")
        );
    },

    _cellValue(row, key) {
        if (key === "__all__") {
            return [...row.querySelectorAll("[data-ets-col]")].map((c) => c.textContent).join(" ");
        }
        const cell = row.querySelector(`[data-ets-col="${key}"]`);
        if (!cell) {
            return "";
        }
        return cell.dataset.etsValue !== undefined ? cell.dataset.etsValue : cell.textContent;
    },

    _normalizeText(value) {
        value = (value || "").toLowerCase();
        return this.ignoreSpaces ? value.replace(/\s+/g, "") : value.replace(/\s+/g, " ").trim();
    },

    _visibleValuesSelect(key) {
        return this.el.querySelector(`.o_ets_values[data-col="${key}"]`);
    },

    // ------------------------------------------------------------------
    // Matching per mode
    // ------------------------------------------------------------------
    _buildMatcher() {
        const { key, type } = this._currentColumn();

        if (type === "number") {
            const raw = this._$(".o_ets_number").value;
            if (raw === "") {
                return null;
            }
            const target = parseFloat(raw);
            const op = NUMBER_OPS[this._$(".o_ets_num_op").value];
            return (row) => {
                const value = parseFloat(this._cellValue(row, key));
                return !Number.isNaN(value) && op(value, target);
            };
        }

        if (type === "select") {
            const select = this._visibleValuesSelect(key);
            const chosen = select ? select.value : "";
            if (chosen === "") {
                return null;
            }
            const equal = this._$(".o_ets_sel_op").value === "eq";
            return (row) => (this._cellValue(row, key).trim() === chosen) === equal;
        }

        // text
        const needle = this._normalizeText(this._$(".o_ets_text").value);
        if (!needle) {
            return null;
        }
        return (row) => this._normalizeText(this._cellValue(row, key)).includes(needle);
    },

    _applyFilter() {
        const rows = this._rows();
        const matcher = this._buildMatcher();
        let shown = 0;
        for (const row of rows) {
            const visible = !matcher || matcher(row);
            row.classList.toggle("d-none", !visible);
            shown += visible ? 1 : 0;
        }
        this._toggleNoResultRow(rows.length > 0 && shown === 0);
        this._$(".o_ets_count").textContent = matcher ? `${shown} of ${rows.length} shown` : "";
    },

    _toggleNoResultRow(show) {
        if (!this.table || !this.table.tBodies[0]) {
            return;
        }
        let row = this.table.tBodies[0].querySelector(".o_ets_no_result");
        if (show && !row) {
            row = this.table.tBodies[0].insertRow();
            row.className = "o_ets_no_result";
            const cell = row.insertCell();
            cell.colSpan = this.table.tHead ? this.table.tHead.rows[0].cells.length : 1;
            cell.className = "text-center text-muted";
            cell.textContent = "No matching records.";
        }
        if (row) {
            row.classList.toggle("d-none", !show);
        }
    },

    // ------------------------------------------------------------------
    // Handlers
    // ------------------------------------------------------------------
    _onColumnChange() {
        const { key, type } = this._currentColumn();
        for (const mode of this.el.querySelectorAll(".o_ets_mode")) {
            mode.classList.toggle("d-none", mode.dataset.mode !== type);
        }
        for (const select of this.el.querySelectorAll(".o_ets_values")) {
            select.classList.toggle("d-none", select.dataset.col !== key);
        }
        this._applyFilter();
    },

    _onToggleIgnoreSpaces(ev) {
        this.ignoreSpaces = !this.ignoreSpaces;
        const button = ev.currentTarget;
        button.setAttribute("aria-pressed", String(this.ignoreSpaces));
        button.classList.toggle("btn-secondary", this.ignoreSpaces);
        button.classList.toggle("btn-outline-secondary", !this.ignoreSpaces);
        this._applyFilter();
    },

    _onClear() {
        this._$(".o_ets_text").value = "";
        this._$(".o_ets_number").value = "";
        for (const select of this.el.querySelectorAll(".o_ets_values")) {
            select.value = "";
        }
        this._applyFilter();
    },
});

export default publicWidget.registry.EnvcareTableSearch;