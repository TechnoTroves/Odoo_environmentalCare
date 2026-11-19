/** @odoo-module **/
/**
 * Reusable "add / remove rows" helper for Environmental Care website forms.
 * Markup:
 *   <div class="o_envcare_rows">
 *       <button type="button" class="o_er_add">Add</button>
 *       <table><tbody>
 *           ...rows...
 *           <tr class="o_er_template d-none"> inputs with disabled="disabled" ...
 *               <button type="button" class="o_er_remove">x</button>
 *           </tr>
 *       </tbody></table>
 *   </div>
 * The template row's inputs are disabled so it is never submitted;
 * "Add" copies it, shows it and enables its inputs.
 * "__ROW__" in an input's name / id / for is replaced by a number unique to the
 * new row, so a row can have checkboxes, multi-selects and file inputs
 * (e.g. budget_new__ROW___amount -> budget_new1732012345678_amount).
 */
import publicWidget from "@web/legacy/js/public/public_widget";

let rowCounter = Date.now();

publicWidget.registry.EnvcareRowEditor = publicWidget.Widget.extend({
    selector: ".o_envcare_rows",
    events: {
        "click .o_er_add": "_onAdd",
        "click .o_er_remove": "_onRemove",
    },

    _onAdd() {
        const template = this.el.querySelector(".o_er_template");
        if (!template) {
            return;
        }
        const row = template.cloneNode(true);
        row.classList.remove("o_er_template", "d-none");
        for (const field of row.querySelectorAll("[disabled]")) {
            field.disabled = false;
        }
        const index = String(++rowCounter);
        for (const attr of ["name", "id", "for"]) {
            for (const el of row.querySelectorAll(`[${attr}*="__ROW__"]`)) {
                el.setAttribute(attr, el.getAttribute(attr).replaceAll("__ROW__", index));
            }
        }
        template.before(row);
        const first = row.querySelector("input, select, textarea");
        if (first) {
            first.focus();
        }
    },

    _onRemove(ev) {
        const row = ev.currentTarget.closest("tr");
        if (row && !row.classList.contains("o_er_template")) {
            row.remove();
        }
    },
});

export default publicWidget.registry.EnvcareRowEditor;