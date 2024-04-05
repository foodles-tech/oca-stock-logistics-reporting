# Copyright 2023-2024 Foodles (https://www.foodles.co/).
# @author Pierre Verkest <pierreverkest84@gmail.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.osv.expression import AND


class DefaultDict(defaultdict):
    def __missing__(self, key):
        self[key] = self.default_factory(*key)
        return self[key]


class StockQuantHistorySnapshot(models.Model):
    _name = "stock.quant.history.snapshot"
    _description = "stock.quant.history generation configuration model"
    _order = "inventory_date desc"

    name = fields.Char(
        compute="_compute_name",
    )
    stock_quant_history_ids = fields.One2many(
        comodel_name="stock.quant.history",
        inverse_name="snapshot_id",
        string="Stock quant history",
        help="Generated stock quant history for current snapshot settings.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("generated", "Generated"),
        ],
        string="Status",
        copy=False,
        default="draft",
        readonly=True,
        required=True,
    )

    inventory_date = fields.Datetime(
        string="Inventory date",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        help="The date used to create stock.quant.history as it was for the given date",
    )
    generated_date = fields.Datetime(
        string="Generated date",
        readonly=True,
        copy=False,
        help="Date when stock.quant.history line have been created.",
    )
    previous_snapshot_id = fields.Many2one(
        comodel_name="stock.quant.history.snapshot",
        string="Snapshot base",
        readonly=True,
        help="Base snapshot used to generate this snapshot",
    )

    @api.depends("inventory_date")
    def _compute_name(self):
        # Odoo enforce users to be linked to an active lang
        lang = self.env["res.lang"]._lang_get(self.env.user.lang)
        dt_format = lang.date_format + " " + lang.time_format

        for rec in self:
            rec.name = _("Snapshot %s") % (rec.inventory_date.strftime(dt_format))

    def action_generate_stock_quant_history(self):
        for snapshot in self:
            snapshot._generate_stock_quant_history()

    def _prepare_stock_move_line_filter(self, previous_quant_snapshot):
        domain = [
            ("state", "=", "done"),
            ("date", "<=", self.inventory_date),
        ]
        if previous_quant_snapshot.exists():
            domain = AND(
                [domain, [("date", ">", previous_quant_snapshot.inventory_date)]]
            )

        return domain

    def _generate_stock_quant_history(self):
        self.ensure_one()
        self.generated_date = fields.Datetime.now()
        previous_quant_snapshot = self.search(
            [
                ("state", "=", "generated"),
                ("inventory_date", "<=", self.inventory_date),
            ],
            order="inventory_date desc",
            limit=1,
        )
        quant_history = DefaultDict(
            lambda product, lot, location: self.env["stock.quant.history"]
            .sudo()
            .create(
                {
                    "snapshot_id": self.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "location_id": location.id,
                    "quantity": 0,
                }
            )
        )

        self.previous_snapshot_id = previous_quant_snapshot
        if previous_quant_snapshot.stock_quant_history_ids.exists():
            current_snapshot_quants = (
                previous_quant_snapshot.stock_quant_history_ids.sudo().copy_multi(
                    {"snapshot_id": self.id}
                )
            )
            for current_quant_history in current_snapshot_quants:
                quant_history[
                    (
                        current_quant_history.product_id,
                        current_quant_history.lot_id,
                        current_quant_history.location_id,
                    )
                ] = current_quant_history
        for move_line in (
            self.env["stock.move.line"]
            .sudo()
            .search(
                self._prepare_stock_move_line_filter(previous_quant_snapshot),
            )
        ):
            quant_history[
                (move_line.product_id, move_line.lot_id, move_line.location_id)
            ].quantity -= move_line.qty_done
            quant_history[
                (move_line.product_id, move_line.lot_id, move_line.location_dest_id)
            ].quantity += move_line.qty_done

        # remove line with zero to save same disk space
        for quant in quant_history.values():
            if quant.quantity == 0:
                quant.unlink()

        self.state = "generated"

    def action_related_stock_quant_history_tree_view(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock_quant_history.action_stock_quant_history"
        )
        action["domain"] = [("snapshot_id", "in", self.ids)]
        return action
