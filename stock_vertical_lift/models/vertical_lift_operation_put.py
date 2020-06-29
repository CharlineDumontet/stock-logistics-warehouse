# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.osv.expression import AND


class VerticalLiftOperationPut(models.Model):
    _name = "vertical.lift.operation.put"
    _inherit = "vertical.lift.operation.transfer"
    _description = "Vertical Lift Operation Put"

    _initial_state = "scan_source"

    def _selection_states(self):
        return [
            ("scan_source", "Scan a package, product or lot to put-away"),
            ("scan_tray_type", "Scan Tray Type"),
            ("save", "Put goods in tray and save"),
            ("release", "Release"),
        ]

    def _transitions(self):
        return (
            self.Transition(
                "scan_source",
                "scan_tray_type",
                # transition only if a move line has been selected
                # (by on_barcode_scanner)
                lambda self: self.current_move_line_id,
            ),
            self.Transition("scan_tray_type", "save"),
            self.Transition("save", "release", lambda self: self.process_current()),
            self.Transition(
                "release", "scan_source", lambda self: self.clear_current_move_line()
            ),
        )

    def _domain_move_lines_to_do(self):
        domain = [
            ("state", "in", ("assigned", "partially_available")),
            ("location_dest_id", "child_of", self.location_id.id),
        ]
        return domain

    def _domain_move_lines_to_do_all(self):
        shuttle_locations = self.env["stock.location"].search(
            [("vertical_lift_kind", "=", "view")]
        )
        domain = [
            ("state", "in", ("assigned", "partially_available")),
            ("location_dest_id", "child_of", shuttle_locations.ids),
        ]
        return domain

    def on_barcode_scanned(self, barcode):
        self.ensure_one()
        if self.step() == "scan_source":
            line = self._find_move_line(barcode)
            if line:
                self.current_move_line_id = line
                self.next_step()
            else:
                self.env.user.notify_warning(
                    _("No move line found for barcode {}").format(barcode)
                )

        # TODO if the move line already has a storage type, assign directly a
        # destination and save

        elif self.step() == "scan_tray_type":
            tray_type = self._find_tray_type(barcode)
            if tray_type:
                if self._assign_available_cell(tray_type):
                    self.fetch_tray()
                    self.next_step()
                else:
                    self.env.user.notify_warning(
                        _("No free space for this tray type in this shuttle.")
                    )
            else:
                self.env.user.notify_warning(
                    _("No tray type found for barcode {}").format(barcode)
                )

    def _find_tray_type(self, barcode):
        return self.env["stock.location.tray.type"].search(
            [("code", "=", barcode)], limit=1
        )

    def _find_move_line(self, barcode):
        package = self.env["stock.quant.package"].search([("name", "=", barcode)])
        if package:
            return self._find_move_line_for_package(package)

        lot = self.env["stock.production.lot"].search([("name", "=", barcode)])
        if lot:
            return self._find_move_line_for_lot(package)

        product = self.env["product.product"].search([("barcode", "=", barcode)])
        if not product:
            packaging = self.env["product.packaging"].search(
                [("product_id", "!=", False), ("barcode", "=", barcode)]
            )
            product = packaging.product_id
        if product:
            return self._find_move_line_for_product(product)

    def _find_move_line_for_package(self, package):
        domain = AND(
            [self._domain_move_lines_to_do_all(), [("package_id", "=", package.id)]]
        )
        return self.env["stock.move.line"].search(domain, limit=1)

    def _find_move_line_for_lot(self, lot):
        domain = AND(
            [
                self._domain_move_lines_to_do_all(),
                [
                    ("lot_id", "=", lot.id),
                    # if the lot is in a package, the package must be scanned
                    ("package_id", "=", False),
                ],
            ]
        )
        return self.env["stock.move.line"].search(domain, limit=1)

    def _find_move_line_for_product(self, product):
        domain = AND(
            [
                self._domain_move_lines_to_do_all(),
                [
                    ("product_id", "=", product.id),
                    # if the lot is in a package, the package must be scanned
                    ("package_id", "=", False),
                ],
            ]
        )
        return self.env["stock.move.line"].search(domain, limit=1)

    def _check_tray_type(self, barcode):
        location = self.current_move_line_id.location_dest_id
        tray_type = location.cell_in_tray_type_id
        return barcode == tray_type.code

    def _assign_available_cell(self, tray_type):
        locations = self.env["stock.location"].search(
            [
                ("id", "child_of", self.location_id.id),
                ("cell_in_tray_type_id", "=", tray_type.id),
            ]
        )
        location = fields.first(
            locations.filtered(lambda loc: not loc.tray_cell_contains_stock)
        )
        if location:
            self.current_move_line_id.location_dest_id = location
            return True
        return False

    def fetch_tray(self):
        self.current_move_line_id.fetch_vertical_lift_tray_dest()
