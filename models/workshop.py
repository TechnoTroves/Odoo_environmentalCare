from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import is_html_empty

class EnvWorkshopItems(models.Model):
    _name = "envcare.workshop.items"
    _description = "Environmental Care Workshop Items"
    _inherit = ['mail.thread', 'mail.activity.mixin']

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



class EnvWorkshopBudgets(models.Model):
    _name = "envcare.workshop.budgets"
    _description = "Environmental Care Workshop Budgets"
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    _inherit = ['mail.thread','mail.activity.mixin']
    
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


# ---------------------------------------------------------------------------
# Workshop status flow
# ---------------------------------------------------------------------------
# Order the workshop moves through (canceled is outside the flow)
WORKSHOP_STATE_FLOW = [
    "draft",
    "workshop_lead_approved",
    "hr_approved",
    "additional_approved",
    "events_head_additional_approved",
    "events_head_approved_design_details",
    "closure_details",
    "closed",
]

# Content that must be filled BEFORE a workshop can move INTO a status.
# Add more statuses here as their rules are decided.
WORKSHOP_STATE_REQUIRED_FIELDS = {
    # Ready to be sent to HR for approval
    "workshop_lead_approved": [
        "name",
        "description",
        "event_id",
        "workshop_lead_id",
        "workshop_deputy_id",
        "date_start",
        "date_end",
        "sevak_ids",
        "items_ids",
    ],
}

# The backend header buttons (views/workshop_views.xml), as data:
#   target status -> (button method, statuses in which that button is visible)
# The website status dropdown offers exactly what these buttons allow, and
# applies a choice by calling the same button method - one set of rules.
WORKSHOP_BUTTONS = {
    "workshop_lead_approved": ("action_approve_lead", ["draft"]),
    "hr_approved": ("action_approve_hr", ["workshop_lead_approved"]),
    "additional_approved": ("action_approve_additional_lead", ["hr_approved"]),
    "events_head_additional_approved": ("action_approve_additional_head", ["additional_approved"]),
    "events_head_approved_design_details": ("action_approve_design_head", ["events_head_additional_approved"]),
    "closure_details": ("action_closure", ["events_head_approved_design_details"]),
    "closed": ("action_close", ["closure_details"]),
    # "Cancel Workshop" is hidden once the workshop is LIVE / closing / closed
    "canceled": ("action_cancel", [
        "draft", "workshop_lead_approved", "hr_approved",
        "additional_approved", "events_head_additional_approved",
    ]),
}

# Dropdown order: Draft and Canceled first, then the flow
WORKSHOP_DROPDOWN_ORDER = ["draft", "canceled"] + WORKSHOP_STATE_FLOW[1:]

# Who may move a workshop INTO each status (from the backend button labels).
#   lead        -> the workshop's Lead
#   hr          -> HR (Sevak / Head)
#   events_head -> Event Head
#   editor      -> anyone who can edit the workshop
# IT and Admin may always do every move.
WORKSHOP_STATE_ROLES = {
    "workshop_lead_approved": "lead",               # Approve (Workshop Lead)
    "hr_approved": "hr",                            # Approve (HR)
    "additional_approved": "lead",                  # Additional Approved (Workshop Lead)
    "events_head_additional_approved": "events_head",
    "events_head_approved_design_details": "events_head",
    "closure_details": "lead",                      # Closure (Workshop Lead)
    "closed": "events_head",                        # Close Workshop (Events Head)
    "canceled": "editor",                           # Cancel Workshop
}
WORKSHOP_ROLE_LABELS = {
    "lead": "the Workshop Lead",
    "hr": "HR",
    "events_head": "the Events Head",
    "editor": "someone who can edit the workshop",
}


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

    state = fields.Selection(
        [
            ("canceled","Canceled"),
            ("draft","Draft"),
            ("workshop_lead_approved","Workshop Lead Approved"),
            ("hr_approved","HR Approved"),
            ("additional_approved","Workshop Lead Approved Additional"),
            ("events_head_additional_approved","Events Head Approved Additional"),
            ("events_head_approved_design_details","LIVE Events Head Approved Design Details"),
            ("closure_details","Closure Details Approved"),
            ("closed","Closed")
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True
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

    # ---------------- status flow helpers ----------------
    def _get_next_state(self):
        """The status that comes after the current one (None at the end / canceled)."""
        self.ensure_one()
        if self.state not in WORKSHOP_STATE_FLOW:
            return None
        index = WORKSHOP_STATE_FLOW.index(self.state)
        return WORKSHOP_STATE_FLOW[index + 1] if index + 1 < len(WORKSHOP_STATE_FLOW) else None

    def _get_missing_fields_for(self, state):
        """Labels of the fields still empty before moving into `state`."""
        self.ensure_one()
        missing = []
        for fname in WORKSHOP_STATE_REQUIRED_FIELDS.get(state, []):
            field = self._fields[fname]
            value = self[fname]
            empty = is_html_empty(value) if field.type == "html" else not value
            if empty:
                missing.append(field.string)
        return missing

    def _get_previous_state(self):
        """The status before the current one (None for Draft / Canceled)."""
        self.ensure_one()
        if self.state not in WORKSHOP_STATE_FLOW:
            return None
        index = WORKSHOP_STATE_FLOW.index(self.state)
        return WORKSHOP_STATE_FLOW[index - 1] if index > 0 else None

    def _envcare_has_role(self, role, user=None):
        """Does `user` (default: current user) hold `role` for this workshop?"""
        self.ensure_one()
        user = user or self.env.user
        if user.has_group("base.group_system") or user.has_group("environmental_care.group_envcare_it"):
            return True
        if role == "lead":
            return user == self.sudo().workshop_lead_id
        if role == "hr":
            return user.has_group("environmental_care.group_envcare_hr_sevak")
        if role == "events_head":
            return user.has_group("environmental_care.group_event_head")
        if role == "editor":
            return self.with_user(user).has_access("write")
        return False

    def _envcare_can_move_to(self, target, user=None):
        """Role + flow + content check for one move."""
        self.ensure_one()
        if target == self.state:
            return True
        previous_state, next_state = self._get_previous_state(), self._get_next_state()
        if target == next_state:
            return (self._envcare_has_role(WORKSHOP_STATE_ROLES.get(target), user)
                    and not self._get_missing_fields_for(target))
        if target == previous_state:
            # step back = undo the current approval: same people who approve it
            return self._envcare_has_role(WORKSHOP_STATE_ROLES.get(self.state), user)
        if target == "canceled":
            _method, visible_in = WORKSHOP_BUTTONS["canceled"]
            return self.state in visible_in and self._envcare_has_role("editor", user)
        return False

    def _get_website_state_options(self, user=None):
        """Status dropdown on the website: 1 before, the current one, 1 after
        (+ Canceled where the backend allows it) - each only if this user may
        make that move. Order: Draft and Canceled first, then the flow."""
        self.ensure_one()
        candidates = {self.state, self._get_previous_state(), self._get_next_state(), "canceled"} - {None}
        allowed = {state for state in candidates if self._envcare_can_move_to(state, user)}
        return [state for state in WORKSHOP_DROPDOWN_ORDER if state in allowed]

    def _envcare_status_info(self, user=None):
        """For the website "i" button: dropdown options + why the next step is locked."""
        self.ensure_one()
        labels = dict(self._fields["state"]._description_selection(self.env))
        options = self._get_website_state_options(user)
        next_state = self._get_next_state()
        missing, waiting_for = [], ""
        if next_state and next_state not in options:
            missing = self._get_missing_fields_for(next_state)
            if not missing:
                waiting_for = WORKSHOP_ROLE_LABELS.get(WORKSHOP_STATE_ROLES.get(next_state), "")
        return {
            "options": [(state, labels.get(state, state)) for state in options],
            "missing": missing,
            "waiting_for": waiting_for,
            "next_label": labels.get(next_state, "") if next_state else "",
        }

    def _apply_website_state(self, target):
        """Move to `target` if the current user may. The move itself runs as
        superuser AFTER the role check, because approvers (Lead, HR ...) are
        not allowed to edit the workshop's other fields."""
        self.ensure_one()
        if target == self.state:
            return
        if not self._envcare_can_move_to(target):
            labels = dict(self._fields["state"]._description_selection(self.env))
            missing = self._get_missing_fields_for(target)
            raise ValidationError(
                f"You cannot move workshop '{self.name}' to '{labels.get(target, target)}'."
                + (f" Please fill: {', '.join(missing)}." if missing else "")
            )
        record = self.sudo()  # same user id -> chatter shows who did it
        if target == self._get_previous_state():
            record.state = target
        else:
            getattr(record, WORKSHOP_BUTTONS[target][0])()

    # ---------------- website chatter hooks ----------------
    def _envcare_website_url(self):
        return f"/workshop/{self.id}"

    def _envcare_chatter_owner(self):
        # Workshop owners: the Events Head of the parent event, the Lead and the Deputy
        record = self.sudo()
        return record.event_id.create_uid | record.workshop_lead_id | record.workshop_deputy_id

    def _envcare_can_manage_chatter(self):
        return self.has_access("write") or self.env.user.has_group("base.group_system")

    def _check_ready_for(self, state):
        for record in self:
            missing = record._get_missing_fields_for(state)
            if missing:
                label = dict(record._fields["state"]._description_selection(record.env)).get(state, state)
                raise ValidationError(
                    f"Workshop '{record.name}' cannot move to '{label}' yet. "
                    f"Please fill: {', '.join(missing)}."
                )

    def action_approve_lead(self):
        self._check_ready_for("workshop_lead_approved")
        for record in self:
            record.state = "workshop_lead_approved"

    def action_approve_hr(self):
        for record in self:
            record.state = "hr_approved"
    
    def action_approve_additional_lead(self):
        for record in self:
            record.state = "additional_approved"
            
    def action_approve_additional_head(self):
        for record in self:
            record.state = "events_head_additional_approved"

    def action_approve_design_head(self):
        for record in self:
            record.state = "events_head_approved_design_details"

    def action_closure(self):
        for record in self:
            record.state = "closure_details"

    def action_close(self):
        for record in self:
            record.state = "closed"

    def action_cancel(self):
        for record in self:
            record.state = "canceled"

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