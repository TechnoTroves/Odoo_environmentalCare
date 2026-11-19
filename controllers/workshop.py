"""Workshops on the website: list, detail (with chatter) and the Add / Edit form.
Every workshop field is shown; it is editable only for the people who may edit
the workshop (models/workshop.py: _envcare_can_edit), read-only for everyone else."""
from odoo import Command, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools import html2plaintext, html_sanitize, plaintext2html

from .common import EnvCareWebsiteMixin

# Rich-text fields (environmental_care.html_input), in form order
WORKSHOP_HTML_FIELDS = [
    "process", "design_requirements", "statistics_product_impact", "talkie", "statistics_workshop",
]
# Attachment fields (environmental_care.attachment_input); input name = field name
WORKSHOP_FILE_FIELDS = ["pitch_deck", "design_collaterals", "av_footage", "docs_files"]
# One2many tables (environmental_care.line_table) - column spec: see controllers/common.py
WORKSHOP_LINE_TABLES = {
    "budget": {
        "field": "budgets_ids", "label": "Budget", "add_label": "Add Expense",
        "columns": [
            {"name": "name", "label": "Expense Name", "type": "char", "required": True, "width": 170},
            {"name": "category_id", "label": "Category", "type": "m2o", "options": "budget_categories", "width": 150},
            {"name": "quantity", "label": "Qty", "type": "int", "width": 80},
            {"name": "amount", "label": "Amount", "type": "float", "width": 110},
            {"name": "bills", "label": "Bills", "type": "files", "width": 220},
            {"name": "remarks", "label": "Remarks", "type": "text", "width": 180},
        ],
    },
    "account": {
        "field": "accounts_ids", "label": "Accounts", "add_label": "Add Expense",
        "columns": [
            {"name": "name", "label": "Expense Name", "type": "char", "required": True, "width": 170},
            {"name": "category_id", "label": "Category", "type": "m2o", "options": "account_categories", "width": 150},
            {"name": "quantity", "label": "Qty", "type": "int", "width": 80},
            {"name": "amount", "label": "Amount", "type": "float", "width": 110},
            {"name": "bills", "label": "Bills", "type": "files", "width": 220},
            {"name": "sevaks_ids", "label": "Sevaks", "type": "m2m", "options": "workshop_sevaks", "width": 170},
            {"name": "paid_by", "label": "Paid By", "type": "m2o", "options": "users", "width": 160},
            {"name": "remarks", "label": "Remarks", "type": "text", "width": 180},
            {"name": "re_imbursement", "label": "Re-imbursed", "type": "bool"},
        ],
    },
    "docurl": {
        "field": "doc_id", "label": "Document URLs", "add_label": "Add URL",
        "columns": [
            {"name": "docs_urls", "label": "URL", "type": "url", "required": True, "width": 320},
        ],
    },
}


class EnvWorkshopWebsite(EnvCareWebsiteMixin, http.Controller):

    # =====================================================================
    # helpers
    # =====================================================================
    def _can_open_form(self, workshop):
        """Form page: everyone who can read the workshop. Only the people who
        may edit it (IT / Admin, the event's Events Head, Lead, Deputy) or switch
        Canceled get editable inputs and a Save button; the rest see it read-only."""
        return workshop.has_access("read")

    def _can_change(self, workshop):
        """Edit (pencil) button + Save: may edit, or may switch Canceled."""
        return workshop.can_edit or workshop.can_cancel

    # ---------- line tables ----------
    def _line_options(self, workshop=None):
        """Choices for the line tables' dropdowns: key -> [(id_str, label)]."""
        def _pairs(records):
            return [(str(r.id), r.display_name) for r in records]
        env = request.env
        sevaks = workshop.sevak_ids if workshop else self._sevak_options()
        return {
            "budget_categories": _pairs(env["envcare.workshop.budgets.categories"].search([], order="name")),
            "account_categories": _pairs(env["envcare.workshop.accounts.categories"].search([], order="name")),
            "workshop_sevaks": _pairs(sevaks.sorted("name")),
            "users": _pairs(self._sevak_options()),
        }

    def _line_tables(self, workshop=None, error=None):
        """Everything environmental_care.line_table needs, per table."""
        Workshop = request.env["envcare.workshop"]
        tables = {}
        for key, cfg in WORKSHOP_LINE_TABLES.items():
            model = Workshop._fields[cfg["field"]].comodel_name
            tables[key] = dict(
                cfg, key=key,
                rows=self._line_rows(workshop[cfg["field"]], cfg["columns"]) if workshop else [],
                new_rows=self._posted_new_line_rows(key, cfg["columns"]) if error else [],
                can_delete=request.env[model].has_access("unlink"),
            )
        return tables

    def _save_extra(self, workshop):
        """Attachments + line tables (need the saved workshop)."""
        self._save_attachments(workshop, WORKSHOP_FILE_FIELDS)
        options = self._line_options(workshop)
        allowed = {key: {int(i) for i, _label in pairs} for key, pairs in options.items()}
        for key, cfg in WORKSHOP_LINE_TABLES.items():
            model = workshop._fields[cfg["field"]].comodel_name
            self._save_line_table(
                workshop, key, cfg["field"], cfg["columns"], allowed, cfg["label"],
                can_delete=request.env[model].has_access("unlink"),
            )

    def _event_options(self):
        """Events a new workshop can go under: IT -> all, Events Head -> own events."""
        return request.env["envcare.event"].search([], order="date_begin desc").filtered("can_edit")

    def _product_options(self):
        return request.env["product.product"].search([], order="name", limit=2000)

    def _form_values(self, workshop):
        return {
            "name": workshop.name or "",
            "description": workshop.description or "",
            "event_id": str(workshop.event_id.id or ""),
            "lead": str(workshop.workshop_lead_id.id or ""),
            "deputy": str(workshop.workshop_deputy_id.id or ""),
            "date_start": self._to_input_datetime(workshop.date_start),
            "date_end": self._to_input_datetime(workshop.date_end),
            "sevak_ids": [str(uid) for uid in workshop.sevak_ids.ids],
            "is_canceled": workshop.is_canceled,
            **{fname: workshop[fname] or "" for fname in WORKSHOP_HTML_FIELDS},
        }

    def _posted_values(self, post):
        form = request.httprequest.form
        return dict(post, sevak_ids=form.getlist("sevak_ids"),
                    description=html_sanitize(post.get("description") or ""),
                    is_canceled=bool(post.get("is_canceled")),
                    **{fname: html_sanitize(post.get(fname) or "") for fname in WORKSHOP_HTML_FIELDS})

    def _new_item_rows(self):
        """New item rows as typed (to show them again after an error)."""
        form = request.httprequest.form
        rows = zip(form.getlist("item_new_product"), form.getlist("item_new_qty"), form.getlist("item_new_remarks"))
        return [{"product": p, "qty": q, "remarks": r} for p, q, r in rows]

    def _render_form(self, workshop=None, values=None, error=None):
        Workshop = request.env["envcare.workshop"]
        can_edit_fields = workshop.can_edit if workshop else Workshop.has_access("create")
        if values is None:
            if workshop:
                values = self._form_values(workshop)
            else:
                values = {"event_id": request.params.get("event_id") or "", "sevak_ids": []}
        events = request.env["envcare.event"]
        if can_edit_fields:
            events = self._event_options()
            if workshop:
                events |= workshop.event_id  # keep the current event selectable
        elif workshop:
            events = workshop.event_id
        return request.render("environmental_care.workshop_form_template", {
            "workshop": workshop,
            "values": values,
            "error": error,
            "form_action": f"/workshop/update/{workshop.id}" if workshop else "/workshop/create",
            "can_edit_fields": can_edit_fields,
            "can_cancel": bool(workshop and workshop.can_cancel),
            "can_save": can_edit_fields or bool(workshop and workshop.can_cancel),
            "line_tables": self._line_tables(workshop, error),
            "line_options": self._line_options(workshop),
            "events": events,
            "sevaks": self._sevak_options(),
            "products": self._product_options() if can_edit_fields else request.env["product.product"],
            "new_items": self._new_item_rows() if error else [],
            "can_delete_items": request.env["envcare.workshop.items"].has_access("unlink"),
            "remarks_text": lambda html: html2plaintext(html or "").strip(),
        })

    # ---------- reading the form ----------
    def _workshop_vals_from_post(self, post):
        name = (post.get("name") or "").strip()
        event_id = int(post["event_id"]) if (post.get("event_id") or "").isdigit() else False
        lead = int(post["lead"]) if (post.get("lead") or "").isdigit() else False
        deputy = int(post["deputy"]) if (post.get("deputy") or "").isdigit() else False
        missing = [label for value, label in (
            (name, "Workshop Name"), (event_id, "Event"), (lead, "Workshop Lead"), (deputy, "Workshop Deputy"),
        ) if not value]
        if missing:
            raise ValidationError("Please fill: %s" % ", ".join(missing))

        allowed_users = set(self._sevak_options().ids)
        sevaks = [int(u) for u in request.httprequest.form.getlist("sevak_ids")
                  if u.isdigit() and int(u) in allowed_users]
        event = request.env["envcare.event"].browse(event_id).exists()
        if not event:
            raise ValidationError("Please choose an event.")
        return {
            "name": name,
            "description": html_sanitize(post.get("description") or ""),
            "event_id": event.id,
            "workshop_lead_id": lead,
            "workshop_deputy_id": deputy,
            # Empty dates -> the event's dates (same as the backend)
            "date_start": self._from_input_datetime(post.get("date_start")) or event.date_begin,
            "date_end": self._from_input_datetime(post.get("date_end")) or event.date_end,
            # Lead and Deputy are added to the Sevaks automatically by the model
            "sevak_ids": [Command.set(sevaks)],
            **{fname: html_sanitize(post.get(fname) or "") for fname in WORKSHOP_HTML_FIELDS},
        }

    def _item_commands(self, workshop=None):
        """Workshop Item List rows -> One2many commands."""
        form = request.httprequest.form
        commands = []
        can_delete = request.env["envcare.workshop.items"].has_access("unlink")

        def _qty(value):
            try:
                qty = int(value)
            except (TypeError, ValueError):
                raise ValidationError("Item quantities must be whole numbers.")
            if qty <= 0:
                raise ValidationError("Item quantities must be more than 0.")
            return qty

        for item in (workshop.items_ids if workshop else []):
            prefix = f"item_{item.id}_"
            if f"{prefix}product" not in form:
                continue
            if can_delete and form.get(f"{prefix}delete"):
                commands.append(Command.delete(item.id))
                continue
            product = form.get(f"{prefix}product")
            if not (product or "").isdigit():
                raise ValidationError("Every item needs a product.")
            vals = {
                "product_id": int(product),
                "qty": _qty(form.get(f"{prefix}qty")),
                "remarks": plaintext2html(form.get(f"{prefix}remarks") or ""),
            }
            if (item.product_id.id, item.qty, html2plaintext(item.remarks or "").strip()) != (
                    vals["product_id"], vals["qty"], (form.get(f"{prefix}remarks") or "").strip()):
                commands.append(Command.update(item.id, vals))

        for row in self._new_item_rows():
            if not row["product"] and not (row["remarks"] or "").strip():
                continue  # empty row
            if not (row["product"] or "").isdigit():
                raise ValidationError("Every item needs a product.")
            commands.append(Command.create({
                "product_id": int(row["product"]),
                "qty": _qty(row["qty"] or 1),
                "remarks": plaintext2html(row["remarks"] or ""),
            }))
        return commands

    # =====================================================================
    # 1. List
    # =====================================================================
    @http.route("/workshops", type="http", auth="user", website=True)
    def workshop_list(self, **kw):
        Workshop = request.env["envcare.workshop"]
        if not Workshop.has_access("read"):
            return request.redirect("/my")
        workshops = Workshop.search([], order="date_start desc, id desc")
        events = workshops.event_id
        search_columns = [
            {"key": "name", "label": "Workshop Name", "type": "text"},
            {"key": "event", "label": "Event", "type": "select",
             "options": [(str(e.id), e.name) for e in events.sorted("name")]},
            {"key": "lead", "label": "Lead", "type": "text"},
            {"key": "deputy", "label": "Deputy", "type": "text"},
            {"key": "date_start", "label": "Start", "type": "text"},
            {"key": "date_end", "label": "End", "type": "text"},
            {"key": "canceled", "label": "Canceled", "type": "select",
             "options": [("yes", "Yes"), ("no", "No")]},
        ]
        return request.render("environmental_care.workshop_list_template", {
            "workshops": workshops,
            "can_create": Workshop.has_access("create"),
            "search_columns": search_columns,
        })

    # =====================================================================
    # 2. Detail (+ chatter)
    # =====================================================================
    @http.route('/workshop/<model("envcare.workshop"):workshop>', type="http", auth="user", website=True)
    def workshop_detail(self, workshop, **kw):
        values = {
            "workshop": workshop,
            "can_edit": self._can_change(workshop),
            "line_tables": self._line_tables(workshop),
        }
        values.update(self._chatter_values(workshop))
        return request.render("environmental_care.workshop_detail_template", values)

    # =====================================================================
    # 3. Add
    # =====================================================================
    @http.route("/workshop/new", type="http", auth="user", website=True)
    def workshop_new(self, **kw):
        if not request.env["envcare.workshop"].has_access("create"):
            return request.redirect("/workshops")
        return self._render_form()

    @http.route("/workshop/create", type="http", auth="user", website=True, methods=["POST"])
    def workshop_create(self, **post):
        Workshop = request.env["envcare.workshop"]
        if not Workshop.has_access("create"):
            return request.redirect("/workshops")
        try:
            with request.env.cr.savepoint():
                vals = self._workshop_vals_from_post(post)
                vals["items_ids"] = self._item_commands()
                workshop = Workshop.create(vals)  # new workshops are never canceled
                self._save_extra(workshop)
        except (ValidationError, UserError, AccessError) as e:
            request.env.invalidate_all()
            return self._render_form(values=self._posted_values(post), error=str(e))
        return request.redirect(f"/workshop/{workshop.id}")

    # =====================================================================
    # 4. Edit
    # =====================================================================
    @http.route('/workshop/edit/<model("envcare.workshop"):workshop>', type="http", auth="user", website=True)
    def workshop_edit(self, workshop, **kw):
        if not self._can_open_form(workshop):
            return request.redirect(f"/workshop/{workshop.id}")
        return self._render_form(workshop)

    @http.route('/workshop/update/<model("envcare.workshop"):workshop>', type="http", auth="user",
                website=True, methods=["POST"])
    def workshop_update(self, workshop, **post):
        if not self._can_change(workshop):
            return request.redirect(f"/workshop/{workshop.id}")
        try:
            # All or nothing. Un-cancel first (a canceled workshop can't be edited),
            # then the content, then cancel. Rights are checked again in write().
            with request.env.cr.savepoint():
                can_edit = workshop.can_edit
                canceled = bool(post.get("is_canceled"))
                cancel_changed = workshop.can_cancel and "is_canceled_shown" in post \
                    and canceled != workshop.is_canceled
                if cancel_changed and not canceled:
                    workshop.write({"is_canceled": False})
                    can_edit = workshop._envcare_can_edit()
                if can_edit and "name" in post:  # fields are disabled (not posted) when read-only
                    vals = self._workshop_vals_from_post(post)
                    vals["items_ids"] = self._item_commands(workshop)
                    workshop.write(vals)
                    self._save_extra(workshop)
                if cancel_changed and canceled:
                    workshop.write({"is_canceled": True})
        except (ValidationError, UserError, AccessError) as e:
            request.env.invalidate_all()
            values = self._posted_values(post) if "name" in post else self._form_values(workshop)
            return self._render_form(workshop, values=values, error=str(e))
        return request.redirect(f"/workshop/{workshop.id}")