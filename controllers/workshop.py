"""Workshops on the website: list, detail (with chatter) and the Add / Edit form.
This covers the first part of the workshop: details + Workshop Item List."""
from odoo import Command, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools import html2plaintext, html_sanitize, plaintext2html

from .common import EnvCareWebsiteMixin


class EnvWorkshopWebsite(EnvCareWebsiteMixin, http.Controller):

    # =====================================================================
    # helpers
    # =====================================================================
    def _state_labels(self):
        return dict(request.env["envcare.workshop"]._fields["state"]._description_selection(request.env))

    def _can_open_form(self, workshop):
        """Edit page: users who may edit the workshop, or who may change its
        status (e.g. the Workshop Lead or HR approving it)."""
        return workshop.has_access("write") or len(workshop._get_website_state_options()) > 1

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
            "state": workshop.state,
        }

    def _posted_values(self, post):
        form = request.httprequest.form
        return dict(post, sevak_ids=form.getlist("sevak_ids"),
                    description=html_sanitize(post.get("description") or ""))

    def _new_item_rows(self):
        """New item rows as typed (to show them again after an error)."""
        form = request.httprequest.form
        rows = zip(form.getlist("item_new_product"), form.getlist("item_new_qty"), form.getlist("item_new_remarks"))
        return [{"product": p, "qty": q, "remarks": r} for p, q, r in rows]

    def _render_form(self, workshop=None, values=None, error=None):
        Workshop = request.env["envcare.workshop"]
        can_edit_fields = workshop.has_access("write") if workshop else Workshop.has_access("create")
        if values is None:
            if workshop:
                values = self._form_values(workshop)
            else:
                values = {"state": "draft", "event_id": request.params.get("event_id") or "", "sevak_ids": []}
        if workshop:
            status = workshop._envcare_status_info()
        else:
            status = {"options": [("draft", self._state_labels().get("draft", "Draft"))],
                      "missing": [], "waiting_for": "", "next_label": ""}
        return request.render("environmental_care.workshop_form_template", {
            "workshop": workshop,
            "values": values,
            "error": error,
            "form_action": f"/workshop/update/{workshop.id}" if workshop else "/workshop/create",
            "can_edit_fields": can_edit_fields,
            "status": status,
            "events": request.env["envcare.event"].search([], order="date_begin desc"),
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
            {"key": "state", "label": "Status", "type": "select",
             "options": list(self._state_labels().items())},
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
            "can_edit": self._can_open_form(workshop),
            "status": workshop._envcare_status_info(),
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
                workshop = Workshop.create(vals)  # new workshops always start as Draft
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
        if not self._can_open_form(workshop):
            return request.redirect(f"/workshop/{workshop.id}")
        try:
            # All or nothing: content first, then the status (needs the saved content)
            with request.env.cr.savepoint():
                if workshop.has_access("write"):
                    vals = self._workshop_vals_from_post(post)
                    vals["items_ids"] = self._item_commands(workshop)
                    workshop.write(vals)
                requested = post.get("state")
                if requested and requested != workshop.state:
                    workshop._apply_website_state(requested)  # role check inside
        except (ValidationError, UserError, AccessError) as e:
            request.env.invalidate_all()
            values = self._posted_values(post) if workshop.has_access("write") else self._form_values(workshop)
            return self._render_form(workshop, values=values, error=str(e))
        return request.redirect(f"/workshop/{workshop.id}")