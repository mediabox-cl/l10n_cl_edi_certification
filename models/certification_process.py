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
        ('preparation', 'Preparación'),
        ('in_progress', 'En Progreso'),
        ('completed', 'Completado'),
        ('error', 'Error')
    ], string='Estado', default='preparation', track_visibility='onchange')
    
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
        
        # 2. **MEJORAR VERIFICACIÓN AUTOMÁTICA DE ESTADO**
        if record:
            try:
                # Verificar y recuperar relaciones perdidas
                record._recover_lost_relationships()
                
                # Verificar estado automáticamente
                record.check_certification_status()
                _logger.info("Estado verificado automáticamente para proceso %s: %s", record.id, record.state)
            except Exception as e:
                _logger.warning("Error verificando estado automáticamente: %s", str(e))
    
        # 3. Comportamiento estándar de search_read
        return super(CertificationProcess, self).search_read(domain, fields, offset, limit, order)

    def _recover_lost_relationships(self):
        """
        Método para recuperar relaciones perdidas entre casos DTE y facturas
        después de actualizaciones de módulo o problemas de sincronización.
        """
        self.ensure_one()
        _logger.info(f"=== INICIANDO RECUPERACIÓN DE RELACIONES PERDIDAS ===")
        
        # Buscar casos DTE sin factura vinculada pero que podrían tener una
        unlinked_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generated_account_move_id', '=', False),
            ('generation_status', '=', 'generated')  # Casos que dicen estar generados pero sin factura
        ])
        
        recovered_count = 0
        for case in unlinked_cases:
            # Buscar facturas que podrían estar relacionadas con este caso
            potential_invoices = self.env['account.move'].search([
                ('ref', '=', f'Certificación DTE - Caso {case.id}'),
                ('state', '!=', 'cancel')
            ])
            
            if potential_invoices:
                # Vincular la primera factura encontrada
                case.generated_account_move_id = potential_invoices[0]
                _logger.info(f"Recuperada relación: Caso {case.id} → Factura {potential_invoices[0].name}")
                recovered_count += 1
            else:
                # Si no hay factura pero el estado dice 'generated', resetear a 'pending'
                case.generation_status = 'pending'
                _logger.info(f"Reseteado estado del caso {case.id} a 'pending' (no se encontró factura)")
        
        if recovered_count > 0:
            _logger.info(f"=== RECUPERADAS {recovered_count} RELACIONES PERDIDAS ===")
            self.message_post(
                body=f"Se recuperaron {recovered_count} relaciones perdidas entre casos DTE y facturas",
                subject="Recuperación de Relaciones"
            )

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
        
        # **MEJORAR APERTURA DE FORMULARIO**
        try:
            # Recuperar relaciones perdidas
            self._recover_lost_relationships()
            
            # Verificar estado
            result = self.check_certification_status()
            _logger.info("Abierto registro de certificación %s, estado verificado: %s", self.id, self.state)
        except Exception as e:
            _logger.warning("Error en verificación al abrir formulario: %s", str(e))
        
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
        
        # 6. Retornar acción que recarga la vista actual
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.process',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
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
            ('account_type', 'in', ['income', 'income_other']),
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
        target_name = 'The John Doe\'s Foundation'
        target_vat = f'CL{sii_rut}{sii_dv}'
        
        _logger.info(f"Buscando/creando partner de certificación con RUT: {target_vat}")
        
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
        
        # 1. PRIMERA BÚSQUEDA: Por RUT exacto (más importante)
        partners_with_rut = self.env['res.partner'].search([
            ('vat', '=', target_vat),
            ('company_id', 'in', [company.id, False])
        ])
        
        _logger.info(f"Partners encontrados con RUT {target_vat}: {len(partners_with_rut)}")
        
        if partners_with_rut:
            # 2. VERIFICAR SI ALGUNO TIENE EL NOMBRE CORRECTO
            exact_match = partners_with_rut.filtered(lambda p: p.name == target_name)
            
            if exact_match:
                _logger.info(f"Partner exacto encontrado (RUT + nombre): {exact_match[0].name} (ID: {exact_match[0].id})")
                certification_partner = exact_match[0]
            else:
                # 3. USAR EL PRIMER PARTNER CON EL RUT Y ACTUALIZAR SU NOMBRE
                certification_partner = partners_with_rut[0]
                _logger.info(f"Partner con RUT encontrado pero nombre diferente: '{certification_partner.name}' -> '{target_name}' (ID: {certification_partner.id})")
            
            # Asegurar que esté correctamente configurado
            update_vals = {
                'name': target_name,  # Asegurar nombre correcto
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
            _logger.info(f"Partner actualizado correctamente: {certification_partner.name} (ID: {certification_partner.id})")
            return certification_partner
        
        # 4. NO EXISTE NINGÚN PARTNER CON ESE RUT - CREAR UNO NUEVO
        _logger.info(f"No se encontró ningún partner con RUT {target_vat}. Creando uno nuevo...")
        
        # Buscar región metropolitana (opcional)
        region_metropolitana = self.env['res.country.state'].search([
            ('country_id.code', '=', 'CL'),
            ('code', '=', 'RM')
        ], limit=1)
        
        vals = {
            'name': target_name,
            'is_company': True,
            'customer_rank': 1,
            'supplier_rank': 0,
            'vat': target_vat,
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
        
        # Retornar acción que recarga la vista actual
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.process',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_generate_dte_documents(self):
        """
        Genera todos los documentos tributarios electrónicos pendientes.
        Usa el nuevo flujo sale.order → invoice para evitar problemas con rating mixin.
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

        # Generar documentos usando el nuevo generador
        generated_count = 0
        error_count = 0
        
        for dte_case in cases_to_generate:
            try:
                # Crear el generador
                generator = self.env['l10n_cl_edi.certification.document.generator'].create({
                    'dte_case_id': dte_case.id,
                    'certification_process_id': self.id
                })
                
                # Generar el documento usando el nuevo flujo
                invoice = generator.generate_document()
                generated_count += 1
                _logger.info("Documento generado exitosamente para caso %s: %s", 
                           dte_case.case_number_raw, invoice.name)
                
            except Exception as e:
                # Error en la generación
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
        
        # Construir mensaje
        message_parts = []
        if generated_count > 0:
            message_parts.append(_("%s DTEs generados exitosamente") % generated_count)
        if error_count > 0:
            message_parts.append(_("%s DTEs con error") % error_count)
            
        message = ". ".join(message_parts) + "."
        
        # Determinar tipo de notificación
        notification_type = 'success' if error_count == 0 else 'warning'
        
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
        _logger.info(f"=== INICIANDO CHECK CERTIFICATION STATUS para empresa {self.company_id.name} ===")
        
        # ETAPA 1: Verificar PREPARATION (Preparación Inicial)
        _logger.info("Verificando etapa PREPARATION...")
        preparation_complete, preparation_details = self._check_preparation_complete()
        _logger.info(f"Preparation complete: {preparation_complete}, detalles: {preparation_details}")
        
        if not preparation_complete:
            _logger.warning(f"Preparation incompleta. Manteniendo estado 'preparation'. Faltantes: {preparation_details}")
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
        _logger.info("Preparation completa. Verificando etapa CONFIGURATION...")
        configuration_complete, configuration_details = self._check_configuration_complete()
        _logger.info(f"Configuration complete: {configuration_complete}, detalles: {configuration_details}")
        
        if not configuration_complete:
            _logger.info(f"Configuration incompleta. Cambiando estado a 'configuration'. Faltantes: {configuration_details}")
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
        _logger.info("Configuration completa. Cambiando estado a 'generation'")
        self.state = 'generation'
        generation_status = self._check_generation_status()
        
        result = {
            'state': 'generation',
            'complete': True,
            'generation_details': generation_status,
            'message': generation_status.get('message', 'Proceso de generación en curso')
        }
        
        _logger.info(f"=== CHECK CERTIFICATION STATUS COMPLETADO. Estado final: {self.state} ===")
        
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
        _logger.info("--- Verificando validaciones de preparation ---")
        
        checks = {
            'company_data': self._validate_company_data(),
            'digital_signature': self._validate_digital_signature(), 
            'server_config': self._validate_server_configuration(),
            'certification_resources': self._validate_certification_resources(),
        }
        
        for check_name, result in checks.items():
            _logger.info(f"Validación {check_name}: {'✓ PASS' if result else '✗ FAIL'}")
        
        missing = [key for key, value in checks.items() if not value]
        _logger.info(f"Validaciones faltantes: {missing}")
        return len(missing) == 0, missing

    def _validate_company_data(self):
        """Valida que los datos de la empresa estén completos."""
        _logger.info("--- Verificando datos de la empresa ---")
        
        checks = {
            'company_activity_ids': bool(self.company_activity_ids),
            'resolution_number': bool(self.resolution_number),
            'resolution_date': bool(self.resolution_date),
            'sii_regional_office': bool(self.sii_regional_office),
        }
        
        for field, result in checks.items():
            _logger.info(f"  {field}: {'✓' if result else '✗'} (valor: {getattr(self, field, 'N/A')})")
        
        return all(checks.values())

    def _validate_digital_signature(self):
        """Valida que exista una firma digital válida."""
        _logger.info("Verificando firma digital...")
        
        cert_count = self.env['certificate.certificate'].search_count([
            ('company_id', '=', self.company_id.id),
            ('is_valid', '=', True)
        ])
        
        _logger.info(f"  Certificados válidos encontrados: {cert_count}")
        return cert_count > 0

    def _validate_server_configuration(self):
        """Valida configuración de servidores y email."""
        _logger.info("Verificando configuración del servidor...")
        
        checks = {
            'dte_service_provider': bool(self.dte_service_provider),
            'dte_email': bool(self.dte_email),
        }
        
        for field, result in checks.items():
            _logger.info(f"  {field}: {'✓' if result else '✗'} (valor: {getattr(self, field, 'N/A')})")
        
        return all(checks.values())

    def _validate_certification_resources(self):
        """Valida que existan recursos necesarios para la certificación."""
        _logger.info("Verificando recursos de certificación...")
        
        checks = {
            'certification_journal_id': bool(self.certification_journal_id),
            'certification_partner_id': bool(self.certification_partner_id),
        }
        
        for field, result in checks.items():
            resource = getattr(self, field, None)
            _logger.info(f"  {field}: {'✓' if result else '✗'} (ID: {resource.id if resource else 'None'})")
        
        return all(checks.values())

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
        self.check_certification_status()
        
        # Retornar acción que recarga la vista actual
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.process',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }