"""Helpers shared by all Environmental Care website controllers."""
from datetime import datetime, timedelta

import pytz

from odoo.http import request
from odoo.tools import format_datetime, is_html_empty

# Models that have the website chatter (they inherit envcare.chatter.mixin)
CHATTER_MODELS = {"envcare.event", "envcare.workshop"}

ACTIVITY_TYPES = [
    ("mail.mail_activity_data_email", "Email"),
    ("mail.mail_activity_data_call", "Call"),
    ("mail.mail_activity_data_meeting", "Meeting"),
    ("mail.mail_activity_data_todo", "To Do"),
]


class EnvCareWebsiteMixin:
    """Plain mixin (not a controller): dates, sevak lists and chatter data."""

    # ---------- dates ----------
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

    def _format_dt(self, value):
        return format_datetime(request.env, value, tz=request.env.user.tz, dt_format="medium") if value else ""

    # ---------- people ----------
    def _sevak_options(self):
        """Environmental Care users (for Lead / Deputy / Send to / Assign to)."""
        group = request.env.ref("environmental_care.group_envcare_user")
        return request.env["res.users"].sudo().search(
            [("share", "=", False), ("groups_id", "in", group.ids)], order="name"
        )

    # ---------- chatter ----------
    def _chatter_values(self, record):
        """Everything the environmental_care.chatter template needs."""
        user = request.env.user
        can_manage = record._envcare_can_manage_chatter()

        messages = []
        for msg in record.message_ids.filtered(lambda m: m.message_type in ("comment", "notification")):
            tracking = [
                (change["changedField"], change["oldValue"]["value"] or "", change["newValue"]["value"] or "")
                for change in msg.sudo().tracking_value_ids._tracking_value_format()
            ]
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

        today = datetime.now(self._user_tz()).date()
        activities = []
        for act in record.activity_ids.sorted(lambda a: (a.date_deadline, a.envcare_remind_at or datetime.min)):
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
                "can_done": user in (act.user_id | act.create_uid) or can_manage,
            })

        default_remind = datetime.now(self._user_tz()) + timedelta(hours=1)
        base = f"/envcare/chatter/{record._name}/{record.id}"
        return {
            "chatter_messages": messages,
            "chatter_activities": activities,
            "can_send_message": can_manage,
            "event_owner": ", ".join(record._envcare_chatter_owner().mapped("name")),
            "activity_types": ACTIVITY_TYPES,
            "sevaks": self._sevak_options(),
            "default_remind_at": default_remind.strftime("%Y-%m-%dT%H:%M"),
            "chatter_error": request.params.get("chatter_error"),
            "chatter_post_url": f"{base}/post",
            "activity_schedule_url": f"{base}/schedule",
            "activity_done_url": "/envcare/activity/%s/done",
        }

    def _back_to_chatter(self, record, error=None):
        url = record._envcare_website_url()
        if error:
            from werkzeug.urls import url_encode
            url += "?" + url_encode({"chatter_error": error})
        return request.redirect(url + "#envcare_chatter")