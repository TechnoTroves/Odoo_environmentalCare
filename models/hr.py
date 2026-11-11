from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Sevak Master fields (HR sheet) that HR and IT may create / edit on any user.
# Everything else on res.users (password, groups, ...) stays with Settings admins.
ENVCARE_HR_FIELDS = {
    "image_1920",
    "name",
    "login",
    "email",
    "envcare_contact",
    "envcare_address",
    "envcare_allergies",
    "envcare_expertise_ids",
    "envcare_arpit_group_id",
    "envcare_gid",
    "envcare_qr_image",
    "envcare_dob",
    "envcare_committed_hours_id",
    "envcare_department_line_ids",
}

HR_GROUP = "environmental_care.group_envcare_hr_sevak"
IT_GROUP = "environmental_care.group_envcare_it"

# Personal data - only HR, IT and Settings admins can read these fields
HR_PRIVATE = f"{HR_GROUP},{IT_GROUP},base.group_erp_manager"


# ---------------------------------------------------------------------------
# Master lists (from the "Master Lists" sheet)
# ---------------------------------------------------------------------------
class EnvCareHrExpertise(models.Model):
    _name = "envcare.hr.expertise"
    _description = "Environmental Care HR Expertise"
    _order = "name"

    name = fields.Char(string="Expertise", required=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "This expertise already exists."),
    ]


class EnvCareHrArpitGroup(models.Model):
    _name = "envcare.hr.arpit.group"
    _description = "Environmental Care HR Arpit Group"
    _order = "name"

    name = fields.Char(string="Arpit Group", required=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "This Arpit Group already exists."),
    ]


class EnvCareHrCommittedHours(models.Model):
    _name = "envcare.hr.committed.hours"
    _description = "Environmental Care HR Committed Hours"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Committed Hours", required=True)


# ---------------------------------------------------------------------------
# Departments and Roles
# A Role is linked to ONE security group. Assigning a Role to a user
# adds that group; changing / clearing it removes the old one.
# Only IT can edit this mapping, so HR can only hand out groups IT allowed.
# ---------------------------------------------------------------------------
class EnvCareHrDepartment(models.Model):
    _name = "envcare.hr.department"
    _description = "Environmental Care HR Department"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Department", required=True)
    role_ids = fields.One2many("envcare.hr.department.role", "department_id", string="Roles")
    line_ids = fields.One2many("envcare.hr.user.department", "department_id", string="Members")

    _sql_constraints = [
        ("name_unique", "unique(name)", "This department already exists."),
    ]


class EnvCareHrDepartmentRole(models.Model):
    _name = "envcare.hr.department.role"
    _description = "Environmental Care HR Department Role"
    _order = "department_id, sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Role", required=True)
    department_id = fields.Many2one(
        "envcare.hr.department", string="Department", required=True, ondelete="cascade"
    )
    group_id = fields.Many2one(
        "res.groups",
        string="Access Group",
        required=True,
        ondelete="restrict",
        help="Users given this role are added to this group.",
    )

    @api.depends("name", "department_id.name")
    def _compute_display_name(self):
        for role in self:
            role.display_name = f"{role.department_id.name} / {role.name}" if role.department_id else role.name


# ---------------------------------------------------------------------------
# Sevak <-> Department / Role (a sevak can be in many departments,
# with one role per department)
# ---------------------------------------------------------------------------
class EnvCareHrUserDepartment(models.Model):
    _name = "envcare.hr.user.department"
    _description = "Environmental Care HR Sevak Department / Role"
    _order = "department_id, id"

    user_id = fields.Many2one("res.users", string="Sevak", required=True, ondelete="cascade", index=True)
    department_id = fields.Many2one("envcare.hr.department", string="Department", required=True, ondelete="cascade")
    role_id = fields.Many2one(
        "envcare.hr.department.role",
        string="Role",
        ondelete="set null",
        domain="[('department_id', '=', department_id)]",
    )

    _sql_constraints = [
        ("user_department_unique", "unique(user_id, department_id)",
         "A sevak can be added to the same department only once."),
    ]

    @api.constrains("department_id", "role_id")
    def _check_role_department(self):
        for line in self:
            if line.role_id and line.role_id.department_id != line.department_id:
                raise ValidationError(
                    _("The role %(role)s does not belong to the department %(dept)s.",
                      role=line.role_id.name, dept=line.department_id.name)
                )

    @api.onchange("department_id")
    def _onchange_department_id(self):
        if self.role_id and self.role_id.department_id != self.department_id:
            self.role_id = False

    # Any change here -> update the sevak's groups
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.user_id._envcare_after_department_change()
        return lines

    def write(self, vals):
        users = self.user_id
        res = super().write(vals)
        (users | self.user_id)._envcare_after_department_change()
        return res

    def unlink(self):
        users = self.user_id
        res = super().unlink()
        users.exists()._envcare_after_department_change()
        return res


# ---------------------------------------------------------------------------
# Sevak Master Record (on res.users)
# ---------------------------------------------------------------------------
class ResUsers(models.Model):
    _inherit = "res.users"

    envcare_sr_no = fields.Char(string="Sr No", readonly=True, copy=False, index=True)
    envcare_contact = fields.Char(string="Contact No.", groups=HR_PRIVATE)
    envcare_address = fields.Text(string="Address", groups=HR_PRIVATE)
    envcare_allergies = fields.Text(
        string="Allergies / Badha",
        groups=HR_PRIVATE,
        help="Anything to be aware of on site - food, medical, restrictions.",
    )
    envcare_expertise_ids = fields.Many2many(
        "envcare.hr.expertise",
        "envcare_hr_user_expertise_rel",
        "user_id",
        "expertise_id",
        string="Expertise",
    )
    envcare_arpit_group_id = fields.Many2one("envcare.hr.arpit.group", string="Arpit Group")
    envcare_gid = fields.Char(string="GID", copy=False, groups=HR_PRIVATE, help="Unique identity number.")
    envcare_qr_image = fields.Image(
        string="One-time QR",
        max_width=512,
        max_height=512,
        copy=False,
        groups=HR_PRIVATE,
        help="QR image uploaded by HR. Used for attendance / entry at events.",
    )
    envcare_dob = fields.Date(string="DOB", groups=HR_PRIVATE)
    envcare_age = fields.Integer(string="Age", compute="_compute_envcare_age", groups=HR_PRIVATE)
    envcare_committed_hours_id = fields.Many2one("envcare.hr.committed.hours", string="Committed Hours")
    envcare_department_line_ids = fields.One2many(
        "envcare.hr.user.department", "user_id", string="Departments & Roles"
    )
    envcare_department_ids = fields.Many2many(
        "envcare.hr.department",
        "envcare_hr_user_department_rel",
        "user_id",
        "department_id",
        string="Departments",
        compute="_compute_envcare_departments",
        store=True,
    )
    envcare_role_ids = fields.Many2many(
        "envcare.hr.department.role",
        "envcare_hr_user_role_rel",
        "user_id",
        "role_id",
        string="Roles",
        compute="_compute_envcare_departments",
        store=True,
    )

    _sql_constraints = [
        ("envcare_gid_unique", "unique(envcare_gid)", "GID must be unique for every sevak."),
    ]

    # ---------------- computes ----------------
    @api.depends("envcare_dob")
    def _compute_envcare_age(self):
        today = fields.Date.context_today(self)
        for user in self:
            dob = user.envcare_dob
            if dob:
                user.envcare_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            else:
                user.envcare_age = 0

    @api.depends("envcare_department_line_ids.department_id", "envcare_department_line_ids.role_id")
    def _compute_envcare_departments(self):
        for user in self:
            user.envcare_department_ids = user.envcare_department_line_ids.department_id
            user.envcare_role_ids = user.envcare_department_line_ids.role_id

    # ---------------- constraints ----------------
    @api.constrains("envcare_dob")
    def _check_envcare_dob(self):
        today = fields.Date.context_today(self)
        for user in self:
            if user.envcare_dob and user.envcare_dob > today:
                raise ValidationError(_("Date of birth cannot be in the future."))

    # ---------------- create / write ----------------
    def _envcare_is_manager(self):
        """HR (Sevak / Head) or IT (Sevak / Head)."""
        user = self.env.user
        return user.has_group(HR_GROUP) or user.has_group(IT_GROUP)

    def _envcare_use_manager_mode(self, keys):
        """True when an HR / IT user (not a Settings admin) is saving
        Sevak Master fields. Those writes are checked here and then done
        with sudo, so they also update the linked contact (name / email)."""
        if self.env.su or self.env.user.has_group("base.group_erp_manager"):
            return False
        if not self._envcare_is_manager():
            return False  # normal access rules apply (= denied)
        blocked = set(keys) - ENVCARE_HR_FIELDS
        if blocked:
            raise AccessError(_("You can only edit Sevak Master fields. Not allowed: %s", ", ".join(sorted(blocked))))
        return True

    @staticmethod
    def _envcare_prepare_vals(vals):
        # One "Email" in the sheet -> keep login and contact email the same
        if vals.get("login") and "email" not in vals:
            vals = dict(vals, email=vals["login"])
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        keys = set().union(*vals_list) if vals_list else set()
        if self._envcare_use_manager_mode(keys):
            self.check_access("create")
            vals_list = [self._envcare_prepare_vals(vals) for vals in vals_list]
            users = super(ResUsers, self.sudo()).create(vals_list).with_env(self.env)
        else:
            users = super().create(vals_list)
        # Departments given in the form are synced by the line model;
        # otherwise read Department / Role from the groups the user got.
        if not self.env.context.get("envcare_skip_sync") and "envcare_department_line_ids" not in keys:
            users._envcare_sync_role_from_groups()
        return users

    def write(self, vals):
        own_prefs = self == self.env.user and set(vals) <= set(self.SELF_WRITEABLE_FIELDS)
        if not own_prefs and self._envcare_use_manager_mode(vals):
            self.check_access("write")
            self._envcare_check_manager_targets(vals)
            res = super(ResUsers, self.sudo()).write(self._envcare_prepare_vals(vals))
        else:
            res = super().write(vals)
        if not self.env.context.get("envcare_skip_sync") and any(self._envcare_is_group_key(k) for k in vals):
            # Groups changed (e.g. Settings > Users) -> update Departments / Roles
            self._envcare_sync_role_from_groups()
        return res

    @staticmethod
    def _envcare_is_group_key(key):
        # Settings > Users form sends groups as groups_id or as
        # virtual "sel_groups_x_y" / "in_group_x" fields
        return key == "groups_id" or key.startswith(("sel_groups_", "in_group_"))

    def _envcare_check_manager_targets(self, vals):
        env_user = self.env.user
        keys = set(vals)
        if env_user in self and "envcare_department_line_ids" in keys:
            raise AccessError(_("You cannot change your own departments or roles."))
        # Changing someone's login lets you reset their password, and their
        # departments change their access. HR cannot do that for IT / admin users.
        if keys & {"login", "email", "envcare_department_line_ids"}:
            protected = self.filtered(
                lambda u: u != env_user
                and (u.sudo().has_group(IT_GROUP) or u.sudo().has_group("base.group_erp_manager"))
            )
            if protected:
                raise AccessError(_("Only IT can change the email, departments or roles of IT / admin users."))

    # ---------------- sync helpers ----------------
    def _envcare_after_department_change(self):
        """Called by the Department / Role lines on any change."""
        if self.env.context.get("envcare_skip_sync"):
            return
        self._envcare_sync_groups()
        self._envcare_onboard()

    def _envcare_onboard(self):
        """Give a Sr No the first time a user joins a department."""
        for user in self.sudo():
            if user.envcare_department_line_ids and not user.envcare_sr_no:
                user.envcare_sr_no = self.env["ir.sequence"].sudo().next_by_code("envcare.sevak")

    def _envcare_sync_groups(self):
        """Departments / Roles -> security groups."""
        role_groups = self.env["envcare.hr.department.role"].sudo().search([]).group_id
        base_group = self.env.ref("environmental_care.group_envcare_user")
        for user in self.sudo().with_context(envcare_skip_sync=True):
            wanted = user.envcare_department_line_ids.role_id.group_id
            keep = wanted | wanted.trans_implied_ids
            commands = [Command.unlink(g.id) for g in (role_groups & user.groups_id) - keep]
            if user.envcare_department_line_ids:
                commands.append(Command.link(base_group.id))
            commands += [Command.link(g.id) for g in wanted - user.groups_id]
            if commands:
                user.write({"groups_id": commands})

    def _envcare_sync_role_from_groups(self):
        """Security groups -> Departments / Roles.
        For each department, picks the most specific role the user's groups
        give them (IT Head over IT Sevak). Departments without a role are
        kept as they are; a role whose group was removed is cleared."""
        roles = self.env["envcare.hr.department.role"].sudo().search([])
        Line = self.env["envcare.hr.user.department"].sudo().with_context(envcare_skip_sync=True)
        for user in self.sudo():
            held = roles.filtered(lambda r: r.group_id in user.groups_id)
            best = held.filtered(
                lambda r: not any(r.group_id in o.group_id.trans_implied_ids for o in held if o != r)
            )
            best_by_dept = {}
            for role in best.sorted("sequence"):
                best_by_dept[role.department_id] = role  # higher sequence wins
            for line in user.envcare_department_line_ids.with_context(envcare_skip_sync=True):
                role = best_by_dept.pop(line.department_id, False)
                if role and line.role_id != role:
                    line.write({"role_id": role.id})
                elif not role and line.role_id:
                    line.write({"role_id": False})
            if best_by_dept:
                Line.create([
                    {"user_id": user.id, "department_id": dept.id, "role_id": role.id}
                    for dept, role in best_by_dept.items()
                ])
        self._envcare_onboard()

    @api.model
    def _envcare_sync_all_from_groups(self):
        """Run on module install / upgrade: fill Departments / Roles
        for users whose groups were set before (or outside) the HR form."""
        self.sudo().with_context(active_test=False).search([("share", "=", False)])._envcare_sync_role_from_groups()


class ResGroups(models.Model):
    _inherit = "res.groups"

    def write(self, vals):
        # Users added / removed from a group's "Users" tab
        if "users" not in vals or self.env.context.get("envcare_skip_sync"):
            return super().write(vals)
        before = self.sudo().users
        res = super().write(vals)
        (before | self.sudo().users)._envcare_sync_role_from_groups()
        return res