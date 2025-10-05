# -*- coding: utf-8 -*-

from odoo import models, fields, api


class Partner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner']

    import_bill_account_id = fields.Many2one('account.account', 
                                            company_dependent=True,
                                            string='Import Expense Account',
                                            domain=[('deprecated', '=', False)],
                                            help='Assign a spending account to each line')