# Copyright 2025 Foodles (https://www.foodles.co/).
# @author Stéphane Mangin <stephane.mangin@webmel.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def get_stock_quant_history(self):
        """Get the last stock quant history related to this picking.
        :return: stock.quant.history recordset"""
        self.ensure_one()
        history_model = self.env["stock.quant.history"]
        domain = [
            ("inventory_date", ">=", max(self.date_done, self.date)),
            ("product_id", "in", self.move_line_ids.mapped("product_id").ids),
            ("lot_id", "in", self.move_line_ids.mapped("lot_id").ids),
        ]
        return history_model.search(domain)

    def action_toggle_is_locked(self):
        # Ensure the picking is allowed to be unlocked before toggling the lock status.
        self.check_unlock_allowed()
        return super().action_toggle_is_locked()

    def check_unlock_allowed(self):
        """Check if the picking can be unlocked.
        :return: True if the picking can be unlocked
        :raises ValidationError: if not allowed to unlock"""
        separator = "\n - "
        self.ensure_one()
        if self.is_locked:
            history_lines = self.get_stock_quant_history()
            if history_lines.exists():
                snapshot_text = separator.join(
                    history_lines.mapped("snapshot_id").mapped("display_name")
                )
                raise ValidationError(
                    _("You cannot unlock '%s' as stock histories exists:%s%s.")
                    % (self.display_name, separator, snapshot_text)
                )
        return True

    def write(self, vals):
        # Constraint the lock status to avoid unlocking a record when a related quant
        # history exists.
        # An unlock action is propagated
        if "is_locked" in vals and not vals.get("is_locked"):
            # Reducing to locked status and done picking
            for picking in self.filtered(
                lambda pick: pick.is_locked and pick.state == "done"
            ):
                picking.check_unlock_allowed()
        return super().write(vals)
