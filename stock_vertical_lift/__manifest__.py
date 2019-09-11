# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    'name': 'Vertical Lift',
    'summary': 'Provides the core for integration with Vertical Lifts',
    'version': '12.0.1.0.0',
    'category': 'Stock',
    'author': 'Camptocamp, Odoo Community Association (OCA)',
    'license': 'AGPL-3',
    'depends': [
        'stock',
        'barcodes',
        'base_sparse_field',
        'web_notify',  # OCA/web
    ],
    'website': 'https://www.camptocamp.com',
    'demo': [
        'demo/stock_location_demo.xml',
        'demo/vertical_lift_shuttle_demo.xml',
        'demo/product_demo.xml',
        'demo/stock_inventory_demo.xml',
        'demo/stock_picking_demo.xml',
    ],
    'data': [
        'views/stock_location_views.xml',
        'views/vertical_lift_shuttle_views.xml',
        'views/vertical_lift_tray_type_views.xml',
        'views/stock_vertical_lift_templates.xml',
        'views/shuttle_screen_templates.xml',
        'data/stock_location.xml',
        'data/vertical_lift_tray_type.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'development_status': 'Alpha',
}
