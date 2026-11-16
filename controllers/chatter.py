"""Website chatter routes, shared by every model in CHATTER_MODELS."""
import uuid

import pytz
from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.tools import html_sanitize, is_html_empty

from .common import ACTIVITY_TYPES, CHATTER_MODELS, EnvCareWebsiteMixin


class EnvCareChatter(EnvCareWebsiteMixin, http.Controller):

    def _chatter_record(self, model, res_id):
        """The record behind a chatter URL, or None if not allowed / not found."""
        if model not in CHATTER_MODELS:
            return None
        record = request.env[model].browse(res_id).exists()
        if not record:
            return None
        try:
            record.check_access("read")
        except (AccessError, MissingError):
            return None
        return record

    @http.route("/envcare/chatter/<string:model>/<int:res_id>/post", type="http", auth="user",
                website=True, methods=["POST"])
    def chatter_post(self, model, res_id, **post):
        """Log note (everyone who can see the record) or Send message (only
        _envcare_can_manage_chatter users). Both e-mail the owner, the sender
        and the people picked in "Send to" - nobody else, no following needed."""
        record = self._chatter_record(model, res_id)
        if not record:
            return request.redirect("/my")
        mode = post.get("mode") or "note"
        if mode == "message" and not record._envcare_can_manage_chatter():
            return self._back_to_chatter(record, "You are not allowed to send messages here.")
        body = html_sanitize(post.get("body") or "")
        files = [f for f in request.httprequest.files.getlist("attachments") if f and f.filename]
        if is_html_empty(body) and not files:
            return self._back_to_chatter(record, "Please write something before posting.")

        picked = {int(u) for u in request.httprequest.form.getlist("recipient_ids") if u.isdigit()}
        partners = self._sevak_options().filtered(lambda u: u.id in picked).partner_id
        partners |= record._envcare_chatter_owner().partner_id
        partners |= request.env.user.partner_id
        partner_ids = partners.ids
        try:
            record.with_context(
                mail_create_nosubscribe=True,          # nobody becomes a follower
                envcare_notify_partner_ids=partner_ids,  # only these are e-mailed
            ).message_post(
                body=Markup(body),
                message_type="comment",
                subtype_xmlid="mail.mt_comment" if mode == "message" else "mail.mt_note",
                partner_ids=partner_ids,
                attachments=[(f.filename, f.read()) for f in files],
                notify_author=True,  # the sender gets a copy too
            )
        except (AccessError, UserError, ValidationError) as e:
            return self._back_to_chatter(record, str(e))
        return self._back_to_chatter(record)

    @http.route("/envcare/chatter/<string:model>/<int:res_id>/schedule", type="http", auth="user",
                website=True, methods=["POST"])
    def chatter_schedule(self, model, res_id, **post):
        """One activity per selected user. Nothing is sent now: only the
        selected users get a reminder e-mail at the scheduled time."""
        record = self._chatter_record(model, res_id)
        if not record:
            return request.redirect("/my")
        type_xmlid = post.get("activity_type")
        if type_xmlid not in dict(ACTIVITY_TYPES):
            return self._back_to_chatter(record, "Please choose an activity type.")
        remind_at = self._from_input_datetime(post.get("remind_at"))
        if not remind_at:
            return self._back_to_chatter(record, "Please choose the date and time of the activity.")
        allowed_ids = set(self._sevak_options().ids)
        user_ids = [int(u) for u in request.httprequest.form.getlist("user_ids")
                    if u.isdigit() and int(u) in allowed_ids] or [request.env.user.id]
        local_day = pytz.utc.localize(remind_at).astimezone(self._user_tz()).date()
        group_key = uuid.uuid4().hex
        try:
            with request.env.cr.savepoint():
                # mail_activity_quick_update: no "assigned to you" e-mail now
                scheduler = record.with_context(mail_activity_quick_update=True)
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
            return self._back_to_chatter(record, str(e))
        return self._back_to_chatter(record)

    @http.route("/envcare/activity/<int:activity_id>/done", type="http", auth="user",
                website=True, methods=["POST"])
    def activity_done(self, activity_id, **post):
        activity = request.env["mail.activity"].browse(activity_id).exists()
        record = activity and self._chatter_record(activity.res_model, activity.res_id)
        if not record:
            return request.redirect("/my")
        user = request.env.user
        if not (user in (activity.user_id | activity.create_uid) or record._envcare_can_manage_chatter()):
            return self._back_to_chatter(record, "Only the assigned user or the creator can mark this done.")
        try:
            activity.action_feedback(feedback=(post.get("feedback") or "").strip() or False)
        except (AccessError, UserError, ValidationError) as e:
            return self._back_to_chatter(record, str(e))
        return self._back_to_chatter(record)