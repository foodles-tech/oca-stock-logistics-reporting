# Copyright 2025 Foodles (https://www.foodles.co/).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).


from freezegun import freeze_time
from setuptools.config._validate_pyproject import ValidationError

from odoo.tests import tagged, users

from . import common


@tagged("post_install", "-at_install")
@freeze_time("2022-06-01 12:00+00")
class TestStockPickingLock(common.TestStockQuantHistoryCommon):
    """Test the lock constraint functionality on picking.
          ┌────────────────────────┐
          │(unlock, no history) TC3│
          ▼                        │
    ┌───────────┐            ┌─────┴─────┐
    │ Unlocked  ├───────────►│  Locked   │
    └───────────┘ (lock) TC1 └─────┬─────┘
                                   │
    (unlock, history exists) TC2   ▼
                             ┌───────────┐
                             │ Exception │
                             └───────────┘
    """

    def setUp(self):
        super().setUp()
        customer_location = self.env.ref("stock.stock_location_customers")
        # prepare a snapshot
        self.picking = self.env["stock.picking"].create(
            {
                "name": "Test Picking",
                "picking_type_id": self.env.ref("stock.picking_type_out").id,
                "location_id": self.location.id,
                "location_dest_id": customer_location.id,
                "is_locked": False,
            }
        )
        self.move_line = self.env["stock.move.line"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "location_dest_id": customer_location.id,
                "picking_id": self.picking.id,
                "product_uom_id": self.product.uom_id.id,
                "product_uom_qty": 1,
                "lot_id": self.lot.id,
            }
        )

    @users("stock_manager")
    def test1__lock_unlock_without_history(self):
        """Test the lock functionality."""
        # Assign and confirm the picking to be locked
        self.picking.action_assign()
        self.picking.action_confirm()
        # This picking should be unlocked (no changes on standard behavior)
        self.picking.write({"is_locked": True})
        self.assertTrue(self.picking.is_locked, "The picking should be locked.")

    @users("stock_manager")
    def test2_unlock_with_history(self):
        """Test the unlock functionality with history."""
        # Validate and finish the picking to be locked
        self.picking.action_assign()
        self.picking.action_confirm()
        self.picking.write({"is_locked": True})
        self.assertTrue(self.picking.is_locked, "The picking should be locked.")
        # Create a snapshot including this picking
        self.stock_history_now.action_generate_stock_quant_history()
        # Try to unlock the picking
        with self.assertRaises(
            ValidationError,
            msg="You cannot unlock this picking as a related quant history exists.",
        ):
            self.picking.write({"is_locked": False})

    @users("stock_manager")
    def test3_unlock_with_past_history(self):
        """Test the unlock functionality without history."""
        # Create a snapshot before confirming the picking
        self.stock_history_now.action_generate_stock_quant_history()
        self.assertIn(
            self.lot,
            self.stock_history_now.stock_quant_history_ids.mapped("lot_id"),
            "The snapshot should have the lot of the move line.",
        )
        # Validate and finish the picking to be locked
        self.picking.action_assign()
        self.picking.action_confirm()
        self.picking.write({"is_locked": True})
        self.assertTrue(self.picking.is_locked, "The picking should be locked.")
        # This picking should be unlocked (no changes on standard behavior)
        self.picking.write({"is_locked": False})
        self.assertFalse(
            self.picking.is_locked, "The picking should be unlocked after toggling."
        )
