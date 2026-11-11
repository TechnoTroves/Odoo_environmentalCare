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
 */
import publicWidget from "@web/legacy/js/public/public_widget";

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