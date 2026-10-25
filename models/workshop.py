from odoo import api, fields, models
from odoo.exceptions import ValidationError

class EnvWorkshopItems(models.Model):
    _name = "envcare.workshop.items"
    _description = "Environmental Care Workshop Items"

    workshop_id = fields.Many2one(
        "envcare.workshop",
        string="Workshop",
        required=True,
        readonly=True,
        ondelete="cascade"
    )

    product_id=fields.Many2one(
        "product.product",
        string="Name",
        required=True
    )

    qty = fields.Integer(
        string="Quantity",
        default=1,
        required=True
    )

    item_image=fields.Binary(
        related="product_id.image_1920",
        string="Image",
        readonly=True
    )

    remarks = fields.Html(
        string="Remarks"
    )

    availability = fields.Char(
        string="Availability",
        compute="_compute_availability",
        readonly=True
    )

    is_available = fields.Boolean(
        string="Is Available",
        compute="_compute_availability",
        store=False
    )

    @api.depends('qty', 'product_id')
    def _compute_availability(self):
        for record in self:
            if not record.product_id:
                record.availability = "Select Product"
                record.is_available = True
                continue

            on_hand = 0
            if hasattr(record.product_id, 'qty_available'):
                on_hand = record.product_id.qty_available

            requested = record.qty or 0

            if on_hand >= requested:
                difference = int(on_hand - requested)
                record.availability = f"✅ Available({difference})"
                record.is_available = True
            else:
                difference = int(requested - on_hand)
                record.availability = f"❌ Not Available({difference})"
                record.is_available = False



class EnvWorkshopAccounts(models.Model):
    _name = "envcare.workshop.accounts"
    _description = "Environmental Care Workshop Accounts"

    workshop_id = fields.Many2one(
        "envcare.workshop",
        string="Workshop",
        required=True,
        readonly=True,
        ondelete="cascade"
    )
    
    name = fields.Char(
        string="Expense Name",
        required=True
    )

    category_id = fields.Many2one(
        "envcare.workshop.accounts.categories",
        string="Category",
    )

    quantity = fields.Integer(
        string="Quantity",
    )

    amount = fields.Float(
        string="Expense Amount",
    )

    bills = fields.Many2many(
        "ir.attachment",
        string="Bills",
    )

    sevaks_ids = fields.Many2many(
        "res.users",
        string="Sevaks",
        domain="[('id','in',workshop_id_sevak_ids)]",
    )

    workshop_id_sevak_ids = fields.Many2many(
        "res.users",
        related="workshop_id.sevak_ids",
        string="Workshop Sevaks Helper"
    )

    remarks = fields.Text(
        string="Remarks",
    )

    re_imbursement = fields.Boolean(
        string="Re-imbursement Done?",
        default=False
    )


class EnvWorkshopAccountsCategories(models.Model):
    _name = "envcare.workshop.accounts.categories"
    _description = "Environmental Care Workshop Accounts Categories"

    name = fields.Char(
        string="Category Name",
        required=True
    )

class EnvWorkshops(models.Model):
    _name = "envcare.workshop"
    _description = "Environmental Care Workshop"

    name = fields.Char(
        string="Workshop Name",
        required=True
    )

    description = fields.Html(
        string="Description"
    )

    event_id = fields.Many2one(
        "envcare.event",
        string="Event ID",
        required=True,
        ondelete="cascade"
    )

    event_creator_id=fields.Many2one(
        "res.users",
        related="event_id.create_uid",
        string="Event Head",
        readonly=True
    )
    
    sevak_ids = fields.Many2many(
        comodel_name="res.users",
        relation="envcare_workshop_sevak_rel",
        column1="workshop_id",
        column2="user_id",
        string="Sevaks",
    )

    date_start = fields.Datetime(
        string="Start Date & Time"
    )

    date_end = fields.Datetime(
        string="End Date & Time"
    )

    state = fields.Selection(
        [
            ("draft","Draft"),
            ("workshop_lead_approved","Workshop Lead Approved"),
            ("hr_approved","HR Approved"),
            ("approved","Fully Approved"),
            ("closed","Closed")
        ],
        string="Status",
        default="draft",
        required=True,
        # tracking=True
    )

    workshop_lead_id = fields.Many2one(
        "res.users",
        string="Workshop Lead",
        required=True
    )

    workshop_deputy_id = fields.Many2one(
        "res.users",
        string="Workshop Deputy",
        required=True
    )

    items_ids = fields.One2many(
        "envcare.workshop.items",
        "workshop_id",
        string="Workshop Items"
    )

    accounts_ids = fields.One2many(
        "envcare.workshop.accounts",
        "workshop_id",
        string="Accounts"
    )

    pitch_deck = fields.Many2many(
        "ir.attachment",
        string="Pitch Deck"
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.workshop_lead_id and record.workshop_lead_id not in record.sevak_ids:
                record.sevak_ids = [(4, record.workshop_lead_id.id)]
            if record.workshop_deputy_id and record.workshop_deputy_id not in record.sevak_ids:
                record.sevak_ids = [(4, record.workshop_deputy_id.id)]
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'workshop_lead_id' in vals or 'workshop_deputy_id' in vals:
            for record in self:
                if record.workshop_lead_id and record.workshop_lead_id not in record.sevak_ids:
                    record.sevak_ids = [(4, record.workshop_lead_id.id)]
                if record.workshop_deputy_id and record.workshop_deputy_id not in record.sevak_ids:
                    record.sevak_ids = [(4, record.workshop_deputy_id.id)]
        return res

    @api.constrains('workshop_lead_id', 'workshop_deputy_id')
    def _check_lead_and_deputy_distinct(self):
        for record in self:
            if record.workshop_lead_id and record.workshop_deputy_id and record.workshop_lead_id == record.workshop_deputy_id:
                raise ValidationError(
                    f"The Workshop Lead and Workshop Deputy cannot be the same user ({record.workshop_lead_id.name}). "
                    "Please assign different users for these roles."
                )

    @api.onchange("workshop_lead_id","workshop_deputy_id")
    def _onchange_workshop_lead_id(self):
        if self.workshop_lead_id:
            self.sevak_ids |= self.workshop_lead_id
        if self.workshop_deputy_id:
            self.sevak_ids |= self.workshop_deputy_id

    @api.onchange("event_id")
    def _onchange_event_id(self):
        if self.event_id and not self.date_start and not self.date_end:
            self.date_start = self.event_id.date_begin
            self.date_end = self.event_id.date_end

    @api.constrains('sevak_ids','workshop_lead_id','workshop_deputy_id')
    def _check_workshop_lead_in_sevaks(self):
        for record in self:
            if record.workshop_lead_id and record.workshop_lead_id not in record.sevak_ids:
                raise ValidationError(
                    f"The Workshop Lead ({record.workshop_lead_id.name}) must remain in the Sevaks list. "
                    "You cannot remove the workshop lead unless you assign a different Workshop Lead first."
                )
            if record.workshop_deputy_id and record.workshop_deputy_id not in record.sevak_ids:
                raise ValidationError(
                    f"The Workshop Deputy ({record.workshop_deputy_id.name}) must remain in the Sevaks list. "
                    "You cannot remove the workshop deputy unless you assign a different Workshop Deputy first."
                )

    @api.constrains('date_start','date_end','event_id')
    def _check_workshop_dates(self):
        if not self.date_start and not self.date_end:
            self.date_start = self.event_id.date_begin
            self.date_end = self.event_id.date_end

        for record in self:
            if record.date_start and record.date_end:
                if record.date_start >= record.date_end:
                    raise ValidationError(
                        "Workshop End Time must be after Start Time"
                    )
                
                event = record.event_id
                if event and event.date_begin and event.date_end:
                    if (record.date_start < event.date_begin or record.date_end > event.date_end):
                        raise ValidationError(
                            f"The workshop timing ({record.date_start} to {record.date_end}) "
                            f"must fall within the parent Event timing ({event.date_begin} to {event.date_end})."
                        )

    @api.onchange("date_start","date_end")
    def _onchange_event_id(self):
        if not self.date_start and not self.date_end:
            self.date_start = self.event_id.date_begin
            self.date_end = self.event_id.date_end

    def action_approve_lead(self):
        for record in self:
            record.state = "workshop_lead_approved"

    def action_approve_hr(self):
        for record in self:
            record.state = "hr_approved"

    def action_approve_final(self):
        for record in self:
            record.state = "approved"
    
    def action_close(self):
        for record in self:
            record.state = "closed"

    def action_open_workshop(self):
        self.ensure_one()
        return {
            "type":"ir.actions.act_window",
            "name": f"Workshop: {self.name}",
            "res_model": "envcare.workshop",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": {
                "form_view_initial_mode": "edit",
                "force_detailed_view": True
            }
        }