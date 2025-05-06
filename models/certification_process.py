from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging

# For XML Parsing
from lxml import etree

_logger = logging.getLogger(__name__)

class CertificationProcess(models.Model):
    _name = 'l10n_cl_edi.certification.process'  # Actualizado
    _description = 'Proceso de Certificación SII'
    _rec_name = 'company_id'
    
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('setup', 'Configuración Inicial'),
        ('data_loaded', 'Datos Cargados'),
        ('generation', 'Generación DTEs'),
        ('finished', 'Certificado')
    ], string='Estado', default='draft', tracking=True)
    
    # Información de certificación
    dte_email = fields.Char(related='company_id.l10n_cl_dte_email', readonly=False, string='Email DTE')
    resolution_number = fields.Char(related='company_id.l10n_cl_dte_resolution_number', readonly=False, string='Número Resolución SII')
    resolution_date = fields.Date(related='company_id.l10n_cl_dte_resolution_date', readonly=False, string='Fecha Resolución SII')
    sii_regional_office = fields.Selection(related='company_id.l10n_cl_sii_regional_office', readonly=False, string='Oficina Regional SII')
    dte_service_provider = fields.Selection(related='company_id.l10n_cl_dte_service_provider', readonly=False, string='Proveedor Servicio DTE')
    company_activity_ids = fields.Many2many(related='company_id.l10n_cl_company_activity_ids', readonly=False, string='Actividades Económicas')
    
    # Contador de documentos
    caf_count = fields.Integer(compute='_compute_caf_count', string='CAFs')
    document_count = fields.Integer(compute='_compute_document_count', string='Documentos de Prueba Generados')
    
    # Seguimiento de set de pruebas
    set_prueba_file = fields.Binary(string='Archivo XML Set de Pruebas', attachment=True)
    set_prueba_filename = fields.Char(string='Nombre del archivo XML')
    test_invoice_ids = fields.One2many(
        'account.move', 'l10n_cl_edi_certification_id',  # Actualizado
        string='Documentos de Prueba Generados',
        domain=[('move_type', 'not in', ('entry', 'liq_purchase'))])

    # New field to link to parsed sets
    parsed_set_ids = fields.One2many(
        'l10n_cl_edi.certification.parsed_set', 'certification_process_id',  # Actualizado
        string='Sets de Pruebas Definidos')
    
    dte_case_to_generate_count = fields.Integer(
        compute='_compute_dte_case_to_generate_count',
        string='Casos DTE Pendientes')

    # Checklists
    has_digital_signature = fields.Boolean(compute='_compute_has_digital_signature', string='Firma Digital')
    has_company_activities = fields.Boolean(compute='_compute_has_company_activities', string='Actividades Económicas')
    has_required_cafs = fields.Boolean(compute='_compute_has_required_cafs', string='CAFs Requeridos')
    
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Crear un registro automáticamente si no existe y se solicita desde la acción del menú"""
        if self.env.context.get('create_if_not_exist'):
            existing = self.search([('company_id', '=', self.env.company.id)], limit=1)
            if not existing:
                self.create({'company_id': self.env.company.id})
        
        return super(CertificationProcess, self).search_read(domain=domain, fields=fields, 
                                                            offset=offset, limit=limit, order=order)
    @api.model
    def default_get(self, fields_list):
        # Asegurar que solo haya un registro por compañía
        res = super(CertificationProcess, self).default_get(fields_list)
        res['company_id'] = self.env.company.id
        return res
        
    def _compute_caf_count(self):
        for record in self:
            record.caf_count = self.env['l10n_cl.dte.caf'].search_count([
                ('company_id', '=', record.company_id.id)
            ])
    
    def _compute_document_count(self):
        for record in self:
            record.document_count = len(record.test_invoice_ids)
    
    def _compute_dte_case_to_generate_count(self):
        for record in self:
            record.dte_case_to_generate_count = self.env['l10n_cl_edi.certification.case.dte'].search_count([  # Actualizado
                ('parsed_set_id.certification_process_id', '=', record.id),
                ('generation_status', '=', 'pending')
            ])
    
    def _compute_has_digital_signature(self):
        for record in self:
            record.has_digital_signature = bool(self.env['certificate.certificate'].search([
                ('company_id', '=', record.company_id.id),
                ('is_valid', '=', True)
            ], limit=1))
    
    def _compute_has_company_activities(self):
        for record in self:
            record.has_company_activities = bool(record.company_id.l10n_cl_company_activity_ids)
    
    def _compute_has_required_cafs(self):
        for record in self:
            # Verificar CAFs para los tipos de documento requeridos (33, 61, 56, 52)
            required_doc_types = ['33', '61', '56', '52']
            record.has_required_cafs = all(
                self.env['l10n_cl.dte.caf'].search_count([
                    ('company_id', '=', record.company_id.id),
                    ('l10n_latam_document_type_id.code', '=', doc_type),
                    ('status', '=', 'in_use')
                ]) > 0
                for doc_type in required_doc_types
            )
    
    def action_prepare_certification(self):
        """Prepara la base de datos para el proceso de certificación"""
        self.ensure_one()
        
        # 1. Crear/actualizar tipo de documento SET
        self._create_document_type_set()
        
        # 2. Actualizar estado
        self.state = 'setup'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Base de datos preparada'),
                'message': _('Se ha configurado el tipo de documento SET para referencias.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _create_document_type_set(self):
        """Crea o actualiza el tipo de documento SET para referencias de certificación"""
        doc_type_set = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        vals = {
            'code': 'SET',
            'name': 'Documento Referencia SII (SET)',
            'internal_type': 'invoice',
            'l10n_cl_active': True,
            'doc_code_prefix': 'SET'
        }
        if doc_type_set:
            doc_type_set.write(vals)
        else:
            chile = self.env.ref('base.cl')
            vals.update({
                'country_id': chile.id,
                'sequence': 100
            })
            doc_type_set = self.env['l10n_latam.document.type'].create(vals)
        
        return doc_type_set
    
    def action_create_demo_cafs(self):
        """Crea CAFs de demostración para los tipos de documento requeridos"""
        self.ensure_one()
        
        # Verificar que estamos en modo SIIDEMO
        if self.company_id.l10n_cl_dte_service_provider != 'SIIDEMO':
            raise UserError(_('Para crear CAFs de demostración, primero debe configurar el Proveedor de Servicio DTE a SIIDEMO'))
        
        # Crear CAFs para los tipos de documento necesarios
        self.company_id._create_demo_caf_files()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('CAFs creados'),
                'message': _('Se han creado CAFs de demostración para los documentos requeridos.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_process_set_prueba_xml(self):
        """Procesa el archivo XML de set de pruebas para crear las definiciones de los documentos."""
        self.ensure_one()
        
        if not self.set_prueba_file:
            raise UserError(_('Debe cargar un archivo XML de Set de Pruebas primero'))

        # Clear previous parsed data for this process to avoid duplicates if re-processing
        self.parsed_set_ids.unlink() 

        try:
            xml_content = base64.b64decode(self.set_prueba_file).decode('utf-8')
            root = etree.fromstring(xml_content.encode('utf-8'))
        except Exception as e:
            _logger.error("Error parsing XML Set de Pruebas: %s", str(e))
            raise UserError(_("Error al procesar el archivo XML: %s") % str(e))

        parsed_set_model = self.env['l10n_cl_edi.certification.parsed_set']  # Actualizado
        dte_case_model = self.env['l10n_cl_edi.certification.case.dte']  # Actualizado
        item_model = self.env['l10n_cl_edi.certification.case.dte.item']  # Actualizado
        ref_model = self.env['l10n_cl_edi.certification.case.dte.reference']  # Actualizado
        purchase_entry_model = self.env['l10n_cl_edi.certification.purchase_book.entry']  # Actualizado
        instructional_model = self.env['l10n_cl_edi.certification.instructional_set']  # Actualizado

        sequence = 10
        for set_node in root.findall('ParsedSet'):
            set_vals = {
                'certification_process_id': self.id,
                'sequence': sequence,
                'set_type_raw': set_node.get('set_type_raw'),
                'set_type_normalized': set_node.get('set_type_normalized'),
                'attention_number': set_node.get('attention_number'),
                'raw_header_text': set_node.findtext('RawHeaderText')
            }
            parsed_set_rec = parsed_set_model.create(set_vals)
            sequence += 10

            # Process DTE Cases if they exist
            dte_cases_node = set_node.find('DTECases')
            if dte_cases_node is not None:
                case_seq = 10
                for case_node in dte_cases_node.findall('DTECase'):
                    dte_case_vals = {
                        'parsed_set_id': parsed_set_rec.id,
                        'case_number_raw': case_node.get('case_number_raw'),
                        'document_type_raw': case_node.get('document_type_raw'),
                        'document_type_code': case_node.get('document_type_code'),
                        'global_discount_percent': float(case_node.get('global_discount_percent', 0.0)),
                        'dispatch_motive_raw': case_node.findtext('DispatchMotiveRaw'),
                        'dispatch_transport_type_raw': case_node.findtext('DispatchTransportTypeRaw'),
                        'export_reference_text': case_node.findtext('ExportReferenceText'),
                        'export_currency_raw': case_node.findtext('ExportCurrencyRaw'),
                        'raw_text_block': case_node.findtext('RawTextBlock'),
                        'generation_status': 'pending'
                    }
                    dte_case_rec = dte_case_model.create(dte_case_vals)
                    case_seq += 10

                    item_seq = 10
                    items_node = case_node.find('Items')
                    if items_node is not None:
                        for item_node in items_node.findall('Item'):
                            item_vals = {
                                'case_dte_id': dte_case_rec.id,
                                'sequence': item_seq,
                                'name': item_node.get('name'),
                                'quantity': float(item_node.get('quantity', 1.0)),
                                'uom_raw': item_node.get('uom_raw'),
                                'price_unit': float(item_node.get('price_unit', 0.0)),
                                'discount_percent': float(item_node.get('discount_percent', 0.0)),
                                'is_exempt': item_node.get('is_exempt', 'false').lower() == 'true'
                            }
                            item_model.create(item_vals)
                            item_seq += 10
                    
                    ref_seq = 10
                    refs_node = case_node.find('References')
                    if refs_node is not None:
                        for ref_node in refs_node.findall('Reference'):
                            ref_vals = {
                                'case_dte_id': dte_case_rec.id,
                                'sequence': ref_seq,
                                'reference_document_text_raw': ref_node.get('text_raw'),
                                'referenced_sii_case_number': ref_node.get('sii_case_number'),
                                'reason_raw': ref_node.get('reason_raw')
                            }
                            ref_model.create(ref_vals)
                            ref_seq += 10

            # Process Purchase Book Entries if they exist
            purchase_entries_node = set_node.find('PurchaseBookEntries')
            if purchase_entries_node is not None:
                entry_seq = 10
                for entry_node in purchase_entries_node.findall('Entry'):
                    pb_vals = {
                        'parsed_set_id': parsed_set_rec.id,
                        'sequence': entry_seq,
                        'document_type_raw': entry_node.get('document_type_raw'),
                        'folio': entry_node.get('folio'),
                        'observations_raw': entry_node.get('observations_raw'),
                        'amount_exempt': float(entry_node.get('amount_exempt', 0.0)),
                        'amount_net_affected': float(entry_node.get('amount_net_affected', 0.0)),
                        'raw_text_lines': entry_node.findtext('RawTextLines')
                    }
                    purchase_entry_model.create(pb_vals)
                    entry_seq += 10
            
            # Process Instructional Content if it exists
            instructional_node = set_node.find('InstructionalContent')
            if instructional_node is not None:
                instructional_model.create({
                    'parsed_set_id': parsed_set_rec.id,
                    'instructions_text': instructional_node.findtext('InstructionsText'),
                    'general_observations': instructional_node.findtext('GeneralObservations')
                })

        self.state = 'data_loaded'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Set de Pruebas XML procesado'),
                'message': _('Se han cargado las definiciones de los sets y casos desde el archivo XML.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_generate_dte_documents(self):
        self.ensure_one()
        if self.state != 'data_loaded':
            raise UserError(_("Primero debe cargar y procesar el archivo XML del Set de Pruebas."))

        self.state = 'generation'
        self.env.cr.commit()

        cases_to_generate = self.env['l10n_cl_edi.certification.case.dte'].search([  # Actualizado
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generation_status', '=', 'pending')
        ])
        
        if not cases_to_generate:
            self.state = 'data_loaded'
            raise UserError(_("No hay casos DTE pendientes de generación."))

        generated_count = 0
        error_count = 0
        for dte_case in cases_to_generate:
            try:
                self._create_move_from_dte_case(dte_case)
                generated_count += 1
            except Exception as e:
                _logger.error("Error generando DTE para caso %s: %s", dte_case.case_number_raw, str(e))
                dte_case.write({
                    'generation_status': 'error',
                    'error_message': str(e)
                })
                error_count += 1
            self.env.cr.commit()

        if error_count == 0 and generated_count > 0:
            all_cases = self.env['l10n_cl_edi.certification.case.dte'].search_count([  # Actualizado
                ('parsed_set_id.certification_process_id', '=', self.id)
            ])
            total_generated = self.env['l10n_cl_edi.certification.case.dte'].search_count([  # Actualizado
                ('parsed_set_id.certification_process_id', '=', self.id),
                ('generation_status', '=', 'generated')
            ])
            if all_cases == total_generated:
                self.state = 'finished'
            else:
                self.state = 'data_loaded'
        elif generated_count > 0 and error_count > 0:
            self.state = 'data_loaded'
        elif error_count > 0 and generated_count == 0:
            self.state = 'data_loaded'
        
        message = _("%s DTEs generados exitosamente. %s DTEs con error.") % (generated_count, error_count)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Generación de DTEs Completada'),
                'message': message,
                'type': 'info' if error_count > 0 else 'success',
                'sticky': True,
            }
        }

    def _get_partner_for_dte(self, dte_case):
        """ 
        Placeholder: Get or create a partner for the DTE.
        For certification, usually a generic partner (the company itself or a test partner) is used.
        This method should be adapted based on actual requirements.
        """
        partner = self.company_id.partner_id
        if not partner:
            raise UserError(_("La compañía %s no tiene un partner asociado.") % self.company_id.name)
        return partner

    def _get_product_for_dte_item(self, item_name):
        """
        Placeholder: Get or create a product for the DTE line.
        For certification, generic products are often used.
        """
        product_model = self.env['product.product']
        product = product_model.search([('name', 'ilike', item_name)], limit=1)
        if not product:
            product = product_model.search([('default_code', '=', 'CERTIF_PROD')], limit=1)
            if not product:
                product = product_model.create({
                    'name': item_name,
                    'default_code': 'CERTIF_PROD' if item_name != 'Producto Certificación' else 'CERTIF_PROD_GENERIC',
                    'type': 'service',
                    'invoice_policy': 'order',
                    'list_price': 0,
                    'standard_price': 0,
                    'taxes_id': False,
                })
        return product

    def _get_referenced_move(self, referenced_sii_case_number):
        """Finds a generated account.move based on the SII case number of the reference."""
        self.ensure_one()
        if not referenced_sii_case_number:
            return self.env['account.move']
        
        referenced_dte_case = self.env['l10n_cl_edi.certification.case.dte'].search([  # Actualizado
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('case_number_raw', '=', referenced_sii_case_number),
            ('generated_account_move_id', '!=', False)
        ], limit=1)
        return referenced_dte_case.generated_account_move_id

    def _prepare_move_vals(self, dte_case, partner):
        """Prepares the main values for creating an account.move from a DTE case."""
        self.ensure_one()
        dte_case.ensure_one()

        doc_type_model = self.env['l10n_latam.document.type']
        sii_doc_type = doc_type_model.search([
            ('code', '=', dte_case.document_type_code),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        if not sii_doc_type:
            raise UserError(_("Tipo de documento SII '%s' no encontrado en Odoo para el caso %s.") % 
                            (dte_case.document_type_code, dte_case.case_number_raw))

        move_type_map = {
            '33': 'out_invoice',
            '34': 'out_invoice',
            '56': 'out_refund',
            '61': 'out_refund',
            '52': 'out_invoice',
            '110': 'out_invoice',
            '111': 'out_refund',
            '112': 'out_refund',
        }
        move_type = move_type_map.get(dte_case.document_type_code, 'out_invoice')
        if sii_doc_type.internal_type == 'debit_note':
             move_type = 'out_refund'
        elif sii_doc_type.internal_type == 'invoice' and dte_case.document_type_code == '34':
            move_type = 'out_invoice'
        elif sii_doc_type.internal_type == 'credit_note':
             move_type = 'out_refund'
        
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_latam_use_documents', '=', True)
        ], limit=1)
        if not journal:
            raise UserError(_("No se encontró un diario de ventas configurado para documentos LATAM en la compañía %s.") % self.company_id.name)

        move_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'l10n_latam_document_type_id': sii_doc_type.id,
            'invoice_date': fields.Date.context_today(self),
            'l10n_cl_edi_certification_id': self.id, 
        }
        return move_vals

    def _prepare_move_line_vals(self, dte_item, move_vals):
        """Prepares values for an account.move.line from a DTE case item."""
        product = self._get_product_for_dte_item(dte_item.name)
        price_unit = dte_item.price_unit
        if move_vals.get('move_type') == 'out_refund':
            pass

        line_vals = {
            'product_id': product.id,
            'name': dte_item.name,
            'quantity': dte_item.quantity,
            'price_unit': price_unit,
            'product_uom_id': product.uom_id.id,
            'discount': dte_item.discount_percent or 0.0,
        }
        if dte_item.is_exempt:
            line_vals['tax_ids'] = [(6, 0, [])]
        else:
            iva_tax = self.env['account.tax'].search([
                ('company_id', '=', self.company_id.id),
                ('type_tax_use', '=', 'sale'),
                ('amount_type', '=', 'percent'),
                ('amount', '=', 19),
                ('country_id.code', '=', 'CL')
            ], limit=1)
            if iva_tax:
                line_vals['tax_ids'] = [(6, 0, [iva_tax.id])]
            else:
                _logger.warning("No se encontró impuesto IVA al 19%% para ventas en Chile. Línea para '%s' sin impuesto.", dte_item.name)

        return line_vals

    def _prepare_references_for_move(self, dte_case, new_move):
        """Prepares reference data for the account.move. 
           This is usually handled by l10n_cl_edi module logic when _get_cl_reference_data is called.
           Here we are primarily concerned with linking to other Cert Process generated docs.
        """
        ref_data_to_store_on_move = []
        if not dte_case.reference_ids:
            return []

        for ref_def in dte_case.reference_ids:
            referenced_move = self._get_referenced_move(ref_def.referenced_sii_case_number)
            if not referenced_move:
                _logger.warning(
                    "Referenced move for SII Case %s not found for DTE Case %s. Manual check might be needed.", 
                    ref_def.referenced_sii_case_number, dte_case.case_number_raw
                )
                pass

        return ref_data_to_store_on_move

    def _create_move_from_dte_case(self, dte_case):
        """Creates an account.move record from a l10n_cl_edi.certification.case.dte record."""
        self.ensure_one()
        dte_case.ensure_one()

        _logger.info("Generando DTE para Caso SII: %s", dte_case.case_number_raw)

        partner = self._get_partner_for_dte(dte_case)
        move_vals = self._prepare_move_vals(dte_case, partner)
        
        invoice_lines_vals = []
        for item in dte_case.item_ids:
            invoice_lines_vals.append((0, 0, self._prepare_move_line_vals(item, move_vals)))
        move_vals['invoice_line_ids'] = invoice_lines_vals

        if dte_case.global_discount_percent and dte_case.global_discount_percent > 0:
            _logger.info("Caso %s tiene descuento global de %s%%. Implementar manejo.", 
                         dte_case.case_number_raw, dte_case.global_discount_percent)
            move_vals['narration'] = (move_vals.get('narration', '') + 
                                     f"\nDescuento Global Test SII: {dte_case.global_discount_percent}%").strip()

        new_move = self.env['account.move'].create(move_vals)
        
        self._prepare_references_for_move(dte_case, new_move)

        if dte_case.document_type_code == '52':
            new_move.write({
                'l10n_cl_dte_gd_move_reason': self._map_dispatch_motive_to_code(dte_case.dispatch_motive_raw),
                'l10n_cl_dte_gd_transport_type': self._map_dispatch_transport_to_code(dte_case.dispatch_transport_type_raw),
            })
        
        if dte_case.document_type_code in ['110', '111', '112']:
             new_move.write({
             })

        dte_case.write({
            'generated_account_move_id': new_move.id,
            'generation_status': 'generated',
            'error_message': False
        })
        _logger.info("DTE %s generado para Caso SII %s (ID: %s)", new_move.name, dte_case.case_number_raw, new_move.id)
        return new_move

    def _map_dispatch_motive_to_code(self, motive_raw):
        if not motive_raw: return False
        motive_upper = motive_raw.upper()
        if 'VENTA' in motive_upper: return '1'
        if 'COMPRA' in motive_upper: return '2'
        if 'CONSIGNACION' in motive_upper and 'A' in motive_upper: return '3'
        if 'CONSIGNACION' in motive_upper and 'DE' in motive_upper: return '4'
        if 'TRASLADO INTERNO' in motive_upper: return '5'
        if 'OTROS TRASLADOS NO VENTA' in motive_upper: return '6'
        if 'GUIA DE DEVOLUCION' in motive_upper: return '7'
        if 'TRASLADO PARA EXPORTACION' in motive_upper: return '8'
        if 'VENTA PARA EXPORTACION' in motive_upper: return '9'
        return False

    def _map_dispatch_transport_to_code(self, transport_raw):
        if not transport_raw: return False
        transport_upper = transport_raw.upper()
        if 'EMISOR' in transport_upper: return '1'
        if 'CLIENTE' in transport_upper and 'CUENTA' in transport_upper : return '2'
        if 'TERCEROS' in transport_upper: return '3'
        return False

    def action_view_cafs(self):
        self.ensure_one()
        return {
            'name': _('CAFs'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl.dte.caf',
            'view_mode': 'tree,form',
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
        }
    
    def action_view_test_documents(self):
        self.ensure_one()
        return {
            'name': _('Documentos de Prueba Generados'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.test_invoice_ids.ids)],
        }

    def action_view_parsed_sets(self):
        self.ensure_one()
        return {
            'name': _('Sets de Pruebas Definidos'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.parsed_set',
            'view_mode': 'tree,form',
            'domain': [('certification_process_id', '=', self.id)],
            'context': {'default_certification_process_id': self.id}
        }