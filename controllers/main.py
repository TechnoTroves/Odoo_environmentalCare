import base64

from odoo import Command, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .common import EnvCareWebsiteMixin

from odoo.tools import html2plaintext, html_sanitize

# Where non-IT / non-admin users land instead of the backend:
# their own profile page (every logged-in user can open it)
WEBSITE_HOME = "/my"

# Only these groups may open the backend (/odoo, /web)
BACKEND_GROUPS = (
    "base.group_system",                     # Settings / Administration (Admin)
    "environmental_care.group_envcare_it",   # IT Sevak / IT Head
)


def _backend_allowed(user):
    return user._is_superuser() or any(user.has_group(group) for group in BACKEND_GROUPS)


def _is_backend_url(url):
    path = (url or "").split("?")[0].split("#")[0]
    return path in ("/web", "/odoo") or path.startswith(("/web/", "/odoo/", "/scoped_app"))


# ---------------------------------------------------------------------------
# 1 & 2. Keep everyone except IT / Admin out of the backend
# ---------------------------------------------------------------------------
class EnvCareHome(Home):

    @http.route()
    def web_client(self, s_action=None, **kw):
        # /odoo is an auth="none" route: request.env.user is not set yet,
        # so read the logged-in user from the session.
        ensure_db()
        uid = request.session.uid
        if uid:
            user = request.env["res.users"].sudo().browse(uid).exists()
            if user and user._is_internal() and not _backend_allowed(user):
                return request.redirect(WEBSITE_HOME)
        return super().web_client(s_action, **kw)

    def _login_redirect(self, uid, redirect=None):
        url = super()._login_redirect(uid, redirect=redirect)
        user = request.env["res.users"].sudo().browse(uid)
        if user._is_internal() and not _backend_allowed(user) and (not url or _is_backend_url(url)):
            return WEBSITE_HOME
        return url


# ---------------------------------------------------------------------------
# Events website
# ---------------------------------------------------------------------------
class EnvEventWebsite(EnvCareWebsiteMixin, http.Controller):
    # No sudo(): access rights and record rules decide what the user sees / does.

    # ---------- helpers ----------
    def _event_form_values(self, event):
        return {
            "name": event.name or "",
            "description": event.description or "",
            "date_begin": self._to_input_datetime(event.date_begin),
            "date_end": self._to_input_datetime(event.date_end),
            "deadline": event.deadline.isoformat() if event.deadline else "",
            "location": event.location or "",
            "status": event.status or "draft",
        }

    def _event_vals_from_post(self, post):
        vals = {
            "name": (post.get("name") or "").strip(),
            "description": html_sanitize(post.get("description") or ""),
            "date_begin": self._from_input_datetime(post.get("date_begin")),
            "date_end": self._from_input_datetime(post.get("date_end")),
            "deadline": post.get("deadline") or False,
            "location": (post.get("location") or "").strip(),
        }
        status = post.get("status")
        if status in dict(self._status_options()):
            vals["status"] = status
        missing = [label for key, label in (
            ("name", "Event Name"), ("date_begin", "Start"), ("date_end", "End"),
            ("deadline", "Deadline"), ("location", "Location"),
        ) if not vals[key]]
        if not html2plaintext(vals["description"]).strip():
            missing.insert(1, "Description")
        if missing:
            raise ValidationError("Please fill: %s" % ", ".join(missing))
        if vals["date_end"] <= vals["date_begin"]:
            raise ValidationError("The event must end after it starts.")
        return vals

    def _render_event_form(self, event=None, values=None, error=None):
        if values is not None and "description" in values:
            # Re-showing what the user typed: clean the HTML first
            values = dict(values, description=html_sanitize(values.get("description") or ""))
        return request.render("environmental_care.event_form_template", {
            "event": event,
            "values": values if values is not None else (self._event_form_values(event) if event else {}),
            "error": error,
            "form_action": f"/event/update/{event.id}" if event else "/event/create",
            "status_options": self._status_options(),
            # Workshops table
            "sevaks": self._sevak_options(),
            "new_workshops": self._new_workshop_rows() if error else [],
            "can_delete_workshops": request.env["envcare.workshop"].has_access("unlink"),
            "to_input_dt": self._to_input_datetime,
        })

    # ---------- documents / workshops helpers ----------
    def _status_options(self):
        return request.env["envcare.event"]._fields["status"]._description_selection(request.env)

    def _new_workshop_rows(self):
        """New workshop rows as typed in the form (to show them again after an error)."""
        form = request.httprequest.form
        rows = zip(
            form.getlist("ws_new_name"), form.getlist("ws_new_lead"), form.getlist("ws_new_deputy"),
            form.getlist("ws_new_start"), form.getlist("ws_new_end"),
        )
        return [
            {"name": n, "lead": l, "deputy": d, "start": st, "end": en}
            for n, l, d, st, en in rows
        ]

    def _workshop_vals(self, event, name, lead, deputy, start, end):
        name = (name or "").strip()
        if not name:
            raise ValidationError("Every workshop needs a name.")
        if not lead or not deputy:
            raise ValidationError(f"Workshop '{name}' needs a Lead and a Deputy.")
        vals = {
            "name": name,
            "workshop_lead_id": int(lead),
            "workshop_deputy_id": int(deputy),
            # Empty dates -> use the event's dates (same as in the backend)
            "date_start": self._from_input_datetime(start) or event.date_begin,
            "date_end": self._from_input_datetime(end) or event.date_end,
        }
        return vals

    def _save_documents(self, event):
        files = [f for f in request.httprequest.files.getlist("documents") if f and f.filename]
        remove_ids = {int(x) for x in request.httprequest.form.getlist("doc_remove") if x.isdigit()}
        commands = [Command.unlink(doc.id) for doc in event.document_ids if doc.id in remove_ids]
        for upload in files:
            attachment = request.env["ir.attachment"].create({
                "name": upload.filename,
                "datas": base64.b64encode(upload.read()),
                "res_model": "envcare.event",
                "res_id": event.id,
            })
            commands.append(Command.link(attachment.id))
        if commands:
            event.write({"document_ids": commands})

    def _save_workshops(self, event):
        form = request.httprequest.form
        Workshop = request.env["envcare.workshop"]
        can_delete = Workshop.has_access("unlink")
        # Existing workshops: update, cancel / un-cancel or delete.
        # Rows the user can't edit are disabled in the form (not posted);
        # write() checks the rights again on the server.
        for ws in event.workshop_ids:
            prefix = f"ws_{ws.id}_"
            if can_delete and form.get(f"{prefix}delete"):
                ws.unlink()
                continue
            canceled = bool(form.get(f"{prefix}canceled"))
            cancel_changed = ws.can_cancel and f"{prefix}canceled_shown" in form and canceled != ws.is_canceled
            if cancel_changed and not canceled:
                ws.write({"is_canceled": False})  # un-cancel first, then it can be edited
            if f"{prefix}name" in form and ws._envcare_can_edit():
                vals = self._workshop_vals(
                    event, form.get(f"{prefix}name"), form.get(f"{prefix}lead"), form.get(f"{prefix}deputy"),
                    form.get(f"{prefix}start"), form.get(f"{prefix}end"),
                )
                changed = {
                    key: value for key, value in vals.items()
                    if (ws[key].id if key.endswith("_id") else ws[key]) != value
                }
                if changed:
                    ws.write(changed)
            if cancel_changed and canceled:
                ws.write({"is_canceled": True})
        # New workshops
        for row in self._new_workshop_rows():
            if not (row["name"] or "").strip() and not row["lead"] and not row["deputy"]:
                continue  # completely empty row
            Workshop.create(dict(
                self._workshop_vals(event, row["name"], row["lead"], row["deputy"], row["start"], row["end"]),
                event_id=event.id,
            ))

    # ---------- 1. List ----------
    @http.route("/events", type="http", auth="user", website=True)
    def event_list(self, **kw):
        Event = request.env["envcare.event"]
        if not Event.has_access("read"):
            return request.redirect(WEBSITE_HOME)
        events = Event.search([], order="date_begin desc")
        status_options = Event._fields["status"]._description_selection(request.env)
        # Columns offered by the search component (see table_search template)
        search_columns = [
            {"key": "name", "label": "Event Name", "type": "text"},
            {"key": "location", "label": "Location", "type": "text"},
            {"key": "date_begin", "label": "Start Date", "type": "text"},
            {"key": "date_end", "label": "End Date", "type": "text"},
            {"key": "deadline", "label": "Deadline", "type": "text"},
            {"key": "status", "label": "Status", "type": "select", "options": status_options},
        ]
        return request.render("environmental_care.event_list_template", {
            "events": events,
            "can_create": Event.has_access("create"),
            "search_columns": search_columns,
        })

    # ---------- 2. Detail ----------
    @http.route('/event/<model("envcare.event"):event>', type="http", auth="user", website=True)
    def event_detail(self, event, **kw):
        values = {
            "event": event,
            "can_edit": event.can_edit,
        }
        values.update(self._chatter_values(event))
        return request.render("environmental_care.event_detail_template", values)

    # ---------- 3. Create ----------
    @http.route("/event/new", type="http", auth="user", website=True)
    def event_new_form(self, **kw):
        if not request.env["envcare.event"].has_access("create"):
            return request.redirect("/events")
        return self._render_event_form()

    @http.route("/event/create", type="http", auth="user", website=True, methods=["POST"])
    def event_create(self, **post):
        Event = request.env["envcare.event"]
        if not Event.has_access("create"):
            return request.redirect("/events")
        try:
            # All or nothing: if a workshop or file fails, the event is not created either
            with request.env.cr.savepoint():
                event = Event.create(self._event_vals_from_post(post))
                self._save_documents(event)
                self._save_workshops(event)
        except (ValidationError, UserError, AccessError) as e:
            return self._render_event_form(values=post, error=str(e))
        return request.redirect(f"/event/{event.id}")

    # ---------- 4. Edit ----------
    @http.route('/event/edit/<model("envcare.event"):event>', type="http", auth="user", website=True)
    def event_edit_form(self, event, **kw):
        if not event.can_edit:
            return request.redirect(f"/event/{event.id}")
        return self._render_event_form(event)

    @http.route('/event/update/<model("envcare.event"):event>', type="http", auth="user", website=True, methods=["POST"])
    def event_update_form(self, event, **post):
        if not event.can_edit:
            return request.redirect(f"/event/{event.id}")
        try:
            # write() without sudo -> record rules re-checked on the server.
            # All or nothing: an error rolls back the event, files and workshops.
            with request.env.cr.savepoint():
                event.write(self._event_vals_from_post(post))
                self._save_documents(event)
                self._save_workshops(event)
        except (ValidationError, UserError, AccessError) as e:
            request.env.invalidate_all()  # drop values that were rolled back
            return self._render_event_form(event, values=post, error=str(e))
        return request.redirect(f"/event/{event.id}")


# ---------------------------------------------------------------------------
# My Profile: /my (view only) and /my/account (edit)
# Replaces Odoo's portal "My Account" pages.
# ---------------------------------------------------------------------------
class EnvCarePortal(CustomerPortal):

    def _profile_values(self, editable, error=None, values=None):
        user = request.env.user
        user_sudo = user.sudo()
        current = {
            "name": user.name or "",
            "email": user.login or user.email or "",
            "phone": user_sudo.envcare_contact or "",
        }
        return {
            # NOTE: not called "editable" - the website sets its own
            # "editable" (page editor) and would overwrite it
            "profile_edit": editable,
            "profile_user": user,
            # cache-busting so a new photo shows straight away
            "avatar_url": f"/web/image/res.users/{user.id}/avatar_256?unique={int(user.write_date.timestamp()) if user.write_date else 0}",
            "values": dict(current, **(values or {})),
            # Address is kept by HR (Sevak Master Record): read only here
            "address": user_sudo.envcare_address or "",
            "error": error,
            "saved": bool(request.params.get("saved")),
        }

    @http.route()
    def home(self, **kw):
        """/my - view only profile of the logged-in user."""
        return request.render("environmental_care.my_profile", self._profile_values(editable=False))

    @http.route()
    def account(self, redirect=None, **post):
        """/my/account - edit name, phone and photo (email and address are
        shown read only; HR changes them). Cancel / Save."""
        if request.httprequest.method != "POST":
            return request.render("environmental_care.my_profile", self._profile_values(editable=True))

        user = request.env.user
        name = (post.get("name") or "").strip()
        phone = (post.get("phone") or "").strip()
        typed = {"name": name, "phone": phone}

        if not name:
            return request.render("environmental_care.my_profile",
                                  self._profile_values(True, "Please enter your name.", typed))

        # Email (= login) and Address are kept by HR: never taken from this form
        partner_vals = {"name": name}
        photo = request.httprequest.files.get("image")
        if photo and photo.filename:
            if not (photo.mimetype or "").startswith("image/"):
                return request.render("environmental_care.my_profile",
                                      self._profile_values(True, "The photo must be an image file.", typed))
            partner_vals["image_1920"] = base64.b64encode(photo.read())

        try:
            with request.env.cr.savepoint():
                # Only these fields, on the user's OWN record (sudo after the checks above)
                user.partner_id.sudo().write(partner_vals)
                user.sudo().write({"envcare_contact": phone})
        except (UserError, ValidationError) as e:
            return request.render("environmental_care.my_profile", self._profile_values(True, str(e), typed))
        return request.redirect("/my?saved=1")