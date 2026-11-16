from odoo import api, fields, models

class EnvEvents(models.Model):
    _name = "envcare.event"
    _description = "Environmental Care Event"
    # envcare.chatter.mixin: website chatter (post access, e-mail recipients, links)
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.chatter.mixin']

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

    # ---------------- website chatter hooks ----------------
    def _envcare_website_url(self):
        return f"/event/{self.id}"

    def _envcare_chatter_owner(self):
        return self.sudo().create_uid

    def _envcare_can_manage_chatter(self):
        # Events Head who created the event, IT (can_edit) or Admin
        return self.can_edit or self.env.user.has_group("base.group_system")

    def action_set_live(self):
        for record in self:
            record.status = "live"

    def action_set_closed(self):
        for record in self:
            record.status = "closed"