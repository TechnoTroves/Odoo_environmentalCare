from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

class EnvWorkshopLineMixin(models.AbstractModel):
    """Lines of a workshop (items, budget, accounts, document URLs): nobody but
    IT / Admin may change them while their workshop is canceled. Who may edit
    them at all is a record rule (same people as the workshop)."""
    _name = "envcare.workshop.line.mixin"
    _description = "Environmental Care Workshop Line (canceled lock)"

    @api.model_create_multi
    def create(self, vals_list):
        workshop_ids = {vals.get("workshop_id") for vals in vals_list} - {None, False}
        self.env["envcare.workshop"].browse(list(workshop_ids))._envcare_check_not_canceled()
        return super().create(vals_list)

    def write(self, vals):
        if all(key.startswith(EnvWorkshops._ENVCARE_FREE_FIELD_PREFIXES) for key in vals):
            return super().write(vals)  # chatter / activity bookkeeping only
        self.workshop_id._envcare_check_not_canceled()
        if vals.get("workshop_id"):
            self.env["envcare.workshop"].browse(vals["workshop_id"])._envcare_check_not_canceled()
        return super().write(vals)

    def unlink(self):
        self.workshop_id._envcare_check_not_canceled()
        return super().unlink()


class EnvWorkshopItems(models.Model):
    _name = "envcare.workshop.items"
    _description = "Environmental Care Workshop Items"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.workshop.line.mixin']

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
                record.availability = f"✅ Available"
                record.is_available = True
            else:
                difference = int(requested - on_hand)
                record.availability = f"❌ Not Available"
                record.is_available = False



class EnvWorkshopBudgets(models.Model):
    _name = "envcare.workshop.budgets"
    _description = "Environmental Care Workshop Budgets"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.workshop.line.mixin']

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
        "envcare.workshop.budgets.categories",
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

    workshop_id_sevak_ids = fields.Many2many(
        "res.users",
        related="workshop_id.sevak_ids",
        string="Workshop Sevaks Helper"
    )

    remarks = fields.Text(
        string="Remarks",
    )

class EnvWorkshopAccounts(models.Model):
    _name = "envcare.workshop.accounts"
    _description = "Environmental Care Workshop Accounts"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.workshop.line.mixin']

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

    paid_by = fields.Many2one(
        "res.users",
        string="Paid By",
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
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Category Name",
        required=True
    )

class EnvWorkshopBudgetsCategories(models.Model):
    _name = "envcare.workshop.budgets.categories"
    _description = "Environmental Care Workshop Budgets Categories"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Category Name",
        required=True
    )

class EnvWorkshopDocs(models.Model):
    _name = "envcare.workshop.docs"
    _description = "Environmental Care Workshop Documents"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.workshop.line.mixin']
    
    docs_urls = fields.Char(
        string="Docs URLs"
    )

    workshop_id = fields.Many2one(
        "envcare.workshop",
        string="Workshop",
        required=True,
        readonly=True,
        ondelete="cascade"
    )


class EnvWorkshops(models.Model):
    _name = "envcare.workshop"
    _description = "Environmental Care Workshop"
    # envcare.chatter.mixin: website chatter (post access, e-mail recipients, links)
    _inherit = ['mail.thread', 'mail.activity.mixin', 'envcare.chatter.mixin']

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

    # Replaces the old Status. Only the parent event's Events Head and IT / Admin
    # can switch it; a canceled workshop is read-only for everyone except IT / Admin.
    is_canceled = fields.Boolean(
        string="Canceled",
        default=False,
        tracking=True
    )

    # For the logged-in user (views + website): see _envcare_can_edit / _envcare_can_cancel
    can_edit = fields.Boolean(
        compute="_compute_envcare_access",
    )

    can_cancel = fields.Boolean(
        compute="_compute_envcare_access",
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

    budgets_ids = fields.One2many(
        "envcare.workshop.budgets",
        "workshop_id",
        string="Budget"
    )

    pitch_deck = fields.Many2many(
        "ir.attachment",
        "workshop_pitch_deck_rel",
        "workshop_id", 
        "attachment_id",
        string="Pitch Deck"
    )

    process = fields.Html(
        string="Workshop Process"
    )

    design_requirements = fields.Html(
        string="Design Requirements"
    )

    design_collaterals = fields.Many2many(
        "ir.attachment",
        "workshop_design_collaterals_rel",
        "workshop_id", 
        "attachment_id",
        string="Design Collaterals"
    )

    statistics_product_impact = fields.Html(
        string="Stats - Product Impact"
    )

    talkie = fields.Html(
        string="Talkie"
    )

    accounts_ids = fields.One2many(
        "envcare.workshop.accounts",
        "workshop_id",
        string="Accounts"
    )

    statistics_workshop = fields.Html(
        string="Stats - Workshop"
    )

    av_footage = fields.Many2many(
        "ir.attachment",
        "workshop_av_footage_rel",
        "workshop_id", 
        "attachment_id",
        string="AV Footage"
    )

    docs_files = fields.Many2many(
        "ir.attachment",
        "workshop_docs_files_rel",
        "workshop_id", 
        "attachment_id",
        string="Docs Files"
    )

    doc_id = fields.One2many(
        "envcare.workshop.docs",
        "workshop_id",
        string="Document URLs"
    )

    @staticmethod
    def _add_lead_deputy_to_sevaks(vals):
        """Put the Lead / Deputy into sevak_ids in the SAME save, so the
        "must remain in the Sevaks list" check passes (website, imports, code -
        not only the backend form, where the onchange already does it)."""
        user_ids = [vals[key] for key in ("workshop_lead_id", "workshop_deputy_id") if vals.get(key)]
        if not user_ids:
            return vals
        commands = list(vals.get("sevak_ids") or [])
        commands += [Command.link(user_id) for user_id in user_ids]
        return dict(vals, sevak_ids=commands)

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._add_lead_deputy_to_sevaks(vals) for vals in vals_list])

    def write(self, vals):
        self._envcare_check_write(vals)
        return super().write(self._add_lead_deputy_to_sevaks(vals))

    @api.constrains('workshop_lead_id', 'workshop_deputy_id')
    def _check_lead_and_deputy_distinct(self):
        for record in self:
            if record.workshop_lead_id and record.workshop_deputy_id and record.workshop_lead_id == record.workshop_deputy_id:
                raise ValidationError(
                    f"The Workshop Lead and Workshop Deputy cannot be the same user ({record.workshop_lead_id.name}). "
                    "Please assign different users for these roles."
                )

    @api.onchange("event_id", "date_start", "date_end", "workshop_lead_id", "workshop_deputy_id")
    def _onchange_event_id(self):
        # Default workshop timing to the parent event's timing
        if self.event_id and not self.date_start and not self.date_end:
            self.date_start = self.event_id.date_begin
            self.date_end = self.event_id.date_end
        # Lead and Deputy are always part of the Sevaks
        if self.workshop_lead_id:
            self.sevak_ids |= self.workshop_lead_id
        if self.workshop_deputy_id:
            self.sevak_ids |= self.workshop_deputy_id

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

    # ---------------- access: who may edit / cancel ----------------
    # Edit:   IT / Admin always; the parent event's Events Head, the Workshop
    #         Lead and the Workshop Deputy while the workshop is not canceled.
    # Cancel: IT / Admin and the parent event's Events Head.
    # The same rules are record rules in security/envcare_security.xml (edit)
    # and checked again in write() (cancel + canceled lock) - the website and
    # the backend only hide what the server would refuse anyway.
    # Later: per-field edit / approval rights per role are added on top of this.

    # Mail / activity bookkeeping is not "editing the workshop"
    _ENVCARE_FREE_FIELD_PREFIXES = ("message_", "activity_", "website_message", "rating_")

    def _envcare_is_it_or_admin(self, user=None):
        user = user or self.env.user
        return user.has_group("environmental_care.group_envcare_it") or user.has_group("base.group_system")

    def _envcare_is_team(self, user=None):
        """Events Head of the parent event, Workshop Lead or Workshop Deputy."""
        self.ensure_one()
        user = user or self.env.user
        record = self.sudo()
        return user in (record.event_id.create_uid | record.workshop_lead_id | record.workshop_deputy_id)

    def _envcare_can_cancel(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if self._envcare_is_it_or_admin(user):
            return True
        return (user.has_group("environmental_care.group_event_head")
                and self.sudo().event_id.create_uid == user)

    def _envcare_can_edit(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if self._envcare_is_it_or_admin(user):
            return True
        return not self.is_canceled and self._envcare_is_team(user)

    @api.depends_context("uid")
    def _compute_envcare_access(self):
        user = self.env.user
        is_it = self._envcare_is_it_or_admin(user)
        is_head = user.has_group("environmental_care.group_event_head")
        for record in self:
            saved = record._origin  # saved values: the form doesn't lock itself while typing
            if is_it:
                record.can_edit = record.can_cancel = True
            elif not saved.id:
                # New workshop: Events Heads (for their own events, checked on save)
                record.can_edit, record.can_cancel = is_head, False
            else:
                record.can_edit = saved._envcare_can_edit(user)
                record.can_cancel = saved._envcare_can_cancel(user)

    def _envcare_check_write(self, vals):
        """Server-side guard for write(): Canceled switch + canceled lock."""
        if self.env.su or self._envcare_is_it_or_admin():
            return
        content = [key for key in vals if key != "is_canceled"
                   and not key.startswith(self._ENVCARE_FREE_FIELD_PREFIXES)]
        for record in self:
            if "is_canceled" in vals and bool(vals["is_canceled"]) != record.is_canceled \
                    and not record._envcare_can_cancel():
                raise AccessError(
                    f"Only the Events Head of '{record.event_id.name}' or IT can cancel / un-cancel "
                    f"workshop '{record.name}'."
                )
            still_canceled = record.is_canceled and vals.get("is_canceled", True)
            if content and still_canceled:
                raise UserError(f"Workshop '{record.name}' is canceled, so it cannot be changed.")

    def _envcare_check_not_canceled(self):
        """Used by the workshop's lines (items, budget, accounts, documents)."""
        if self.env.su or self._envcare_is_it_or_admin():
            return
        for record in self.sudo():
            if record.is_canceled:
                raise UserError(f"Workshop '{record.name}' is canceled, so it cannot be changed.")

    @api.model
    def _envcare_migrate_canceled_state(self):
        """Upgrade step (called from security/envcare_security.xml): the old
        Status column is left in the database by Odoo - carry 'Canceled' over
        to the new Canceled switch. Does nothing once the column is gone."""
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'envcare_workshop' AND column_name = 'state'
        """)
        if self.env.cr.fetchone():
            self.env.cr.execute("""
                UPDATE envcare_workshop SET is_canceled = TRUE
                 WHERE state = 'canceled' AND is_canceled IS NOT TRUE
            """)
            # Odoo drops the old column after the upgrade; until then it must not block new rows
            self.env.cr.execute("ALTER TABLE envcare_workshop ALTER COLUMN state DROP NOT NULL")
            self.invalidate_model(["is_canceled"])

    # ---------------- website chatter hooks ----------------
    def _envcare_website_url(self):
        return f"/workshop/{self.id}"

    def _envcare_chatter_owner(self):
        # Workshop owners: the Events Head of the parent event, the Lead and the Deputy
        record = self.sudo()
        return record.event_id.create_uid | record.workshop_lead_id | record.workshop_deputy_id

    def _envcare_can_manage_chatter(self):
        return self.has_access("write") or self.env.user.has_group("base.group_system")

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