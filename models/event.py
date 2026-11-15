from odoo import api, fields, models

class EnvEvents(models.Model):
    _name = "envcare.event"
    _description = "Environmental Care Event"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Anyone who can READ an event may use its chatter (log notes, messages,
    # activities). Who may *send* (email) a message is checked on the website.
    _mail_post_access = 'read'

    name = fields.Char(
        string="Event Name",
        required=True,
        index=True
    )

    description = fields.Html(
        string="Event Description",
        required=True
    )

    date_begin = fields.Datetime(
        string="Start Date",
        required=True,
        index=True
    )

    date_end = fields.Datetime(
        string="End Date",
        required=True,
        index=True
    )

    deadline = fields.Date(
        string="Deadline",
        required=True,
        index=True
    )

    location = fields.Char(
        string="Event Location",
        required=True
    )

    status = fields.Selection(
        [
            ("draft","Draft"),
            ("live","Live"),
            ("closed","Closed")
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        # tracking=True
    )

    document_ids = fields.Many2many(
        "ir.attachment",
        string="Documents"
    )

    workshop_ids = fields.One2many(
        "envcare.workshop",
        "event_id",
        string="Workshops"
    )

    # True when the logged-in user may edit this event:
    # IT (Sevak / Head) always, or Event Head AND (new event OR they created it).
    can_edit = fields.Boolean(
        compute="_compute_can_edit",
    )

    @api.depends("create_uid")
    @api.depends_context("uid")
    def _compute_can_edit(self):
        user = self.env.user
        is_it = user.has_group("environmental_care.group_envcare_it")
        is_head = user.has_group("environmental_care.group_event_head")
        for record in self:
            is_new = not record._origin.id
            record.can_edit = is_it or (is_head and (is_new or record.create_uid == user))

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        """Website chatter: when the context lists the partners to notify
        (event creator + sender + chosen receivers), notify ONLY them -
        not the followers - and always by e-mail (most users have no
        backend inbox)."""
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        listed = self.env.context.get("envcare_notify_partner_ids")
        if listed is None:
            return recipients
        listed = set(listed)
        return [dict(r, notif="email") for r in recipients if r["id"] in listed]

    def _get_access_action(self, access_uid=None, force_website=False):
        """Links in e-mails ("View Event", activity e-mails ...) open the
        website page for everyone except IT / Admin, who have the backend."""
        self.ensure_one()
        user = self.env["res.users"].sudo().browse(access_uid) if access_uid else self.env.user
        if not (user.has_group("base.group_system") or user.has_group("environmental_care.group_envcare_it")):
            return {
                "type": "ir.actions.act_url",
                "url": f"/event/{self.id}",
                "target": "self",
                "target_type": "public",
                "res_id": self.id,
            }
        return super()._get_access_action(access_uid=access_uid, force_website=force_website)

    def action_set_live(self):
        for record in self:
            record.status = "live"

    def action_set_closed(self):
        for record in self:
            record.status = "closed"