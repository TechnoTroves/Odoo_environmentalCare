from odoo import models


class EnvCareChatterMixin(models.AbstractModel):
    """Shared behaviour for records that have a chatter on the website
    (events, workshops, ...). Add it to `_inherit` next to mail.thread.

    Each model implements the three hooks at the bottom."""
    _name = "envcare.chatter.mixin"
    _description = "Environmental Care Website Chatter"

    # Anyone who can READ the record may use its chatter (log notes,
    # messages, activities). Who may *send* a message is checked by
    # _envcare_can_manage_chatter().
    _mail_post_access = "read"

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        """Website chatter: when the context lists the partners to notify
        (owner + sender + chosen receivers), notify ONLY them - not the
        followers - and always by e-mail (most users have no backend inbox)."""
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        listed = self.env.context.get("envcare_notify_partner_ids")
        if listed is None:
            return recipients
        listed = set(listed)
        return [dict(r, notif="email") for r in recipients if r["id"] in listed]

    def _get_access_action(self, access_uid=None, force_website=False):
        """Links in e-mails open the website page for everyone except
        IT / Admin, who have the backend."""
        self.ensure_one()
        user = self.env["res.users"].sudo().browse(access_uid) if access_uid else self.env.user
        if not (user.has_group("base.group_system") or user.has_group("environmental_care.group_envcare_it")):
            return {
                "type": "ir.actions.act_url",
                "url": self._envcare_website_url(),
                "target": "self",
                "target_type": "public",
                "res_id": self.id,
            }
        return super()._get_access_action(access_uid=access_uid, force_website=force_website)

    # ---------------- hooks for each model ----------------
    def _envcare_website_url(self):
        """Website page of this record, e.g. /event/5."""
        raise NotImplementedError()

    def _envcare_chatter_owner(self):
        """res.users (one or more) always e-mailed by Log note / Send message."""
        raise NotImplementedError()

    def _envcare_can_manage_chatter(self):
        """True if the current user may Send message and mark any activity done."""
        raise NotImplementedError()