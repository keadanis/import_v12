# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


import logging
import email
import base64
import pathlib

try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib

from lxml import etree
from datetime import datetime
import re

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, pycompat
from odoo.tests.common import Form
from . import api_import_mail

_logger = logging.getLogger(__name__)
MAX_POP_MESSAGES = 10
MAIL_TIMEOUT = 60


class FetchmailServer(models.Model):
    _inherit = 'fetchmail.server'

    @api.multi
    def fetch_mail(self):
        _logger.info("Test from ir.cron")
        res_companies_ids = self.env['res.company'].sudo().search([])
        for res_company_id in res_companies_ids:
            if res_company_id.import_bill_automatic:
                additionnal_context = {
                    'fetchmail_cron_running': True
                }
                MailThread = self.env['mail.thread']
                server = res_company_id.import_bill_mail_server_id
                additionnal_context['fetchmail_server_id'] = server.id
                additionnal_context['server_type'] = server.type
                # Buscar el mail, leer correos --- importar factura ...
                _logger.info('Start checking for new emails on %s server %s', server.type, server.name)
                count, failed = 0, 0
                imap_server = None
                if server.type == 'imap':
                    try:
                        imap_server = server.connect()
                        imap_server.select(mailbox=res_company_id.import_bill_folder_import or 'INBOX')
                        result, data = imap_server.search(None, '(UNSEEN)')
                        if not data[0]:
                            _logger.info("Empty Folder (Stop Execute)")
                            return
                        for num in data[0].split():
                            result, data = imap_server.fetch(num, '(RFC822)')
                            imap_server.store(num, '-FLAGS', '\\Seen')
                            message = data[0][1]
                            try:
                                # To leave the mail in the state in which they were.
                                if isinstance(message, xmlrpclib.Binary):
                                    message = bytes(message.data)
                                if isinstance(message, pycompat.text_type):
                                    message = message.encode('utf-8')
                                extract = getattr(email, 'message_from_bytes', email.message_from_string)
                                msg_txt = extract(message)
                                # parse the message, verify we are not in a loop by checking message_id is not
                                # duplicated
                                msg = MailThread.with_context(**additionnal_context).message_parse(msg_txt,
                                                                                                   save_original=False)
                                # Fixing --> Save Original : False --> No store Content On Odoo
                                _logger.info("------ Process Message --------")
                                _logger.info("Subject : %s " % msg.get('subject', ''))
                                _logger.info("From: %s " % msg.get('from', ''))
                                _logger.info("To: %s " % msg.get('to', ''))
                                result = self.create_invoice_with_attamecth(msg, res_company_id)
                                if result and not isinstance(result, bool):
                                    if not server.original:
                                        _logger.info("Deleting Mail")
                                        imap_server.store(num, '+FLAGS', '\\Deleted')
                                    _logger.info("Invoice created correctly %s", str(result))
                                elif result:
                                    if not server.original:
                                        _logger.info("Deleting Mail")
                                        imap_server.store(num, '+FLAGS', '\\Deleted')
                                    _logger.info("Repeated Invoice")
                                else:
                                    _logger.info("Ignore email")
                            except Exception as e:
                                _logger.info('Failed to process mail from %s server %s. Exception (%s)', server.type,
                                             server.name, str(e),
                                             exc_info=True)
                                failed += 1
                            imap_server.store(num, '+FLAGS', '\\Seen')
                            self._cr.commit()
                            count += 1
                            _logger.info("------ End Process Message -------")
                        _logger.info("Fetched %d email(s) on %s server %s; %d succeeded, %d failed.", count,
                                     server.type, server.name, (count - failed), failed)
                    except Exception as e:
                        _logger.info("General failure when trying to fetch mail from %s server %s. Exception (%s)",
                                     server.type,
                                     server.name, str(e), exc_info=True)
                    finally:
                        if imap_server:
                            _logger.info("Finally Execute -> Close Imap Server")
                            imap_server.close()
                            imap_server.logout()
                    server.write({'date': fields.Datetime.now()})
                else:
                    _logger.info("Only Support for IMAP Server")
                    server.write({'date': fields.Datetime.now()})
                    return super(FetchmailServer, self).fetch_mail()

    @staticmethod
    def is_xml_file_in_attachment(attach):
        file_name = attach.fname or 'item.ignore'
        if pathlib.Path(file_name.upper()).suffix == '.XML':
            return True
        return False

    def get_bill_exist_or_false(self, invoice_xml):
        namespaces = invoice_xml.nsmap
        inv_xmlns = namespaces.pop(None)
        namespaces['inv'] = inv_xmlns
        electronic_number = invoice_xml.xpath("inv:Clave", namespaces=namespaces)[0].text
        domain = [('number_electronic', '=', electronic_number)]
        return self.env['account.invoice'].search(domain, limit=1)

    def create_ir_attachment_invoice(self, invoice, attach, mimetype):
        return self.env['ir.attachment'].create({
            'name': attach.fname,
            'type': 'binary',
            'datas': base64.b64encode(attach.content),
            'datas_fname': attach.fname,
            'res_model': 'account.invoice',
            'res_id': invoice.id,
            'mimetype': mimetype
        })

    def create_invoice_with_attamecth(self, msg, company_id):
        for attach in msg.get('attachments'):
            if self.is_xml_file_in_attachment(attach):
                try:
                    attachencode = base64.encodestring(attach.content)
                    invoice_xml = etree.fromstring(base64.b64decode(attachencode))
                    document_type = re.search(
                        'FacturaElectronica|NotaCreditoElectronica|'
                        'NotaDebitoElectronica|TiqueteElectronico|MensajeHacienda',
                        invoice_xml.tag).group(0)
                    
                    # if document_type == 'TiqueteElectronico' or document_type == 'NotaDebitoElectronica':
                    if document_type == 'TiqueteElectronico':
                        _logger.info("This is a TICKET only invoices are valid for taxes")
                        continue
                        # continue
                    # Check Exist
                    exist_invoice = self.get_bill_exist_or_false(invoice_xml)

                    if document_type == 'MensajeHacienda':
                        if exist_invoice:
                            if not exist_invoice.has_ack:
                                attachment_id = self.create_ir_attachment_invoice(exist_invoice, attach,
                                                                                  'application/xml')
                                exist_invoice.message_post(attachment_ids=[attachment_id.id])
                                exist_invoice.has_ack = True
                                _logger.info('ACK was loaded in exist Invoice')
                                return exist_invoice
                            else:
                                _logger.info('ACK is loaded, Deleting Mail')
                                return True
                        continue
                    if document_type == 'FacturaElectronica' and exist_invoice:
                        _logger.info("it isn´t ACK, Its duplicate Invoice (%s), Deleting Mail" % exist_invoice.number)
                        return True
                    if document_type == 'NotaCreditoElectronica' and exist_invoice:
                        _logger.info("it isn´t ACK, Its duplicate Invoice (%s), Deleting Mail" % exist_invoice.number)
                        return True
                    # If not is ACK is Invoice
                    if document_type == 'FacturaElectronica' or document_type == 'NotaDebitoElectronica':
                        type_invoice = 'in_invoice'
                    elif document_type == 'NotaCreditoElectronica':
                        type_invoice = 'in_refund'
                    else:
                        _logger.info("The electronic receipt is unknown, it will simply be ignored")

                    self = self.with_context(default_journal_id=company_id.import_bill_journal_id.id,
                                             default_type=type_invoice, type=type_invoice, journal_type='purchase')
                    invoice_form = Form(self.env['account.invoice'], view='account.invoice_supplier_form')
                    invoice = invoice_form.save()
                    invoice.fname_xml_supplier_approval = attach.fname
                    invoice.xml_supplier_approval = base64.encodestring(attach.content)
                    api_import_mail.load_xml_data_from_mail(invoice, True, company_id.import_bill_account_id,
                                                            company_id.import_bill_product_id,
                                                            company_id.import_bill_account_analytic_id)

                    if invoice:
                        attachment_id = self.create_ir_attachment_invoice(invoice, attach, 'application/xml')
                        list_attachment = [attachment_id.id]
                        # Searching PDF
                        for attach in msg.get('attachments'):
                            file_name = attach.fname or 'item.ignore'
                            if pathlib.Path(file_name.upper()).suffix == '.XML':
                                attachencode = base64.encodestring(attach.content)
                                invoice_xml = etree.fromstring(base64.b64decode(attachencode))
                                if re.search('MensajeHacienda', invoice_xml.tag):
                                    list_attachment.append(
                                        self.create_ir_attachment_invoice(invoice, attach, 'application/xml').id)
                            if pathlib.Path(file_name.upper()).suffix == '.PDF':
                                list_attachment.append(
                                    self.create_ir_attachment_invoice(invoice, attach, 'application/pdf').id)

                        invoice.message_post(attachment_ids=list_attachment)
                        return invoice
                    else:
                        False

                except Exception as e:
                    _logger.info("This XML file is not XML-compliant. Error: %s", e)
                    continue
        return False
