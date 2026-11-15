import base64
import uuid
from datetime import datetime, timedelta

import pytz

from odoo import Command, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from markupsafe import Markup

from odoo.tools import format_datetime, html2plaintext, html_sanitize, is_html_empty

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
class EnvEventWebsite(http.Controller):
    # No sudo(): access rights and record rules decide what the user sees / does.

    # ---------- helpers ----------
    def _user_tz(self):
        return pytz.timezone(request.env.user.tz or "UTC")

    def _to_input_datetime(self, value):
        """UTC datetime from the DB -> 'YYYY-MM-DDTHH:MM' in the user's timezone."""
        if not value:
            return ""
        return pytz.utc.localize(value).astimezone(self._user_tz()).strftime("%Y-%m-%dT%H:%M")

    def _from_input_datetime(self, value):
        """'YYYY-MM-DDTHH:MM' in the user's timezone -> naive UTC for the DB."""
        if not value:
            return False
        local = self._user_tz().localize(datetime.strptime(value, "%Y-%m-%dT%H:%M"))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

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
            "ws_state_options": self._ws_state_options(),
            "ws_status": self._workshop_status_info(event),
            "sevaks": self._sevak_options(),
            "new_workshops": self._new_workshop_rows() if error else [],
            "can_delete_workshops": request.env["envcare.workshop"].has_access("unlink"),
            "to_input_dt": self._to_input_datetime,
        })

    # ---------- documents / workshops helpers ----------
    def _status_options(self):
        return request.env["envcare.event"]._fields["status"]._description_selection(request.env)

    def _ws_state_options(self):
        return request.env["envcare.workshop"]._fields["state"]._description_selection(request.env)

    def _workshop_status_info(self, event):
        """Per workshop: which statuses the dropdown offers + what is still
        missing before it can be sent for approval."""
        if not event:
            return {}
        labels = dict(self._ws_state_options())
        info = {}
        for ws in event.workshop_ids:
            options = ws._get_website_state_options()
            next_state = ws._get_next_state()
            # Hint only when the next step exists but is locked by missing content
            missing = ws._get_missing_fields_for(next_state) if next_state and next_state not in options else []
            info[ws.id] = {
                "options": [(state, labels.get(state, state)) for state in options],
                "missing": missing,
                "next_label": labels.get(next_state, ""),
            }
        return info

    def _sevak_options(self):
        """Environmental Care users, for the Workshop Lead / Deputy dropdowns."""
        group = request.env.ref("environmental_care.group_envcare_user")
        return request.env["res.users"].sudo().search(
            [("share", "=", False), ("groups_id", "in", group.ids)], order="name"
        )

    def _new_workshop_rows(self):
        """New workshop rows as typed in the form (to show them again after an error)."""
        form = request.httprequest.form
        rows = zip(
            form.getlist("ws_new_name"), form.getlist("ws_new_lead"), form.getlist("ws_new_deputy"),
            form.getlist("ws_new_start"), form.getlist("ws_new_end"), form.getlist("ws_new_state"),
        )
        return [
            {"name": n, "lead": l, "deputy": d, "start": st, "end": en}
            for n, l, d, st, en, _sta in rows
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
        # Existing workshops: update or delete
        for ws in event.workshop_ids:
            prefix = f"ws_{ws.id}_"
            if f"{prefix}name" not in form:
                continue
            if can_delete and form.get(f"{prefix}delete"):
                ws.unlink()
                continue
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
            # Status: only after the content is saved, and only to a status
            # the workshop is ready for (same list as the dropdown)
            requested = form.get(f"{prefix}state")
            if requested and requested != ws.state:
                if requested not in ws._get_website_state_options():
                    labels = dict(self._ws_state_options())
                    missing = ws._get_missing_fields_for(requested)
                    raise ValidationError(
                        f"Workshop '{ws.name}' cannot move to '{labels.get(requested, requested)}' yet."
                        + (f" Please fill: {', '.join(missing)}." if missing else "")
                    )
                ws._apply_website_state(requested)
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

    # =====================================================================
    # Chatter (messages, log notes, activities) on the event detail page
    # =====================================================================
    ACTIVITY_TYPES = [
        ("mail.mail_activity_data_email", "Email"),
        ("mail.mail_activity_data_call", "Call"),
        ("mail.mail_activity_data_meeting", "Meeting"),
        ("mail.mail_activity_data_todo", "To Do"),
    ]

    def _can_send_message(self, event):
        """Send Message (e-mail): Events Head who created the event, IT, Admin.
        (can_edit = IT, or Event Head + creator)"""
        return event.can_edit or request.env.user.has_group("base.group_system")

    def _format_dt(self, value):
        return format_datetime(request.env, value, tz=request.env.user.tz, dt_format="medium") if value else ""

    def _chatter_values(self, event):
        user = request.env.user
        # ---- messages (newest first) ----
        messages = []
        for msg in event.message_ids.filtered(lambda m: m.message_type in ("comment", "notification")):
            tracking = []
            for change in msg.sudo().tracking_value_ids._tracking_value_format():
                tracking.append((
                    change["changedField"],
                    change["oldValue"]["value"] or "",
                    change["newValue"]["value"] or "",
                ))
            if is_html_empty(msg.body) and not tracking and not msg.attachment_ids:
                continue
            is_note = msg.subtype_id.internal or msg.message_type == "notification"
            messages.append({
                "author": msg.author_id.name or msg.email_from or "System",
                "avatar": f"/web/image/res.partner/{msg.author_id.id}/avatar_128" if msg.author_id else "",
                "date": self._format_dt(msg.date),
                "kind": "note" if is_note else "message",
                "body": msg.body,
                "tracking": tracking,
                "attachments": [(a.id, a.name) for a in msg.attachment_ids],
            })
        # ---- planned activities ----
        today = datetime.now(pytz.timezone(user.tz or "UTC")).date()
        activities = []
        for act in event.activity_ids.sorted(lambda a: (a.date_deadline, a.envcare_remind_at or datetime.min)):
            state = "overdue" if act.date_deadline < today else "today" if act.date_deadline == today else "planned"
            activities.append({
                "id": act.id,
                "type": act.activity_type_id.name,
                "icon": act.activity_type_id.icon or "fa-tasks",
                "summary": act.summary,
                "note": act.note if not is_html_empty(act.note) else False,
                "deadline": act.date_deadline,
                "remind_at": self._format_dt(act.envcare_remind_at),
                "assignee": act.user_id.name,
                "creator": act.create_uid.name,
                "state": state,
                "can_done": user in (act.user_id | act.create_uid) or event.can_edit,
            })
        default_remind = datetime.now(pytz.timezone(user.tz or "UTC")) + timedelta(hours=1)
        return {
            "chatter_messages": messages,
            "chatter_activities": activities,
            "can_send_message": self._can_send_message(event),
            "event_owner": event.sudo().create_uid.name,
            "activity_types": self.ACTIVITY_TYPES,
            "sevaks": self._sevak_options(),
            "default_remind_at": default_remind.strftime("%Y-%m-%dT%H:%M"),
            "chatter_error": request.params.get("chatter_error"),
        }

    def _back_to_chatter(self, event, error=None):
        url = f"/event/{event.id}"
        if error:
            from werkzeug.urls import url_encode
            url += "?" + url_encode({"chatter_error": error})
        return request.redirect(url + "#envcare_chatter")

    @http.route('/event/<model("envcare.event"):event>/chatter/post', type="http", auth="user",
                website=True, methods=["POST"])
    def event_chatter_post(self, event, **post):
        """Log note (everyone who can see the event) or Send message
        (Events Head creator / IT / Admin only). Both e-mail the event
        creator, the sender and the people picked in "Send to"."""
        mode = post.get("mode") or "note"
        if mode == "message" and not self._can_send_message(event):
            return self._back_to_chatter(event, "You are not allowed to send messages on this event.")
        body = html_sanitize(post.get("body") or "")
        files = [f for f in request.httprequest.files.getlist("attachments") if f and f.filename]
        if is_html_empty(body) and not files:
            return self._back_to_chatter(event, "Please write something before posting.")
        # Who is e-mailed (Send message AND Log note):
        #   1. the event creator, 2. the sender, 3. everyone picked in "Send to".
        # Followers are NOT notified, and nobody has to follow the event.
        picked = {int(u) for u in request.httprequest.form.getlist("recipient_ids") if u.isdigit()}
        partners = self._sevak_options().filtered(lambda u: u.id in picked).partner_id
        partners |= event.sudo().create_uid.partner_id
        partners |= request.env.user.partner_id
        partner_ids = partners.ids
        try:
            # mail_create_nosubscribe: posting does not make anyone a follower
            event.with_context(
                mail_create_nosubscribe=True,
                envcare_notify_partner_ids=partner_ids,
            ).message_post(
                body=Markup(body),
                message_type="comment",
                subtype_xmlid="mail.mt_comment" if mode == "message" else "mail.mt_note",
                partner_ids=partner_ids,
                attachments=[(f.filename, f.read()) for f in files],
                notify_author=True,   # the sender gets a copy too
            )
        except (AccessError, UserError, ValidationError) as e:
            return self._back_to_chatter(event, str(e))
        return self._back_to_chatter(event)

    @http.route('/event/<model("envcare.event"):event>/activity/schedule', type="http", auth="user",
                website=True, methods=["POST"])
    def event_activity_schedule(self, event, **post):
        """Schedule an Email / Call / Meeting / To Do for one or more EC users.
        One activity per selected user. Nothing is sent now: only the
        selected users get a reminder e-mail at the scheduled time."""
        type_xmlid = post.get("activity_type")
        if type_xmlid not in dict(self.ACTIVITY_TYPES):
            return self._back_to_chatter(event, "Please choose an activity type.")
        remind_at = self._from_input_datetime(post.get("remind_at"))
        if not remind_at:
            return self._back_to_chatter(event, "Please choose the date and time of the activity.")
        allowed_ids = set(self._sevak_options().ids)
        user_ids = [int(u) for u in request.httprequest.form.getlist("user_ids") if u.isdigit() and int(u) in allowed_ids]
        if not user_ids:
            user_ids = [request.env.user.id]
        local_day = pytz.utc.localize(remind_at).astimezone(self._user_tz()).date()
        group_key = uuid.uuid4().hex
        try:
            with request.env.cr.savepoint():
                # mail_activity_quick_update: no "assigned to you" e-mail now -
                # the selected users are only notified at the scheduled time
                scheduler = event.with_context(mail_activity_quick_update=True)
                for user_id in user_ids:
                    scheduler.activity_schedule(
                        type_xmlid,
                        date_deadline=local_day,
                        summary=(post.get("summary") or "").strip(),
                        note=html_sanitize(post.get("note") or "") or "",
                        user_id=user_id,
                        envcare_remind_at=remind_at,
                        envcare_group_key=group_key,
                    )
        except (AccessError, UserError, ValidationError) as e:
            return self._back_to_chatter(event, str(e))
        return self._back_to_chatter(event)

    @http.route('/event/activity/<int:activity_id>/done', type="http", auth="user",
                website=True, methods=["POST"])
    def event_activity_done(self, activity_id, **post):
        activity = request.env["mail.activity"].browse(activity_id).exists()
        if not activity or activity.res_model != "envcare.event":
            return request.redirect("/events")
        event = request.env["envcare.event"].browse(activity.res_id)
        user = request.env.user
        if not (user in (activity.user_id | activity.create_uid) or event.can_edit):
            return self._back_to_chatter(event, "Only the assigned user or the creator can mark this done.")
        try:
            activity.action_feedback(feedback=(post.get("feedback") or "").strip() or False)
        except (AccessError, UserError, ValidationError) as e:
            return self._back_to_chatter(event, str(e))
        return self._back_to_chatter(event)

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