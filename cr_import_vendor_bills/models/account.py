# © 2011 Guewen Baconnier (Camptocamp)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).-
from odoo import models, fields, api, _
from . import api_import_mail
from odoo.addons import decimal_precision as dp

import logging
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    from_mail = fields.Boolean(
        'Desde email',
        help="If flagged, some fields of the invoice "
             "they will be read only ")

    has_ack = fields.Boolean(
        'Tiene ACK?',
        help="If flagged, indicates you have the "
             "answer (ACK) attached ")

    iva_condition = fields.Selection([
        ('gecr', 'Generate IVA credit'),
        ('crpa', 'Generates partial IVA credit'),
        ('bica', 'Capital assets'),
        ('gcnc', 'Current spending does not generate credit'),
        ('prop', 'Proportionality')],
        string='IVA Condition',
        required=False,
        default='gecr',
    )

    company_activity_id = fields.Many2one("economic.activity", string="Default economic activity", required=False,
                                  context={'active_test': False})

    def load_xml_invoice_tax_lines(self, inv_type=['in_invoice'], from_date='2022-07-01', to_date='2022-07-31'):
        res_companies_ids = self.env['res.company'].sudo().search([])
        for company in res_companies_ids:
            invoice_ids = self.env['account.invoice'].search([
                ('company_id', '=', company.id), ('state', '=', 'draft'), ('xml_supplier_approval', '!=', False),
                ('type', 'in', inv_type), ('date_invoice', '>=', from_date), ('date_invoice', '<=', to_date)
            ])
            count = len(invoice_ids.ids)
            for inv in invoice_ids:
                _logger.info('\n count \n %s \n', (count))
                inv.invoice_line_ids.unlink()
                api_import_mail.load_xml_data_from_mail(inv, True, inv.company_id.import_bill_account_id,
                                                                    inv.company_id.import_bill_product_id,
                                                                    inv.company_id.import_bill_account_analytic_id)
                count -= 1

    # @api.multi
    # def get_taxes_values(self):
    #     tax_grouped = {}
    #     round_curr = self.currency_id.round
    #     dict_lines = self._context.get('dict_lines', {}) or {}
    #     # _logger.info('\nget_taxes_valuesget_taxes_valuesget_taxes_values\n %r \n\n', dict_lines)
    #     for line in self.invoice_line_ids:
    #         if not line.account_id or line.display_type:
    #             continue
    #         dict_line = dict_lines.get(line.id)
    #         price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
    #         taxes = line.invoice_line_tax_ids.with_context(dict_line=dict_line)\
    #             .compute_all(price_unit, self.currency_id, line.quantity, line.product_id, self.partner_id)['taxes']

    #         # _logger.info('\n  taxes taxes taxes \n %r \n\n', taxes)

    #         for tax in taxes:
    #             val = self._prepare_tax_line_vals(line, tax)
    #             key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)
    #             if key not in tax_grouped:
    #                 tax_grouped[key] = val
    #                 tax_grouped[key]['base'] = round_curr(val['base'])
    #             else:
    #                 tax_grouped[key]['amount'] += val['amount']
    #                 tax_grouped[key]['base'] += round_curr(val['base'])
    #     return tax_grouped

 

    def load_invoice_other_charges(self, inv_ids=[], inv_type=['in_invoice'], from_date='2022-07-01', to_date='2022-07-31'):
        res_companies_ids = self.env['res.company'].sudo().search([])
        for company in res_companies_ids:
            domain = [('company_id', '=', company.id), 
                ('state', '!=', 'cancel'),
                ('type', 'in', inv_type), 
                ('date_invoice', '>=', from_date), ('date_invoice', '<=', to_date)]
            if inv_ids:
                domain = [('id','in', inv_ids)]
            invoice_ids = self.env['account.invoice'].search(domain)
            for inv in invoice_ids.filtered(lambda t:t.amount_total != t.amount_total_electronic_invoice):
                status = inv.state
                if inv.state in ('paid','in_payment','open'):
                    payments = inv.payment_move_line_ids
                    inv.action_invoice_cancel()
                    inv.action_invoice_draft()
                inv.read()

                inv.invoice_line_ids.unlink()
                api_import_mail.load_xml_data_from_mail(inv, True, inv.company_id.import_bill_account_id,
                                                                    inv.company_id.import_bill_product_id,
                                                                    inv.company_id.import_bill_account_analytic_id)
                if status in ('paid','in_payment','open'):
                    inv.action_invoice_open()
                    if payments:
                        inv.register_payment(payments)

    # se hereda la funcion del boton para poder importar facturas y se  utiliza la api del correo y no del boton
    @api.multi
    def load_xml_data(self):
        account = self.company_id.import_bill_account_id
        analytic_account = self.company_id.import_bill_account_analytic_id
        product = self.company_id.import_bill_product_id

        purchase_journal = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
        default_account_id = purchase_journal.expense_account_id.id
        if default_account_id:
            account = self.env['account.account'].search([('id', '=', default_account_id)], limit=1)
            load_lines = purchase_journal.load_lines
        else:
            default_account_id = self.env['ir.config_parameter'].sudo().get_param('expense_account_id')
            load_lines = bool(self.env['ir.config_parameter'].sudo().get_param('load_lines'))
            if default_account_id:
                account = self.env['account.account'].search([('id', '=', default_account_id)], limit=1)

        analytic_account_id = purchase_journal.expense_analytic_account_id.id
        if analytic_account_id:
            analytic_account = self.env['account.analytic.account'].search([('id', '=', analytic_account_id)], limit=1)
        else:
            analytic_account_id = self.env['ir.config_parameter'].sudo().get_param('expense_analytic_account_id')
            if analytic_account_id:
                analytic_account = self.env['account.analytic.account'].search([('id', '=', analytic_account_id)], limit=1)

        product_id = purchase_journal.expense_product_id.id
        if product_id:
            product = self.env['product.product'].search([('id', '=', product_id)], limit=1)
        else:
            product_id = self.env['ir.config_parameter'].sudo().get_param('expense_product_id')
            if product_id:
                product = self.env['product.product'].search([('id', '=', product_id)], limit=1)

        api_import_mail.load_xml_data_from_mail(self, True, account, product, analytic_account)

class AccountTax(models.Model):
    _inherit = 'account.tax'

    # def _compute_amount(self, base_amount, price_unit, quantity=1.0, product=None, partner=None):
    #     dict_line = self._context.get('dict_line', {}) or {}
    #     # if dict_line:
    #     #     _logger.info('\n_compute_amount_compute_amount\n%r\n\n', 
    #     #         [dict_line, 
    #     #             dict_line['taxes'].get(self.id),
    #     #             self.id,
    #     #             self.tax_code,
    #     #             self.tax_code == '99', 
    #     #             float(dict_line.get('price_unit',0.0))])
    #     if dict_line and ( (dict_line['taxes'].get(self.id) and self.tax_code == '99') or (float(dict_line.get('price_unit',0.0)) == 0.0) ):
    #         return dict_line['taxes'][self.id]['amount']

    #     return super(AccountTax, self)._compute_amount(
    #         base_amount=base_amount, price_unit=price_unit,
    #         quantity=quantity, product=product, partner=partner
    #     )

class  AccountInvoiceLine_Inherit_module(models.Model):
    _inherit = 'account.invoice.line'

    price_unit = fields.Float(digits=dp.get_precision('Compras FE'))
    quantity = fields.Float(digits=dp.get_precision('Compras FE'))

    @api.onchange('product_id')
    def _onchange_product_id(self):
        domain = {}
        if not self.invoice_id:
            return

        part = self.invoice_id.partner_id
        fpos = self.invoice_id.fiscal_position_id
        company = self.invoice_id.company_id
        currency = self.invoice_id.currency_id
        type = self.invoice_id.type

        if not part:
            warning = {
                    'title': _('Warning!'),
                    'message': _('You must first select a partner.'),
                }
            return {'warning': warning}

        if not self.product_id:
            if type not in ('in_invoice', 'in_refund'):
                self.price_unit = 0.0
            domain['uom_id'] = []
            if fpos:
                self.account_id = fpos.map_account(self.account_id)
        else:
            self_lang = self
            if part.lang:
                self_lang = self.with_context(lang=part.lang)

            product = self_lang.product_id
            account = self.get_invoice_line_account(type, product, fpos, company)
            if account:
                self.account_id = account.id
            self._set_taxes()
            if type not in ('in_invoice', 'in_refund'):
                product_name = self_lang._get_invoice_line_name_from_product()
                if product_name != None:
                    self.name = product_name
            if not self.uom_id or product.uom_id.category_id.id != self.uom_id.category_id.id:
                self.uom_id = product.uom_id.id
            domain['uom_id'] = [('category_id', '=', product.uom_id.category_id.id)]

            if company and currency:

                if self.uom_id and self.uom_id.id != product.uom_id.id:
                    self.price_unit = product.uom_id._compute_price(self.price_unit, self.uom_id)
        return {'domain': domain}
