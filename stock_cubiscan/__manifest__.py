# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    'name': 'Stock Cubiscan',
    'summary': 'Implement inteface with Cubiscan devices for packaging',
    'version': '12.0.1.0.0',
    'category': 'Stock',
    'author': 'Camptocamp',
    'license': 'AGPL-3',
    'depends': [
        'barcodes',
        'stock',
        'web_tree_dynamic_colored_field'
    ],
    'website': 'http://www.camptocamp.com',
    'data': [
        'views/assets.xml',
        'views/cubiscan_view.xml',
        'views/product_packaging_views.xml',
        'wizard/cubiscan_wizard.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
}
