# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'CR Import Vendor Bills',
    'version': '12.0.1.0.1',
    'category': 'Vendor Bills',
    'author': 'CR FACTURA',
    'license': 'AGPL-3',
    'website': 'http://www.crfactura.com/',
    'summary': 'Import Vendor Bills from incoming mail server',

    'description': """
        
    """,

    # any module necessary for this one to work correctly
    'depends': ['cr_electronic_invoice', 'fetchmail'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'data/import_vendor_cron.xml',
        'data/import_other_charges_cron.xml',
        'views/res_partner_view.xml',
        'views/res_company_views.xml',
        'views/account_view.xml',
        'views/account_invoice_view.xml',
        'wizard/cr_multiple_invoice_validation_wz_view.xml',
    ]
    ,
}
