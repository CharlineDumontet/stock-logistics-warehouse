# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.osv import expression
from odoo.tools.float_utils import float_compare


def _default_sequence(record):
    maxrule = record.search([], order="sequence desc", limit=1)
    if maxrule:
        return maxrule.sequence + 10
    else:
        return 0


class StockReserveRule(models.Model):
    """Rules for stock reservations

    Each rule can have many removal rules, they configure the conditions and
    advanced removal strategies to apply on a specific location (sub-location
    of the rule).

    The rules are selected for a move based on their source location and a
    configurable domain on the rule.
    """

    _name = "stock.reserve.rule"
    _description = "Stock Reservation Rule"
    _order = "sequence, id"

    name = fields.Char(string="Description", required=True)
    sequence = fields.Integer(default=lambda s: _default_sequence(s))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.user.company_id.id,
    )

    location_id = fields.Many2one(comodel_name="stock.location", required=True)
    fallback_location_id = fields.Many2one(
        comodel_name="stock.location",
        help="If all removal rules are exhausted, try to reserve in this "
        "location. When empty, the fallback happens in any of the move's "
        "source sub-locations.",
    )

    rule_removal_ids = fields.One2many(
        comodel_name="stock.reserve.rule.removal", inverse_name="rule_id"
    )

    rule_domain = fields.Char(
        string="Rule Domain",
        default=[],
        help="Domain based on Stock Moves, to define if the "
        "rule is applicable or not.",
    )

    def _rules_for_location(self, location):
        return self.search([("location_id", "parent_of", location.id)])

    def _eval_rule_domain(self, move, domain):
        move_domain = [("id", "=", move.id)]
        # Warning: if we build a domain with dotted path such
        # as group_id.is_urgent (hypothetic field), can become very
        # slow as odoo searches all "procurement.group.is_urgent" first
        # then uses "IN group_ids" on the stock move only.
        # In such situations, it can be better either to add a related
        # field on the stock.move, either extend _eval_rule_domain to
        # add your own logic (based on SQL, ...).
        return bool(
            self.env["stock.move"].search(
                expression.AND([move_domain, domain]), limit=1
            )
        )

    def _is_rule_applicable(self, move):
        domain = safe_eval(self.rule_domain) or []
        if domain:
            return self._eval_rule_domain(move, domain)
        return True


class StockReserveRuleRemoval(models.Model):
    """Rules for stock reservations removal

    A removal rule does:

    * Filter quants that a removal rule can reserve for the location
      (_filter_quants)
    * An advanced removal strategy for the preselected quants (_apply_strategy)

    New advanced removal strategies can be added by other modules, see the
    method ``_apply_strategy`` and the default methods for more documentation
    about their contract.
    """

    _name = "stock.reserve.rule.removal"
    _description = "Stock Reservation Rule Removal"
    _order = "sequence, id"

    rule_id = fields.Many2one(
        comodel_name="stock.reserve.rule", required=True, ondelete="cascade"
    )
    name = fields.Char(string="Description")
    location_id = fields.Many2one(comodel_name="stock.location", required=True)

    sequence = fields.Integer(default=lambda s: _default_sequence(s))

    # quants exclusion
    quant_domain = fields.Char(
        string="Quants Domain",
        default=[],
        help="Filter Quants allowed to be reserved for this location "
        "and sub-locations.",
    )

    # advanced removal strategy
    removal_strategy = fields.Selection(
        string="Advanced Removal Strategy",
        selection=[
            ("default", "Default Removal Strategy"),
            ("empty_bin", "Empty Bins"),
            ("packaging", "Prefer Full Packaging"),
        ],
        required=True,
        default="default",
    )

    def _eval_quant_domain(self, quants, domain):
        quant_domain = [("id", "in", quants.ids)]
        return self.env["stock.quant"].search(
            expression.AND([quant_domain, domain])
        )

    def _filter_quants(self, move, quants):
        domain = safe_eval(self.quant_domain) or []
        if domain:
            return self._eval_quant_domain(quants, domain)
        return quants

    def _apply_strategy(self, quants):
        """Apply the advanced removal strategy

        New methods can be added by:

        - Adding a selection in the 'removal_strategy' field.
        - adding a method named after the selection value
          (_apply_strategy_SELECTION)

        A strategy has to comply with this signature: (self, quants)
        Where 'self' is the current rule and 'quants' are the candidate
        quants allowed for the rule, sorted by the company's removal
        strategy (fifo, fefo, ...).
        It has to get the initial need using 'need = yield' once, then,
        each time the strategy decides to take quantities in a location,
        it has to yield and retrieve the remaining needed using:

            need = yield location, location_quantity, quantity_to_take

        See '_apply_strategy_default' for a short example.

        """
        method_name = "_apply_strategy_%s" % (self.removal_strategy)
        yield from getattr(self, method_name)(quants)

    def _apply_strategy_default(self, quants):
        need = yield
        # Propose quants in the same order than returned originally by
        # the _gather method, so based on fifo, fefo, ...
        for quant in quants:
            need = yield (
                quant.location_id,
                quant.quantity - quant.reserved_quantity,
                need,
            )

    def _apply_strategy_empty_bin(self, quants):
        need = yield
        # Group by location (in this removal strategies, we want to consider
        # the total quantity held in a location).
        quants_per_bin = quants._group_by_location()

        # Sort by min quant first so we empty as most bins as we
        # can. But keep the original ordering for equal quantities!
        bins = sorted(
            [
                (
                    sum(quants.mapped("quantity"))
                    - sum(quants.mapped("reserved_quantity")),
                    quants,
                    location,
                )
                for location, quants in quants_per_bin
            ]
        )

        # Propose the smallest quants first, so we can empty as most bins
        # as possible.
        rounding = fields.first(quants).product_id.uom_id.rounding
        for location_quantity, quants, location in bins:
            if location_quantity <= 0:
                continue

            if float_compare(need, location_quantity, rounding) != -1:
                need = yield location, location_quantity, need

    def _apply_strategy_packaging(self, quants):
        need = yield
        # Group by location (in this removal strategies, we want to consider
        # the total quantity held in a location).
        quants_per_bin = quants._group_by_location()

        product = fields.first(quants).product_id

        # we'll walk the packagings from largest to smallest to have the
        # largest containers as possible (1 pallet rather than 10 boxes)
        packaging_quantities = sorted(
            product.packaging_ids.mapped("qty"), reverse=True
        )

        rounding = product.uom_id.rounding

        def is_greater_eq(value, other):
            return (
                float_compare(value, other, precision_rounding=rounding) >= 0
            )

        for pack_quantity in packaging_quantities:
            # Get quants quantity on each loop because they may change.
            # Sort by max quant first so we have more chance to take a full
            # package. But keep the original ordering for equal quantities!
            bins = sorted(
                [
                    (
                        sum(quants.mapped("quantity"))
                        - sum(quants.mapped("reserved_quantity")),
                        quants,
                        location,
                    )
                    for location, quants in quants_per_bin
                ],
                reverse=True,
            )

            for location_quantity, quants, location in bins:
                if location_quantity <= 0:
                    continue
                enough_for_packaging = is_greater_eq(
                    location_quantity, pack_quantity
                )
                asked_more_than_packaging = is_greater_eq(need, pack_quantity)
                if enough_for_packaging and asked_more_than_packaging:
                    # compute how much packaging we can get
                    take = (need // pack_quantity) * pack_quantity
                    need = yield location, location_quantity, take
