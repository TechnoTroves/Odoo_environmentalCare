from odoo import models, fields

class EnvEvents(models.Model):
    _name = "envcare.event"
    _description = "Environmental Care Event"
    _inherit = ['mail.thread', 'mail.activity.mixin']

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

    def action_set_live(self):
        for record in self:
            record.status = "live"

    def action_set_closed(self):
        for record in self:
            record.status = "closed"