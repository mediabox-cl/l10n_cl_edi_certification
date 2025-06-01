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
        ('preparation', 'Preparación Inicial'),
        ('configuration', 'Configuración Sets y CAFs'),
        ('generation', 'Generación DTEs'),
    ], string='Estado', default='preparation', tracking=True)
    
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
        string='Sets de Pruebas Definidas')
    
    dte_case_to_generate_count = fields.Integer(
        compute='_compute_dte_case_to_generate_count',
        string='Casos DTE Pendientes')

    # Checklists
    has_digital_signature = fields.Boolean(compute='_compute_has_digital_signature', string='Firma Digital')
    has_company_activities = fields.Boolean(compute='_compute_has_company_activities', string='Actividades Económicas')
    cafs_status = fields.Char(
        compute='_compute_cafs_status', 
        string='CAFs Requeridos',
        help='Estado de CAFs por tipo de documento'
    )

    cafs_status_color = fields.Char(
        compute='_compute_cafs_status',
        string='Color CAFs',
        help='Color del estado de CAFs'
    )    
    active_company_id = fields.Many2one(
        'res.company',
        string="Compañía Activa",
        compute='_compute_active_company_id',
        store=False
    )
    # CON ESTOS CAMPOS NUEVOS:
    selected_parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set',
        string="Set Seleccionado",
        domain="[('certification_process_id', '=', id)]",
        help="Seleccione un set para ver sus casos DTE"
    )

    related_dte_cases = fields.One2many(
        'l10n_cl_edi.certification.case.dte',
        compute='_compute_related_dte_cases',
        string="Casos DTE del Set Seleccionado",
    )

    # Campos de configuración para certificación
    certification_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Certificación',
        readonly=True,
        help='Diario creado automáticamente para el proceso de certificación'
    )
    certification_partner_id = fields.Many2one(
        'res.partner',
        string='Cliente SII (Certificación)',
        readonly=True,
        help='Partner con RUT del SII creado automáticamente para documentos de certificación'
    )
    default_tax_id = fields.Many2one(
        'account.tax',
        string='Impuesto IVA por Defecto',
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'), ('amount', '=', 19)]",
        help='Impuesto IVA al 19% que se aplicará a los items no exentos'
    )
    default_discount_product_id = fields.Many2one(
        'product.product',
        string='Producto de Descuento',
        domain="[('type', '=', 'service')]",
        help='Producto que se usará para aplicar descuentos globales'
    )

    _sql_constraints = [
            ('company_uniq', 'unique(company_id)', 'Solo puede existir un proceso de certificación por compañía'),
        ]

    def _compute_active_company_id(self):
        """Calcula la compañía activa del usuario"""
        for record in self:
            record.active_company_id = self.env.company

    @api.depends('selected_parsed_set_id')
    def _compute_related_dte_cases(self):
        """Filtra los casos DTE basados en el set seleccionado."""
        for record in self:
            if record.selected_parsed_set_id:
                record.related_dte_cases = record.selected_parsed_set_id.dte_case_ids
            else:
                record.related_dte_cases = False

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """
        Método search_read mejorado que verificación automáticamente el estado
        del proceso al cargar datos para las vistas.
        """
        # 1. Crear un registro automáticamente si no existe ninguno para la empresa actual
        company_id = self.env.company.id
        if not self.search_count([('company_id', '=', company_id)]):
            record = self.create({'company_id': company_id})
        else:
            # Obtener el registro existente
            record = self.search([('company_id', '=', company_id)], limit=1)
        
        # 2. VERIFICAR ESTADO AUTOMÁTICAMENTE
        if record:
            try:
                record.check_certification_status()
                _logger.info("Estado verificado automáticamente para proceso %s: %s", record.id, record.state)
            except Exception as e:
                _logger.warning("Error verificando estado automáticamente: %s", str(e))
    
        # 3. Comportamiento estándar de search_read
        return super(CertificationProcess, self).search_read(domain, fields, offset, limit, order)
    
    @api.model
    def default_get(self, fields_list):
        # Asegurar que solo haya un registro por compañía
        res = super(CertificationProcess, self).default_get(fields_list)
        res['company_id'] = self.env.company.id
        return res
        
    def open(self):
        """
        Método llamado cuando se abre un registro específico desde la vista de lista.
        Verifica automáticamente el estado del proceso al abrir el formulario.
        """
        self.ensure_one()
        result = self.check_certification_status()
        _logger.info("Abierto registro de certificación %s, estado verificado: %s", self.id, self.state)
        
        # Redirigir a la vista del formulario
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.process',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
    
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
    
    def _compute_cafs_status(self):
        """
        Computes and updates the CAFs (Folio Authorization Codes) status for each certification process record.
        This method determines which document types require CAFs based on related DTE (Electronic Tax Document) cases.
        If no DTE cases are found, it falls back to a default set of document types. For each required document type,
        it checks if there is at least one CAF in 'in_use' status for the company. The method then updates the
        `cafs_status` and `cafs_status_color` fields on the record to reflect whether all required CAFs are available.
        Fields updated:
            - cafs_status (str): A string indicating the number of available CAFs versus required, with an emoji.
            - cafs_status_color (str): A CSS class for coloring the status text ('text-success' or 'text-danger').
        """
        for record in self:
            # Obtener tipos de documento requeridos desde los casos DTE
            required_doc_types = []
            
            if record.parsed_set_ids:
                # Extraer tipos únicos de todos los casos DTE
                dte_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
                    ('parsed_set_id.certification_process_id', '=', record.id)
                ])
                
                if dte_cases:
                    required_doc_types = list(set([
                        case.document_type_code for case in dte_cases 
                        if case.document_type_code
                    ]))
            
            # Si no hay casos DTE, usar tipos por defecto
            if not required_doc_types:
                required_doc_types = ['33', '61', '56', '52']
            
            # Verificar CAFs disponibles
            available_count = 0
            for doc_type in required_doc_types:
                if self.env['l10n_cl.dte.caf'].search_count([
                    ('company_id', '=', record.company_id.id),
                    ('l10n_latam_document_type_id.code', '=', doc_type),
                    ('status', '=', 'in_use')
                ]) > 0:
                    available_count += 1
            
            total_required = len(required_doc_types)
            
            # Generar texto del estado
            if available_count == total_required:
                record.cafs_status = f"✅ {available_count}/{total_required} Completo"
                record.cafs_status_color = 'text-success'
            else:
                record.cafs_status = f"❌ {available_count}/{total_required} Faltan CAFs"
                record.cafs_status_color = 'text-danger'

            # Crear detalles por tipo
            caf_details = []
            missing_types = []
            
            for doc_type in required_doc_types:
                # Buscar el nombre del tipo de documento
                doc_type_name = record._get_document_type_name(doc_type)
                
                if self.env['l10n_cl.dte.caf'].search_count([
                    ('company_id', '=', record.company_id.id),
                    ('l10n_latam_document_type_id.code', '=', doc_type),
                    ('status', '=', 'in_use')
                ]) > 0:
                    caf_details.append(f"✅ {doc_type_name}")
                else:
                    caf_details.append(f"❌ {doc_type_name}")
                    missing_types.append(doc_type_name)
            
            # Generar resumen y detalles
            available_count = total_required - len(missing_types)
            
            if missing_types:
                summary = f"❌ {available_count}/{total_required} - Faltan: {', '.join(missing_types)}"
                record.cafs_status_color = 'text-danger'
            else:
                summary = f"✅ {available_count}/{total_required} - Todos los CAFs disponibles"
                record.cafs_status_color = 'text-success'
            
            record.cafs_status = summary

    def _get_document_type_name(self, code):
        """Obtiene el nombre legible del tipo de documento."""
        doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', code),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if doc_type:
            return f"{code} ({doc_type.name})"
        else:
            return code
    
    def action_prepare_certification(self):
        """Prepara la base de datos para el proceso de certificación"""
        self.ensure_one()
        
        # 1. Crear/actualizar tipo de documento SET
        self._create_document_type_set()
        
        # 2. Crear/configurar diario específico para certificación
        certification_journal = self._create_certification_journal()
        
        # 3. Crear/configurar partner del SII para certificación
        certification_partner = self._create_certification_partner()
        
        # 4. Asignar los recursos creados al proceso
        self.write({
            'certification_journal_id': certification_journal.id,
            'certification_partner_id': certification_partner.id,
        })
        
        # 5. Verificar estado automáticamente (no forzar estado)
        self.check_certification_status()
        
        msg = _('Se ha configurado el tipo de documento SET para referencias.')
        msg += _(' Se ha configurado el diario "%s" para la certificación.') % certification_journal.name
        msg += _(' Se ha creado el partner con RUT del SII "%s" para los documentos.') % certification_partner.name
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Base de datos preparada'),
                'message': msg,
                'type': 'success',
                'sticky': False,
            }
        }
        
    def _create_certification_journal(self):
        """
        Crea o configura un diario específico para el proceso de certificación SII.
        
        Este diario servirá exclusivamente para la emisión de documentos
        durante el proceso de certificación, evitando conflictos con la operación normal.
        
        Returns:
            El diario configurado para certificación
        """
        self.ensure_one()
        company = self.company_id
        
        # 1. Buscar si ya existe un diario configurado para certificación
        certification_journal = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('name', '=like', '%Certificación SII%'),
            ('type', '=', 'sale')
        ], limit=1)
        
        if certification_journal:
            # Si ya existe, asegurar que esté correctamente configurado
            if not certification_journal.l10n_latam_use_documents:
                certification_journal.write({
                    'l10n_latam_use_documents': True,
                    'l10n_cl_point_of_sale_type': 'online'
                })
            return certification_journal
        
        # 2. Si no existe un diario específico, crear uno nuevo
        sequence = self.env['ir.sequence'].create({
            'name': 'Diario de Certificación SII',
            'padding': 6,
            'code': 'account.journal.certification.sequence',
            'company_id': company.id,
        })
        
        vals = {
            'name': 'Certificación SII',
            'code': 'CERT',
            'type': 'sale',
            'sequence': 10,
            'sequence_id': sequence.id,
            'company_id': company.id,
            'l10n_latam_use_documents': True,
            'l10n_cl_point_of_sale_type': 'online',
        }
        
        # Buscar cuenta de ingresos para asignar al diario
        income_account = self.env['account.account'].search([
            ('company_id', '=', company.id),
            ('account_type', '=like', 'income%'),
        ], limit=1)
        
        if income_account:
            vals['default_account_id'] = income_account.id
        
        # Crear el diario
        certification_journal = self.env['account.journal'].create(vals)
        _logger.info("Creado diario específico para certificación SII: %s (ID: %s)", 
                     certification_journal.name, certification_journal.id)
        
        return certification_journal
    
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
    
    def _create_certification_partner(self):
        """
        Crea o configura un partner para el proceso de certificación.
        
        Usa el RUT real del SII (requisito obligatorio para certificación) pero con 
        datos ficticios para el resto de la información del partner.
        
        Returns:
            El partner configurado para certificación
        """
        self.ensure_one()
        company = self.company_id
        
        # RUT del SII: 60.803.000-K (requisito obligatorio para certificación)
        sii_rut = '60803000'
        sii_dv = 'K'
        
        # Buscar el tipo de identificación RUT
        rut_identification_type = self.env['l10n_latam.identification.type'].search([
            ('name', '=', 'RUT'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if not rut_identification_type:
            # Fallback: buscar por cualquier criterio que contenga RUT
            rut_identification_type = self.env['l10n_latam.identification.type'].search([
                ('name', 'ilike', 'RUT'),
                ('country_id.code', '=', 'CL')
            ], limit=1)
        
        # 1. Buscar si ya existe nuestro partner específico de certificación
        # Buscar por nombre específico Y RUT para evitar encontrar el SII precargado
        certification_partner = self.env['res.partner'].search([
            ('name', '=', 'The John Doe\'s Foundation'),
            ('vat', '=', f'CL{sii_rut}{sii_dv}'),
            ('company_id', 'in', [company.id, False])
        ], limit=1)
        
        if certification_partner:
            # Si ya existe, asegurar que esté correctamente configurado
            update_vals = {
                'is_company': True,
                'customer_rank': 1,
                'supplier_rank': 0,
                'l10n_cl_sii_taxpayer_type': '1',  # Contribuyente de 1ra categoría
                'l10n_cl_dte_email': 'facturacion@johndoe.foundation',
                'company_id': company.id,
            }
            
            # Agregar tipo de identificación si se encontró
            if rut_identification_type:
                update_vals['l10n_latam_identification_type_id'] = rut_identification_type.id
            
            certification_partner.write(update_vals)
            return certification_partner
        
        # 2. Crear nuevo partner ficticio
        # Buscar región metropolitana (opcional)
        region_metropolitana = self.env['res.country.state'].search([
            ('country_id.code', '=', 'CL'),
            ('code', '=', 'RM')
        ], limit=1)
        
        vals = {
            'name': 'The John Doe\'s Foundation',
            'is_company': True,
            'customer_rank': 1,
            'supplier_rank': 0,
            'vat': f'CL{sii_rut}{sii_dv}',
            'country_id': self.env.ref('base.cl').id,
            'state_id': region_metropolitana.id if region_metropolitana else False,
            'street': 'Av. Ficticia 123, Oficina 456',
            'city': 'Santiago',
            'zip': '7500000',
            'phone': '+56 2 2345 6789',
            'email': 'contacto@johndoe.foundation',
            'website': 'https://johndoe.foundation',
            'company_id': company.id,
            # Campos específicos de Chile
            'l10n_cl_sii_taxpayer_type': '1',  # Contribuyente de 1ra categoría
            'l10n_cl_dte_email': 'facturacion@johndoe.foundation',
            'l10n_cl_activity_description': 'Servicios de consultoría y desarrollo tecnológico',
        }
        
        # Agregar tipo de identificación si se encontró
        if rut_identification_type:
            vals['l10n_latam_identification_type_id'] = rut_identification_type.id
        else:
            _logger.warning("No se encontró el tipo de identificación RUT para Chile. El partner se creará sin este campo.")
        
        # Crear el partner
        certification_partner = self.env['res.partner'].create(vals)
        _logger.info("Creado partner de certificación con RUT del SII: %s (ID: %s)", 
                     certification_partner.name, certification_partner.id)
        
        return certification_partner
    
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

        self.check_certification_status()
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
        """
        Genera todos los documentos tributarios electrónicos pendientes.
        Versión refactorizada que usa el nuevo generador por caso.
        """
        self.ensure_one()
        if self.state != 'generation':
            raise UserError(_("Primero debe completar la configuración inicial y cargar el set de pruebas."))

        # Asegurar que estamos en estado adecuado
        self.state = 'generation'
        self.env.cr.commit()  # Guardar el cambio de estado

        # Buscar casos pendientes
        cases_to_generate = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generation_status', '=', 'pending')
        ])
        
        if not cases_to_generate:
            self.state = 'data_loaded'
            raise UserError(_("No hay casos DTE pendientes de generación."))

        # Generar documentos usando el nuevo método por caso
        generated_count = 0
        error_count = 0
        not_implemented_count = 0
        
        for dte_case in cases_to_generate:
            try:
                # Crear el generador
                generator = self.env['l10n_cl_edi.certification.document.generator'].create({
                    'dte_case_id': dte_case.id,
                    'certification_process_id': self.id
                })
                
                # Intentar generar el documento
                generator.generate_document()
                generated_count += 1
                _logger.info("Documento generado exitosamente para caso %s", dte_case.case_number_raw)
                
            except NotImplementedError as e:
                # Tipo de documento no implementado aún
                _logger.warning("Tipo de documento no implementado para caso %s: %s", 
                               dte_case.case_number_raw, str(e))
                dte_case.write({
                    'generation_status': 'error',
                    'error_message': f"No implementado: {str(e)}"
                })
                not_implemented_count += 1
                
            except Exception as e:
                # Error real en la generación
                _logger.error("Error generando DTE para caso %s: %s", dte_case.case_number_raw, str(e))
                dte_case.write({
                    'generation_status': 'error',
                    'error_message': str(e)
                })
                error_count += 1
                
            # Commit por cada documento para preservar el progreso
            self.env.cr.commit()

        # Actualizar estado del proceso
        self.check_certification_status()
        
        # Construir mensaje más detallado
        message_parts = []
        if generated_count > 0:
            message_parts.append(_("%s DTEs generados exitosamente") % generated_count)
        if not_implemented_count > 0:
            message_parts.append(_("%s tipos de documento pendientes de implementar") % not_implemented_count)
        if error_count > 0:
            message_parts.append(_("%s DTEs con error") % error_count)
            
        message = ". ".join(message_parts) + "."
        
        # Determinar tipo de notificación
        notification_type = 'success'
        if error_count > 0:
            notification_type = 'danger'
        elif not_implemented_count > 0:
            notification_type = 'warning'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Generación de DTEs Completada'),
                'message': message,
                'type': notification_type,
                'sticky': True,
            }
        }

    def _get_partner_for_dte(self, dte_case):
        """ 
        Obtiene el partner ficticio para los documentos de certificación.
        Usa el partner configurado automáticamente durante el setup.
        """
        self.ensure_one()
        
        if not self.certification_partner_id:
            raise UserError(_("No se ha configurado el partner ficticio para certificación. "
                            "Ejecute primero 'Preparar Certificación' desde el proceso."))
        
        return self.certification_partner_id

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
        
        # Usar el diario de certificación configurado
        if not self.certification_journal_id:
            raise UserError(_("No se ha configurado el diario de certificación. "
                            "Ejecute primero 'Preparar Certificación' desde el proceso."))
        
        journal = self.certification_journal_id

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
            # Usar el impuesto configurado por defecto si está disponible
            if self.default_tax_id:
                iva_tax = self.default_tax_id
            else:
                # Fallback a búsqueda automática
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
        """
        Prepara las referencias para el documento account.move basado en el caso DTE.
        """
        references_to_create = []
        
        # Agregar la referencia obligatoria al SET primero
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if set_doc_type:
            references_to_create.append({
                'move_id': new_move.id,
                'l10n_cl_reference_doc_type_id': set_doc_type.id,
                'origin_doc_number': '',
                'reason': f'CASO {dte_case.case_number_raw}'
            })
        
        # Agregar las demás referencias (si existen)
        for ref in dte_case.reference_ids:
            # Buscar el documento referenciado si ya existe
            referenced_move = self._get_referenced_move(ref.referenced_sii_case_number)
            
            reference_values = {
                'move_id': new_move.id,
                'l10n_cl_reference_doc_type_id': (referenced_move.l10n_latam_document_type_id.id 
                                                if referenced_move else False),
                'origin_doc_number': (referenced_move.l10n_latam_document_number 
                                    if referenced_move else f"REF-{ref.referenced_sii_case_number}"),
                'reference_doc_code': ref.reference_code,  # Usar directamente el código de la referencia
                'reason': ref.reason_raw
            }
            references_to_create.append(reference_values)
        
        # Crear todas las referencias de una vez
        references = self.env['l10n_cl.account.invoice.reference'].create(references_to_create)
        
        return references

    def _apply_global_discount(self, move, discount_percent):
        """
        Aplica un descuento global al documento usando el producto de descuento estándar de Odoo.
        
        Args:
            move: Documento account.move al que aplicar el descuento
            discount_percent: Porcentaje de descuento a aplicar
        
        Returns:
            El documento modificado
        """
        if not move or not discount_percent or discount_percent <= 0:
            return move
        
        # Solo aplicar a líneas afectas (no exentas)
        affected_lines = move.invoice_line_ids.filtered(lambda l: l.tax_ids and not l.l10n_latam_vat_exempt)
        
        if not affected_lines:
            _logger.warning("No se pudo aplicar descuento global de %s%% al documento %s: no hay líneas afectas", 
                          discount_percent, move.name)
            return move
        
        # Calcular el monto total de los ítems afectos
        total_affected = sum(line.price_subtotal for line in affected_lines)
        
        # Calcular el monto del descuento
        discount_amount = total_affected * (discount_percent / 100.0)
        
        if discount_amount <= 0:
            return move
        
        # Usar el producto de descuento configurado si está disponible
        if self.default_discount_product_id:
            discount_product = self.default_discount_product_id
        else:
            # Fallback a búsqueda automática
            discount_product = self.env['product.product'].search([
                ('name', '=like', 'Descuento%')
            ], limit=1)
            
            if not discount_product:
                # Si no existe, usar un producto de servicio genérico
                discount_product = self.env.ref('product.product_service_01', raise_if_not_found=False)
                
                if not discount_product:
                    # En caso extremo que no exista ninguno de los anteriores
                    discount_product = self.env['product.product'].create({
                        'name': 'Descuento',
                        'type': 'service',
                        'invoice_policy': 'order',
                        'purchase_ok': True,
                        'sale_ok': True,
                    })
        
        # Obtener la cuenta contable para descuentos
        # Normalmente se usa la misma cuenta que los productos afectos
        account_id = affected_lines[0].account_id.id if affected_lines else False
        
        # Obtener los impuestos de las líneas afectas
        # El descuento debe llevar los mismos impuestos que los productos afectos
        tax_ids = [(6, 0, affected_lines[0].tax_ids.ids)] if affected_lines and affected_lines[0].tax_ids else []
        
        # Crear la línea de descuento
        discount_line_vals = {
            'product_id': discount_product.id,
            'name': f'Descuento Global {discount_percent}%',
            'price_unit': -discount_amount,  # Monto negativo
            'quantity': 1.0,
            'account_id': account_id,
            'tax_ids': tax_ids,
            'move_id': move.id,
        }
        
        # Crear la línea directamente
        discount_line = self.env['account.move.line'].create(discount_line_vals)
        
        # Actualizar totales del documento
        move._recompute_dynamic_lines()
        
        return move

    def _create_move_from_dte_case(self, dte_case):
        """Crea un registro account.move a partir de un registro l10n_cl_edi.certification.case.dte."""
        self.ensure_one()
        dte_case.ensure_one()

        _logger.info("Generando DTE para Caso SII: %s", dte_case.case_number_raw)

        try:
            # Obtener partner
            _logger.info("Obteniendo partner para DTE caso %s", dte_case.case_number_raw)
            partner = self._get_partner_for_dte(dte_case)
            _logger.info("Partner obtenido: %s (ID: %s)", partner.name if partner else 'None', partner.id if partner else 'None')
            
            # Preparar valores del move
            _logger.info("Preparando valores del move para caso %s", dte_case.case_number_raw)
            move_vals = self._prepare_move_vals(dte_case, partner)
            _logger.info("Valores del move preparados: %s", move_vals)
            
            # Preparar líneas de factura
            _logger.info("Preparando líneas de factura para caso %s (items: %d)", dte_case.case_number_raw, len(dte_case.item_ids))
            invoice_lines_vals = []
            for i, item in enumerate(dte_case.item_ids):
                _logger.info("Procesando item %d: %s", i+1, item.name)
                line_vals = self._prepare_move_line_vals(item, move_vals)
                invoice_lines_vals.append((0, 0, line_vals))
                _logger.info("Línea %d preparada: %s", i+1, line_vals)
            
            move_vals['invoice_line_ids'] = invoice_lines_vals

            # Crear el documento sin aplicar aún descuentos globales
            _logger.info("Creando account.move con valores: %s", move_vals)
            new_move = self.env['account.move'].create(move_vals)
            _logger.info("Account.move creado exitosamente: %s (ID: %s)", new_move.name, new_move.id)
            
            # Preparar referencias entre documentos
            _logger.info("Preparando referencias para move %s", new_move.name)
            self._prepare_references_for_move(dte_case, new_move)

            # Para guías de despacho, configurar campos específicos
            if dte_case.document_type_code == '52':
                _logger.info("Configurando campos específicos para guía de despacho")
                new_move.write({
                    'l10n_cl_dte_gd_move_reason': self._map_dispatch_motive_to_code(dte_case.dispatch_motive_raw),
                    'l10n_cl_dte_gd_transport_type': self._map_dispatch_transport_to_code(dte_case.dispatch_transport_type_raw),
                })
            
            # Para documentos de exportación configurar campos específicos
            if dte_case.document_type_code in ['110', '111', '112']:
                _logger.info("Configurando campos específicos para documento de exportación")
                new_move.write({
                    # Aquí se agregarían campos específicos para exportación
                })

            # Aplicar descuento global si corresponde
            if dte_case.global_discount_percent and dte_case.global_discount_percent > 0:
                _logger.info("Aplicando descuento global de %s%% al move %s", dte_case.global_discount_percent, new_move.name)
                self._apply_global_discount(new_move, dte_case.global_discount_percent)

            # Actualizar el caso DTE con la referencia al documento generado
            _logger.info("Actualizando caso DTE %s con referencia al move generado", dte_case.case_number_raw)
            dte_case.write({
                'generated_account_move_id': new_move.id,
                'generation_status': 'generated',
                'error_message': False
            })
            
            _logger.info("DTE %s generado exitosamente para Caso SII %s (ID: %s)", new_move.name, dte_case.case_number_raw, new_move.id)
            return new_move
            
        except Exception as e:
            _logger.error("Error en _create_move_from_dte_case para caso %s: %s", dte_case.case_number_raw, str(e), exc_info=True)
            raise

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
            'view_mode': 'list,form',  # Cambiado de tree a list
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
        }
        
    def action_view_test_documents(self):
        self.ensure_one()
        return {
            'name': _('Documentos de Prueba Generados'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',  # Cambiado de tree a list
            'domain': [('id', 'in', self.test_invoice_ids.ids)],
        }

    def action_view_parsed_sets(self):
        self.ensure_one()
        # Referenciar la acción por su ID XML correcto
        action = self.env.ref('l10n_cl_edi_certification.action_l10n_cl_edi_certification_parsed_set').read()[0]
        return action
    
    @api.model
    def _get_certification_id(self):
        record = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not record:
            record = self.create({'company_id': self.env.company.id})
        return record.id
  
    def check_certification_status(self):
        """Verifica el estado general del proceso de certificación con lógica mejorada."""
        self.ensure_one()
        
        # ETAPA 1: Verificar PREPARATION (Preparación Inicial)
        preparation_complete, preparation_details = self._check_preparation_complete()
        if not preparation_complete:
            self.state = 'preparation'
            result = {
                'state': 'preparation',
                'complete': False,
                'missing': preparation_details,
                'message': 'Complete la configuración básica para continuar'
            }
            
            # Si se llama desde la interfaz, mostrar notificación
            if self.env.context.get('show_notification'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Estado: Preparación Inicial'),
                        'message': _('Faltan: %s') % ', '.join(preparation_details),
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            return result
        
        # ETAPA 2: Verificar CONFIGURATION (Sets y CAFs)
        configuration_complete, configuration_details = self._check_configuration_complete()
        if not configuration_complete:
            self.state = 'configuration'
            result = {
                'state': 'configuration', 
                'complete': False,
                'missing': configuration_details,
                'message': 'Cargue sets de pruebas y verifique CAFs'
            }
            
            # Si se llama desde la interfaz, mostrar notificación
            if self.env.context.get('show_notification'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Estado: Configuración'),
                        'message': _('Faltan: %s') % ', '.join(configuration_details),
                        'type': 'info',
                        'sticky': True,
                    }
                }
            return result
        
        # ETAPA 3: Está en GENERATION
        self.state = 'generation'
        generation_status = self._check_generation_status()
        
        result = {
            'state': 'generation',
            'complete': True,
            'generation_details': generation_status,
            'message': generation_status.get('message', 'Proceso de generación en curso')
        }
        
        # Si se llama desde la interfaz, mostrar notificación
        if self.env.context.get('show_notification'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Estado: Generación'),
                    'message': generation_status.get('message', 'Listo para generar documentos'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        return result

    def _check_preparation_complete(self):
        """Verifica si la preparación inicial está completa."""
        checks = {
            'company_data': self._validate_company_data(),
            'digital_signature': self._validate_digital_signature(), 
            'server_config': self._validate_server_configuration(),
            'certification_resources': self._validate_certification_resources(),
        }
        
        missing = [key for key, value in checks.items() if not value]
        return len(missing) == 0, missing

    def _validate_company_data(self):
        """Valida que los datos de la empresa estén completos."""
        return all([
            bool(self.company_activity_ids),
            bool(self.resolution_number),
            bool(self.resolution_date), 
            bool(self.sii_regional_office),
        ])

    def _validate_digital_signature(self):
        """Valida que exista una firma digital válida."""
        return bool(self.env['certificate.certificate'].search([
            ('company_id', '=', self.company_id.id),
            ('is_valid', '=', True)
        ], limit=1))

    def _validate_server_configuration(self):
        """Valida configuración de servidores y email."""
        return all([
            bool(self.dte_service_provider),
            bool(self.dte_email),
        ])

    def _validate_certification_resources(self):
        """Valida que existan recursos necesarios para la certificación."""
        return all([
            bool(self.certification_journal_id),
            bool(self.certification_partner_id),
        ])

    def _check_configuration_complete(self):
        """Verifica sets cargados y CAFs correspondientes."""
        # Primero verificar que preparation esté completo
        prep_ok, _ = self._check_preparation_complete()
        if not prep_ok:
            return False, ['preparation_incomplete']
        
        checks = {
            'set_document_type': self._validate_set_document_type(),
            'sets_loaded': bool(self.parsed_set_ids),
            'cafs_available': self._validate_required_cafs_dynamic(),
        }
        
        missing = [key for key, value in checks.items() if not value]
        return len(missing) == 0, missing

    def _validate_set_document_type(self):
        """Valida que el tipo de documento SET esté correctamente configurado."""
        doc_type_set = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        return bool(doc_type_set)

    def _validate_required_cafs_dynamic(self):
        """Valida CAFs para los tipos de documento específicos del set cargado."""
        if not self.parsed_set_ids:
            return False
        
        # Extraer tipos de documento únicos de todos los casos DTE
        required_types = set()
        for parsed_set in self.parsed_set_ids:
            for dte_case in parsed_set.dte_case_ids:
                if dte_case.document_type_code:
                    required_types.add(dte_case.document_type_code)
        
        if not required_types:
            return False
        
        # Verificar CAF para cada tipo requerido
        for doc_type in required_types:
            if not self.env['l10n_cl.dte.caf'].search_count([
                ('company_id', '=', self.company_id.id),
                ('l10n_latam_document_type_id.code', '=', doc_type),
                ('status', '=', 'in_use')
            ]):
                return False
        
        return True

    def _check_generation_status(self):
        """Analiza el estado de generación de DTEs (mantiene lógica existente)."""
        all_cases_count = self.env['l10n_cl_edi.certification.case.dte'].search_count([
            ('parsed_set_id.certification_process_id', '=', self.id),
        ])
        
        if all_cases_count == 0:
            return {'stage': 'no_documents', 'message': 'No hay documentos para generar'}
        
        generated_cases_count = self.env['l10n_cl_edi.certification.case.dte'].search_count([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generation_status', '=', 'generated')
        ])
        
        pending_cases_count = all_cases_count - generated_cases_count
        
        if pending_cases_count > 0:
            message = f'{pending_cases_count} documento(s) pendiente(s) de generar'
            stage = 'pending_generation' 
        else:
            message = 'Todos los documentos generados correctamente'
            stage = 'all_generated'
        
        return {
            'stage': stage,
            'message': message,
            'total': all_cases_count,
            'generated': generated_cases_count,
            'pending': pending_cases_count
        }

    def action_check_certification_status(self):
        """Acción para verificar el estado desde la interfaz con notificaciones."""
        return self.with_context(show_notification=True).check_certification_status()