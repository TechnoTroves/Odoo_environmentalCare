"""Helpers shared by all Environmental Care website controllers."""
import base64
import re
from datetime import datetime, timedelta

import pytz

from odoo import Command
from odoo.exceptions import ValidationError
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

    # ---------- attachments (template: environmental_care.attachment_input) ----------
    def _attachment_commands(self, record, name, field):
        """Many2many ir.attachment field `field` of `record` from the form:
        files uploaded in <input type="file" name="{name}"> are added, ticked
        "{name}_remove" checkboxes are removed. Returns the commands (or [])."""
        form = request.httprequest.form
        current = set(record[field].ids)
        remove_ids = {int(x) for x in form.getlist(f"{name}_remove") if x.isdigit()} & current
        commands = [Command.unlink(att_id) for att_id in remove_ids]
        for upload in request.httprequest.files.getlist(name):
            if not (upload and upload.filename):
                continue
            attachment = request.env["ir.attachment"].create({
                "name": upload.filename,
                "datas": base64.b64encode(upload.read()),
                "res_model": record._name,
                "res_id": record.id,
            })
            commands.append(Command.link(attachment.id))
        return commands

    def _save_attachments(self, record, fields):
        """Several attachment fields at once; input name = field name."""
        vals = {}
        for field in fields:
            commands = self._attachment_commands(record, field, field)
            if commands:
                vals[field] = commands
        if vals:
            record.write(vals)

    # ---------- line tables (template: environmental_care.line_table, flag allow_edit) ----------
    # A line table edits a One2many on the website. Column spec (dicts):
    #   name     field name on the line model
    #   label    column title
    #   type     char | url | text | int | float | m2o | m2m | bool | files
    #   options  key into the `options` dict (m2o / m2m): list of (id_str, label)
    #   required True -> every row needs it
    #   width    min width in px (optional)
    # Input names: existing row  {key}_{id}_{field}
    #              new row       {key}_new{n}_{field}  (n given by row_editor.js)
    #              row marker    {prefix}row  (only posted when the row is editable)
    def _line_rows(self, lines, columns):
        """Existing lines -> row dicts for the template."""
        rows = []
        for line in lines:
            row = {"id": line.id}
            for col in columns:
                name, ctype = col["name"], col["type"]
                value = line[name]
                if ctype == "m2o":
                    row[name] = str(value.id or "")
                    row[f"{name}_label"] = value.display_name or ""
                elif ctype == "m2m":
                    row[name] = [str(i) for i in value.ids]
                    row[f"{name}_labels"] = value.mapped("display_name")
                elif ctype in ("char", "url", "text"):
                    row[name] = value or ""
                else:  # int, float, bool, files
                    row[name] = value
            rows.append(row)
        return rows

    def _new_line_indexes(self, key):
        pattern = re.compile(rf"^{re.escape(key)}_new(\d+)_row$")
        found = [int(m.group(1)) for m in map(pattern.match, request.httprequest.form.keys()) if m]
        return sorted(set(found))

    def _posted_new_line_rows(self, key, columns):
        """New rows as typed (to show them again after an error)."""
        form = request.httprequest.form
        rows = []
        for index in self._new_line_indexes(key):
            prefix = f"{key}_new{index}_"
            row = {"index": index}
            for col in columns:
                name = col["name"]
                if col["type"] == "m2m":
                    row[name] = form.getlist(prefix + name)
                elif col["type"] == "bool":
                    row[name] = bool(form.get(prefix + name))
                elif col["type"] != "files":
                    row[name] = form.get(prefix + name) or ""
            rows.append(row)
        return rows

    def _line_vals(self, prefix, columns, allowed, table_label):
        """One posted row -> (vals, has_content). `allowed`: option key -> set of ids."""
        form = request.httprequest.form
        vals, has_content = {}, False
        for col in columns:
            name, ctype, label = col["name"], col["type"], col["label"]
            raw = form.get(prefix + name)
            if ctype == "files":
                has_content |= any(f and f.filename for f in request.httprequest.files.getlist(prefix + name))
                continue
            if ctype in ("char", "url", "text"):
                value = (raw or "").strip()
            elif ctype == "int":
                try:
                    value = int(raw) if (raw or "").strip() else 0
                except ValueError:
                    raise ValidationError(f"{table_label}: {label} must be a whole number.")
            elif ctype == "float":
                try:
                    value = float(raw) if (raw or "").strip() else 0.0
                except ValueError:
                    raise ValidationError(f"{table_label}: {label} must be a number.")
            elif ctype == "m2o":
                ok = allowed.get(col.get("options"), set())
                value = int(raw) if (raw or "").isdigit() and int(raw) in ok else False
            elif ctype == "m2m":
                ok = allowed.get(col.get("options"), set())
                value = [int(x) for x in form.getlist(prefix + name) if x.isdigit() and int(x) in ok]
            elif ctype == "bool":
                value = bool(raw)
            else:
                continue
            has_content |= bool(value)
            vals[name] = value
        return vals, has_content

    def _save_line_table(self, parent, key, field, columns, allowed, table_label, can_delete):
        """Create / update / delete the lines of parent[field] from the form.
        Rows not posted (read-only) are left alone. Files are added after the
        line exists (attachments need the line's id)."""
        form = request.httprequest.form
        Line = parent[field].browse()
        inverse = parent._fields[field].inverse_name
        file_cols = [col["name"] for col in columns if col["type"] == "files"]

        def _check_required(vals):
            for col in columns:
                if col.get("required") and not vals.get(col["name"]):
                    raise ValidationError(f"{table_label}: every row needs {col['label']}.")

        def _to_write(vals):
            return {k: (Command.set(v) if isinstance(v, list) else v) for k, v in vals.items()}

        for line in parent[field]:
            prefix = f"{key}_{line.id}_"
            if f"{prefix}row" not in form:
                continue
            if can_delete and form.get(f"{prefix}delete"):
                line.unlink()
                continue
            vals, _content = self._line_vals(prefix, columns, allowed, table_label)
            _check_required(vals)
            changed = {}
            for name, value in vals.items():
                current = line[name]
                if line._fields[name].type == "many2one":
                    current = current.id or False
                elif line._fields[name].type == "many2many":
                    current, value = sorted(current.ids), sorted(value)
                elif line._fields[name].type in ("char", "text", "html"):
                    current = current or ""
                if current != value:
                    changed[name] = vals[name]
            if changed:
                line.write(_to_write(changed))
            for name in file_cols:
                commands = self._attachment_commands(line, prefix + name, name)
                if commands:
                    line.write({name: commands})

        for index in self._new_line_indexes(key):
            prefix = f"{key}_new{index}_"
            vals, has_content = self._line_vals(prefix, columns, allowed, table_label)
            if not has_content:
                continue  # empty row
            _check_required(vals)
            line = Line.create(dict(_to_write(vals), **{inverse: parent.id}))
            for name in file_cols:
                commands = self._attachment_commands(line, prefix + name, name)
                if commands:
                    line.write({name: commands})

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