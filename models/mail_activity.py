import logging

from markupsafe import Markup

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MailActivity(models.Model):
    """Activities scheduled from the Environmental Care website get an exact
    reminder time. A scheduled job e-mails the assigned (selected) user
    when that time comes - and only then."""
    _inherit = "mail.activity"

    envcare_remind_at = fields.Datetime(
        string="Remind At",
        help="Date and time when the assigned user gets the reminder e-mail.",
    )
    envcare_reminder_sent = fields.Boolean(string="Reminder Sent", copy=False)
    # Activities scheduled together (one per selected user) share this key
    envcare_group_key = fields.Char(copy=False, index=True)

    def write(self, vals):
        if "envcare_remind_at" in vals:
            vals = dict(vals, envcare_reminder_sent=False)  # new time -> remind again
        return super().write(vals)

    # ------------------------------------------------------------------
    # Reminder job (ir.cron "EC: Activity reminders", every 5 minutes)
    # ------------------------------------------------------------------
    @api.model
    def _envcare_send_activity_reminders(self):
        now = fields.Datetime.now()
        activities = self.sudo().search([
            ("envcare_remind_at", "!=", False),
            ("envcare_remind_at", "<=", now),
            ("envcare_reminder_sent", "=", False),
        ])
        if not activities:
            return

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        email_from = self.env.company.email_formatted or self.env.user.email_formatted
        Mail = self.env["mail.mail"].sudo()
        mails = Mail

        for activity in activities:
            record = self.env[activity.res_model].sudo().browse(activity.res_id)
            if hasattr(record, "_envcare_website_url"):
                link = base_url + record._envcare_website_url()   # e.g. /event/5, /workshop/7
            else:
                link = f"{base_url}/odoo/{activity.res_model}/{activity.res_id}"

            # Only the selected (assigned) user is notified
            recipients = activity.user_id

            subject = f"Reminder: {activity.activity_type_id.name} - {activity.summary or activity.res_name}"
            body = Markup(
                "<p>This is a reminder for the activity <strong>{type}</strong>"
                " on <strong>{record}</strong>.</p>"
                "<p><strong>Summary:</strong> {summary}<br/>"
                "<strong>Assigned to:</strong> {assignee}<br/>"
                "<strong>Scheduled by:</strong> {creator}</p>"
                "{note}"
                '<p><a href="{link}">Open in Environmental Care</a></p>'
            ).format(
                type=activity.activity_type_id.name or "",
                record=activity.res_name or "",
                summary=activity.summary or "-",
                assignee=activity.user_id.name or "-",
                creator=activity.create_uid.name or "-",
                note=Markup("<div>{}</div>").format(activity.note) if activity.note else "",
                link=link,
            )
            for user in recipients.filtered(lambda u: u.active and u.email):
                mails |= Mail.create({
                    "subject": subject,
                    "body_html": body,
                    "email_from": email_from,
                    "email_to": user.email_formatted,
                    "auto_delete": True,
                })
            activity.envcare_reminder_sent = True

        if mails:
            # send now: the normal mail queue only runs once an hour
            mails.send()
        _logger.info("EC activity reminders: %s activities, %s e-mails", len(activities), len(mails))