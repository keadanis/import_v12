import logging
_logger = logging.getLogger(__name__)

import re
import base64
import logging

from odoo import _
from odoo.exceptions import UserError

try:
    from lxml import etree
except ImportError:
    from xml.etree import ElementTree


_logger = logging.getLogger(__name__)


def get_tipo_documento_from_xml(node_xml):
    if node_xml == 'FacturaElectronica':
        return 'FE'
    elif node_xml == 'NotaCreditoElectronica':
        return  'NC'
    elif node_xml == 'NotaDebitoElectronica':
        return 'ND'
    elif node_xml == 'TiqueteElectronico':
        return 'TE'
    return ''


def load_xml_data_from_mail(invoice, load_lines, account_id, product_id=False, analytic_account_id=False):
    try:
        invoice_xml = etree.fromstring(base64.b64decode(invoice.xml_supplier_approval))
        document_type = re.search('FacturaElectronica|NotaCreditoElectronica|NotaDebitoElectronica|TiqueteElectronico',
                                  invoice_xml.tag).group(0)
        document_version = re.search('4.3|4.4', invoice_xml.tag).group(0)

        if document_type == 'TiqueteElectronico':
            raise UserError(_("This is a Electronic Ticket only a Electronic Bill are valid for taxes"))

    except Exception as e:
        invoice.unlink()
        raise UserError(_("This XML does not comply with the necessary structure to be processed. Error: %s") % e)

    namespaces = invoice_xml.nsmap
    inv_xmlns = namespaces.pop(None)
    namespaces['inv'] = inv_xmlns


    issuer_activity_id,receiver_activity_id,activity,issuer_neighborhood,other_charges_node = False, False, False, False, False

    # Se ajust diferencias entre versiones de Factura electrónica
    if document_version == '4.3':
        issuer_activity_node = invoice_xml.xpath("inv:CodigoActividad", namespaces=namespaces)
        payment_method_node = invoice_xml.xpath("inv:MedioPago", namespaces=namespaces)
        other_charges_node = invoice_xml.xpath("inv:OtrosCargos", namespaces=namespaces)
    elif document_version == '4.4':
        issuer_activity_node = invoice_xml.xpath("inv:CodigoActividadEmisor", namespaces=namespaces)
        receiver_activity_node = invoice_xml.xpath("inv:CodigoActividadReceptor", namespaces=namespaces)
        payment_method_node = invoice_xml.xpath("inv:MedioPago/inv:TipoMedioPago", namespaces=namespaces)
        other_charges_node = invoice_xml.xpath("inv:OtrosCargos", namespaces=namespaces)
        if receiver_activity_node:
            activity = invoice.env['economic.activity'].with_context(active_test=False).search(
                [
                    ('code', '=', receiver_activity_node[0].text)
                ],
                limit=1
            )
            receiver_activity_id = activity.id

    if issuer_activity_node:
        activity_id = issuer_activity_node[0].text
        activity = invoice.env['economic.activity'].with_context(active_test=False).search([('code', '=', activity_id)],
                                                                                           limit=1)
        issuer_activity_id = activity.id
    #Flag Invoice load from email
    # ---  Información General del Documento Electrónico --- #
    invoice.from_mail = True
    invoice.reference = invoice_xml.xpath("inv:NumeroConsecutivo", namespaces=namespaces)[0].text
    invoice.number_electronic = invoice_xml.xpath("inv:Clave", namespaces=namespaces)[0].text

    invoice.economic_activity_id = issuer_activity_id
    invoice.company_activity_id = receiver_activity_id or invoice.company_id.activity_id.id or False
    invoice.date_issuance = invoice_xml.xpath("inv:FechaEmision", namespaces=namespaces)[0].text
    invoice.date_invoice = invoice.date_issuance

    invoice.tipo_documento = get_tipo_documento_from_xml(document_type)

    invoice.amount_total_electronic_invoice = \
    invoice_xml.xpath("inv:ResumenFactura/inv:TotalComprobante", namespaces=namespaces)[0].text

    tax_node = invoice_xml.xpath("inv:ResumenFactura/inv:TotalImpuesto", namespaces=namespaces)
    if tax_node:
        invoice.amount_tax_electronic_invoice = tax_node[0].text

    currency_node = invoice_xml.xpath("inv:ResumenFactura/inv:CodigoTipoMoneda/inv:CodigoMoneda", namespaces=namespaces)
    if currency_node:
        invoice.currency_id = invoice.env['res.currency'].search([('name', '=', currency_node[0].text)], limit=1).id
    else:
        invoice.currency_id = invoice.env['res.currency'].search([('name', '=', 'CRC')], limit=1).id


    # ---  Información del Emisor --- #
    emisor = invoice_xml.xpath("inv:Emisor/inv:Identificacion/inv:Numero", namespaces=namespaces)[0].text
    try:
        receptor = invoice_xml.xpath("inv:Receptor/inv:Identificacion/inv:Numero", namespaces=namespaces)[0].text
    except Exception as e:
        invoice.unlink()
        raise UserError('The receptor info not was founded in XML. Please check the email in the inbox.')  # noqa

    if receptor != invoice.company_id.vat:
        #Deleted Invoice and stop Process
        invoice.unlink()
        raise UserError('The receptor in the XML does not correspond to the current company ' +
                        receptor + '. Please check the email in the inbox.')  # noqa

    partner = invoice.env['res.partner'].search([('vat', '=', emisor),
                                                 ('supplier', '=', True),
                                                 '|',
                                                 ('company_id', '=', invoice.company_id.id),
                                                 ('company_id', '=', False)],
                                                limit=1)

    if partner:
        invoice.partner_id = partner
    else:
        #Try Create Partner...
        try:
            nombre_emisor = invoice_xml.xpath("inv:Emisor/inv:Nombre", namespaces=namespaces)[0].text
            type_emisor = invoice_xml.xpath("inv:Emisor/inv:Identificacion/inv:Tipo", namespaces=namespaces)[0].text
            type = invoice.env['identification.type'].search([('code', '=', type_emisor)], limit=1)
        except Exception as e:
            invoice.unlink()
            raise UserError("There isn't necessary info for create Partner. Please check the email in the inbox.")

        vals = {
            'name': nombre_emisor,
            'company_id': invoice.company_id.id,
            'identification_id': type.id,
            'vat': emisor,
            'supplier': True,
            'customer': False,
            'active': True,
            'is_company': True,
            'type': 'contact',
            'activity_id': issuer_activity_id
        }
        try:
            issuer_street = invoice_xml.xpath("inv:Emisor/inv:Ubicacion/inv:OtrasSenas", namespaces=namespaces)[0].text
            vals['street'] = issuer_street
        except Exception as e:
            _logger.info("There isn't complementary info, error ({0}), but the invoicy will be created".format(e))
            pass
        try:
            email_emisor  = invoice_xml.xpath("inv:Emisor/inv:CorreoElectronico", namespaces=namespaces)[0].text
            vals['email'] = email_emisor
        except Exception as e:
            _logger.info("There isn't complementary info, error ({0}), but the invoicy will be created".format(e))
            pass
        try:
            phone_emisor = invoice_xml.xpath("inv:Emisor/inv:Telefono/inv:NumTelefono", namespaces=namespaces)[0].text
            vals['phone'] = phone_emisor
        except Exception as e:
            _logger.info("There isn't complementary info, error ({0}), but the invoicy will be created".format(e))
            pass
        try:
            payment_emisor = invoice_xml.xpath("inv:MedioPago", namespaces=namespaces)[0].text
            payment = invoice.env['payment.methods'].search([('sequence', '=', payment_emisor)], limit=1)
            vals['payment_methods_id'] = payment.id
        except Exception as e:
            _logger.info("There isn't complementary info, error ({0}), but the invoicy will be created".format(e))
            pass
        partner = invoice.env['res.partner'].sudo().create(vals)
        invoice.partner_id = partner
        invoice.message_post(
            body='The provider does not exist; it has been created automatically, please fill in the details of this provider before validating the bill.')
        _logger.info('The provider does not exist; it has been created automatically, please fill in the details of this provider before validating the bill.')

    invoice.account_id = partner.property_account_payable_id
    product_account_id = partner.import_bill_account_id.id or account_id.id or False
    invoice.payment_term_id = partner.property_supplier_payment_term_id

    if payment_method_node:
        invoice.payment_methods_id = invoice.env['payment.methods'].search([('sequence','=',payment_method_node[0].text)],limit=1)
    else:
        invoice.payment_methods_id = partner.payment_methods_id

    _logger.debug('FECR - load_lines: %s - account: %s' %
                  (load_lines, account_id))

    product = False
    if product_id:
        product = product_id.id

    analytic_account = False
    if analytic_account_id:
        analytic_account = analytic_account_id.id

    # if load_lines and not invoice.invoice_line_ids:
    if load_lines:
        lines = invoice_xml.xpath("inv:DetalleServicio/inv:LineaDetalle", namespaces=namespaces)
        new_lines = invoice.env['account.invoice.line']
        dict_lines = {}
        for line in lines:

            product_uom = invoice.env['uom.uom'].search(
                [('code', '=', line.xpath("inv:UnidadMedida", namespaces=namespaces)[0].text)],
                limit=1).id
            total_amount = float(line.xpath("inv:MontoTotal", namespaces=namespaces)[0].text)

            discount_percentage = 0.0
            discount_note = None

            if total_amount > 0:
                discount_node = line.xpath("inv:Descuento", namespaces=namespaces)
                discount_amount = 0.0
                discount_note = '' if discount_node else None
                for disc in discount_node:
                    discount_amount_node = disc.xpath("inv:MontoDescuento", namespaces=namespaces)[0].text
                    discount_amount += float(discount_amount_node or '0.0')
                    note_disc = disc.xpath("inv:NaturalezaDescuento", namespaces=namespaces)
                    if note_disc:
                        discount_note += "%s\n" %note_disc[0].text
                if discount_node:
                    discount_percentage = (discount_amount / total_amount) * 100

            total_tax = 0.0
            tax_amount_others = 0.0
            taxes = []
            tax_nodes = line.xpath("inv:Impuesto", namespaces=namespaces)
            dict_tax = {}
            dic_taxes={}
            if not tax_nodes:
                new_price_unit = line.xpath("inv:PrecioUnitario", namespaces=namespaces)[0].text
                quantity_taxs=float(line.xpath("inv:Cantidad", namespaces=namespaces)[0].text)
                new_subtotal_taxs = float(line.xpath("inv:SubTotal", namespaces=namespaces)[0].text)
            for tax_node in tax_nodes:
                tax_code = re.sub(r"[^0-9]+", "", tax_node.xpath("inv:Codigo", namespaces=namespaces)[0].text)
                tax_amount = float(tax_node.xpath("inv:Tarifa", namespaces=namespaces)[0].text)
                _logger.debug('FECR - tax_code: %s', tax_code)
                _logger.debug('FECR - tax_amount: %s', tax_amount)
                domain_tax = [('tax_code', '=', tax_code),
                         ('amount', '=', tax_amount),
                         ('type_tax_use', '=', 'purchase'),
                         ('active', '=', True)]
                iva_tax_code = False
                if document_version == '4.4':
                    iva_tax_code = re.sub(r"[^0-9]+", "", tax_node.xpath("inv:CodigoTarifaIVA", namespaces=namespaces)[0].text)
                    domain_tax.append(('iva_tax_code','=',iva_tax_code))

                if product_id and product_id.non_tax_deductible:
                    domain_tax.append(('non_tax_deductible', '=', True))
                    tax = invoice.env['account.tax'].search(
                        domain_tax,
                        limit=1)
        
                else:
                    domain_tax.append(('non_tax_deductible', '=', False))
                    tax = invoice.env['account.tax'].search(
                        domain_tax,
                        limit=1)
                    
                if tax:
                    
                    _logger.info('\n FECR - tax_amount tax: %s', tax)
                    # uno de los errores de por qué hay diferencia en los decimáles es
                    # porque el sistema no considera el campo total_tax para calcular el total de cada impuesto.
                    # El otro error de por qué hay diferencia al imprimir los reportes,
                    # es debido a que el monto de impuesto otros no lo toma del xml, sino se calcula desde el sql.

                    tax_node_amount = float(tax_node.xpath("inv:Monto", namespaces=namespaces)[0].text)
                    
                    subtotal_tax=float(line.xpath("inv:SubTotal", namespaces=namespaces)[0].text)
                    price_unit_taxs=float(line.xpath("inv:PrecioUnitario", namespaces=namespaces)[0].text)
                    quantity_taxs=float(line.xpath("inv:Cantidad", namespaces=namespaces)[0].text)

                    if tax.tax_code == '99' :
                        tax_amount_others = tax_node_amount
                        continue
                    new_subtotal_taxs = subtotal_tax + tax_amount_others
                    if tax_amount_others:
                        new_price_unit = new_subtotal_taxs / quantity_taxs
                    else:
                        new_price_unit = line.xpath("inv:PrecioUnitario", namespaces=namespaces)[0].text
                    total_tax += tax_node_amount


                    if tax.id not in dict_tax:
                        dict_tax[tax.id] = {'amount': 0.0}

                    dict_tax[tax.id].update(amount=dict_tax[tax.id]['amount'] + tax_node_amount)

                    exonerations = tax_node.xpath("inv:Exoneracion", namespaces=namespaces)
                    if exonerations:
                        for exoneration_node in exonerations:
                            exoneration_percentage = float(
                                exoneration_node.xpath("inv:TarifaExonerada", namespaces=namespaces)[0].text)
                            tax = invoice.env['account.tax'].search(
                                [('percentage_exoneration', '=', exoneration_percentage),
                                 ('type_tax_use', '=', 'purchase'),
                                 ('non_tax_deductible', '=', False),
                                 ('has_exoneration', '=', True),
                                 ('active', '=', True)],
                                limit=1)
                            if tax:
                                taxes.append((4, tax.id))
                    else:
                        taxes.append((4, tax.id))
                else:
                    if product_id and product_id.non_tax_deductible:
                        invoice.message_post(
                            body='Tax code %s and percentage %s as non-tax deductible is not registered in the system' % (
                            tax_code, tax_amount))
                        _logger.info(
                            'Tax code %s and percentage %s as non-tax deductible is not registered in the system' % (
                            tax_code, tax_amount))
                    else:
                        _logger.info('Tax code %s and percentage %s is not registered in the system' % (tax_code, tax_amount))
                        invoice.message_post(
                            body='Tax code %s - %s and percentage %s is not registered in the system' % (
                                tax_code, iva_tax_code or '', tax_amount))
                    
            
            invoice_line = invoice.env['account.invoice.line'].create({
                'name': line.xpath("inv:Detalle", namespaces=namespaces)[0].text,
                'invoice_id': invoice.id,
                'price_unit': new_price_unit,
                'quantity': quantity_taxs,
                'uom_id': product_uom,
                'sequence': line.xpath("inv:NumeroLinea", namespaces=namespaces)[0].text,
                'discount': discount_percentage,
                'discount_note': discount_note,
                # 'total_amount': total_amount,
                'product_id': product,
                'account_id': product_account_id,
                'account_analytic_id': analytic_account,
                'amount_untaxed': new_subtotal_taxs,
                'total_tax': total_tax,
                'economic_activity_id': invoice.economic_activity_id.id,
            })

            # This must be assigned after line is created
            invoice_line.invoice_line_tax_ids = taxes
            invoice_line.economic_activity_id = activity
            new_lines += invoice_line

            dict_lines[invoice_line.id] = {'price_unit': line.xpath("inv:PrecioUnitario", namespaces=namespaces)[0].text, 'taxes': dict_tax}

        # otrosCargos = invoice_xml.xpath("inv:OtrosCargos", namespaces=namespaces)
        if other_charges_node:
            for line in other_charges_node:
                if document_version == '4.3':
                    type_document = line.xpath("inv:TipoDocumento", namespaces=namespaces)[0].text
                elif document_version == '4.4':
                    type_document = line.xpath("inv:TipoDocumentoOC", namespaces=namespaces)[0].text
                # percentage = line.xpath("inv:Porcentaje", namespaces=namespaces)[0].text
                product = invoice.env['product.product'].search([('default_code','=',type_document)],limit=1)
                taxes = product.supplier_taxes_id.filtered(lambda t:t.active==True)
                monto_cargo = line.xpath("inv:MontoCargo", namespaces=namespaces)[0].text
                if not float(monto_cargo):
                    continue
                invoice_line = invoice.env['account.invoice.line'].create({
                    'name': line.xpath("inv:Detalle", namespaces=namespaces)[0].text,
                    'invoice_id': invoice.id,
                    'price_unit': monto_cargo,
                    'quantity': 1,
                    'uom_id': product.uom_id.id,
                    'product_id': product.id,
                    'account_id': product_account_id,
                    'account_analytic_id': analytic_account,
                    'invoice_line_tax_ids':[(4,taxes.id)]
                    })

                invoice_line.economic_activity_id = activity
                new_lines += invoice_line

        invoice.invoice_line_ids = new_lines
    
    invoice.compute_taxes()
