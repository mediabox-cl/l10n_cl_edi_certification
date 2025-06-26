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
        ('configuration', 'Configuración'),
        ('generation', 'Generación'),
        ('finalization', 'Finalización'),
        ('completed', 'Completado'),
        ('error', 'Error')
    ], string='Estado', default='preparation')
    
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

    # Entradas de libro de compras
    purchase_entry_ids = fields.One2many(
        'l10n_cl_edi.certification.purchase_entry',
        'certification_process_id',
        string='Entradas Libro de Compras'
    )
    
    # Libros de guías de despacho
    delivery_guide_book_ids = fields.One2many(
        'l10n_cl_edi.certification.delivery_guide_book',
        'certification_process_id',
        string='Libros de Guías de Despacho'
    )
    
    # Contador de libros de guías
    delivery_guide_book_count = fields.Integer(
        compute='_compute_delivery_guide_book_count',
        string='Libros de Guías'
    )

    # Libros IECV generados
    iecv_book_ids = fields.One2many(
        'l10n_cl_edi.certification.iecv_book',
        'certification_process_id',
        string='Libros IECV Generados'
    )
    
    # Contadores relacionados con libros IECV
    iecv_books_count = fields.Integer(
        compute='_compute_iecv_books_count',
        string='Libros IECV'
    )
    
    purchase_entries_count = fields.Integer(
        compute='_compute_purchase_entries_count',
        string='Entradas de Compra'
    )

    # New field to link to parsed sets
    parsed_set_ids = fields.One2many(
        'l10n_cl_edi.certification.parsed_set', 'certification_process_id',  # Actualizado
        string='Sets de Pruebas Definidas')
    
    dte_case_to_generate_count = fields.Integer(
        compute='_compute_dte_case_to_generate_count',
        string='Casos DTE Pendientes')

    # Archivos de envío consolidado
    generated_batch_files = fields.One2many(
        'l10n_cl_edi.certification.batch_file',
        'certification_id',
        string='Archivos de Envío Consolidado'
    )
    
    batch_files_count = fields.Integer(
        compute='_compute_batch_files_count',
        string='Archivos Consolidados'
    )
    
    # Sets dinámicos disponibles para consolidación
    available_batch_set_ids = fields.One2many(
        'l10n_cl_edi.certification.available_set',
        'certification_process_id',
        string='Sets Disponibles para Consolidación',
        compute='_compute_available_batch_sets',
        help='Sets de documentos disponibles para generar envío consolidado'
    )

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
    # ELIMINADO: certification_partner_id ya no se usa (error arquitectónico resuelto)
    # El partner del SII (60803000-K) ya no se asigna directamente a documentos individuales.
    # Cada DTE individual usa un partner de certificación único del pool de partners precargados.
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
        Método mejorado para recuperar relaciones perdidas entre casos DTE y facturas
        después de actualizaciones de módulo o problemas de sincronización.
        """
        self.ensure_one()
        _logger.info(f"=== INICIANDO RECUPERACIÓN MEJORADA DE RELACIONES PERDIDAS ===")
        
        # 1. ESTRATEGIA 1: Buscar facturas ya vinculadas al proceso
        existing_linked_invoices = self.env['account.move'].search([
            ('l10n_cl_edi_certification_id', '=', self.id),
            ('state', '!=', 'cancel')
        ])
        
        if existing_linked_invoices:
            _logger.info(f"Encontradas {len(existing_linked_invoices)} facturas ya vinculadas al proceso")
            # Asegurar que estén en test_invoice_ids
            if not self.test_invoice_ids:
                self.test_invoice_ids = [(6, 0, existing_linked_invoices.ids)]
                _logger.info(f"Restauradas {len(existing_linked_invoices)} facturas en test_invoice_ids")
        
        # 2. ESTRATEGIA 2: Buscar casos DTE con facturas vinculadas pero sin relación con el proceso
        cases_with_invoices = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generated_account_move_id', '!=', False),
            ('generated_account_move_id.state', '!=', 'cancel')
        ])
        
        recovered_count = 0
        for case in cases_with_invoices:
            invoice = case.generated_account_move_id
            
            # Asegurar que la factura esté vinculada al proceso
            if not invoice.l10n_cl_edi_certification_id:
                invoice.l10n_cl_edi_certification_id = self.id
                _logger.info(f"Vinculada factura {invoice.name} al proceso de certificación")
                recovered_count += 1
            
            # Asegurar que esté en test_invoice_ids
            if invoice not in self.test_invoice_ids:
                self.test_invoice_ids = [(4, invoice.id)]  # Agregar sin reemplazar
                _logger.info(f"Agregada factura {invoice.name} a test_invoice_ids")
        
        # 3. ESTRATEGIA 3: Buscar facturas por patrones de referencia
        all_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id)
        ])
        
        for case in all_cases:
            if not case.generated_account_move_id:
                # Buscar facturas que podrían estar relacionadas
                potential_invoices = self.env['account.move'].search([
                    '|', '|', '|',
                    ('ref', '=', f'Certificación DTE - Caso {case.id}'),
                    ('ref', 'ilike', f'Caso {case.case_number_raw}'),
                    ('ref', 'ilike', f'SII {case.case_number_raw}'),
                    ('ref', 'ilike', f'Case {case.id}'),
                    ('state', '!=', 'cancel'),
                    ('move_type', 'in', ('out_invoice', 'out_refund'))
                ])
                
                if potential_invoices:
                    # Usar la primera factura encontrada
                    invoice = potential_invoices[0]
                    case.generated_account_move_id = invoice.id
                    
                    # Vincular al proceso
                    if not invoice.l10n_cl_edi_certification_id:
                        invoice.l10n_cl_edi_certification_id = self.id
                    
                    # Agregar a test_invoice_ids
                    if invoice not in self.test_invoice_ids:
                        self.test_invoice_ids = [(4, invoice.id)]
                    
                    _logger.info(f"Recuperada relación: Caso {case.case_number_raw} → Factura {invoice.name}")
                    recovered_count += 1
                    
                    # Actualizar estado del caso
                    if case.generation_status != 'generated':
                        case.generation_status = 'generated'
        
        # 4. ELIMINADO: Buscar facturas del partner SII (error arquitectónico resuelto)
        # Ya no usamos un partner único del SII para todos los documentos.
        # Los partners de certificación únicos se asignan individualmente desde datos precargados.
        
        # 5. VALIDACIÓN FINAL
        final_invoice_count = len(self.test_invoice_ids)
        final_case_count = len(all_cases.filtered(lambda c: c.generated_account_move_id))
        
        _logger.info(f"=== RECUPERACIÓN COMPLETADA ===")
        _logger.info(f"Facturas en test_invoice_ids: {final_invoice_count}")
        _logger.info(f"Casos con facturas vinculadas: {final_case_count}")
        _logger.info(f"Relaciones recuperadas en esta sesión: {recovered_count}")
        
        # Forzar recalculo de contadores
        self._compute_document_count()
        self._compute_dte_case_to_generate_count()
        
        return {
            'recovered_count': recovered_count,
            'total_invoices': final_invoice_count,
            'linked_cases': final_case_count
        }

    @api.model
    def default_get(self, fields_list):
        # Asegurar que solo haya un registro por compañía
        res = super(CertificationProcess, self).default_get(fields_list)
        res['company_id'] = self.env.company.id
        
        # Verificar si ya existe un registro para esta compañía
        existing_record = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if existing_record:
            # Si existe, sincronizar automáticamente
            try:
                existing_record._sync_all_dte_cases()
                existing_record.check_certification_status()
                _logger.info(f"Estado sincronizado en default_get para proceso {existing_record.id}")
            except Exception as e:
                _logger.warning(f"Error en sincronización default_get: {str(e)}")
        
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
            
            # Sincronizar estados de casos DTE
            self._sync_all_dte_cases()
            
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

    def read(self, fields=None, load='_classic_read'):
        """
        Override read method to automatically sync status when loading form data.
        """
        result = super().read(fields, load)
        
        # Solo ejecutar sincronización si se está leyendo un registro específico
        if len(self) == 1:
            try:
                self._sync_all_dte_cases()
                self.check_certification_status()
                _logger.info(f"Estado sincronizado automáticamente para proceso {self.id}")
            except Exception as e:
                _logger.warning(f"Error en sincronización automática: {str(e)}")
        
        return result

    def _sync_all_dte_cases(self):
        """
        Sincroniza todos los casos DTE del proceso de certificación.
        """
        self.ensure_one()
        
        # Obtener todos los casos DTE del proceso
        all_dte_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id)
        ])
        
        if all_dte_cases:
            _logger.info(f"Sincronizando {len(all_dte_cases)} casos DTE del proceso {self.id}")
            all_dte_cases._sync_generation_status()
        
    def _compute_caf_count(self):
        for record in self:
            record.caf_count = self.env['l10n_cl.dte.caf'].search_count([
                ('company_id', '=', record.company_id.id)
            ])
    
    def _compute_document_count(self):
        for record in self:
            record.document_count = len(record.test_invoice_ids)
    
    def _compute_iecv_books_count(self):
        for record in self:
            record.iecv_books_count = len(record.iecv_book_ids)
    
    def _compute_purchase_entries_count(self):
        for record in self:
            record.purchase_entries_count = len(record.purchase_entry_ids)
    
    def _compute_delivery_guide_book_count(self):
        for record in self:
            record.delivery_guide_book_count = len(record.delivery_guide_book_ids)
    
    def _compute_dte_case_to_generate_count(self):
        for record in self:
            record.dte_case_to_generate_count = self.env['l10n_cl_edi.certification.case.dte'].search_count([  # Actualizado
                ('parsed_set_id.certification_process_id', '=', record.id),
                ('generation_status', '=', 'pending')
            ])
    
    def _compute_batch_files_count(self):
        for record in self:
            record.batch_files_count = len(record.generated_batch_files)
    
    def _compute_available_batch_sets(self):
        """Detecta dinámicamente qué tipos de sets están disponibles basado en casos generados"""
        for record in self:
            sets_info = record._get_available_sets_info()
            
            # Crear registros transient para cada set disponible
            available_sets = []
            sequence = 10
            
            for set_key, set_data in sets_info.items():
                # Determinar secuencia para ordenar sets lógicamente
                set_sequences = {
                    'basico': 10,
                    'guias': 20,
                    'exportacion1': 30,
                    'exportacion2': 40,
                    'ventas': 50,
                    'compras': 60,
                    'libro_guias': 70,
                }
                
                available_sets.append((0, 0, {
                    'name': set_data['name'],
                    'set_type': set_key,
                    'document_count': set_data['count'],
                    'doc_types': ', '.join(set_data['doc_types']),
                    'icon': set_data['icon'],
                    'sequence': set_sequences.get(set_key, sequence),
                    'certification_process_id': record.id,
                }))
                sequence += 10
            
            record.available_batch_set_ids = available_sets
    
    def _get_available_sets_info(self):
        """Retorna información de sets disponibles con conteos de documentos"""
        # Obtener todos los casos DTE del proceso
        all_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generation_status', '=', 'generated')  # Solo casos con documentos generados
        ])
        
        # Mapeo de tipos de documento a categorías de sets
        doc_type_mappings = {
            'basico': {'types': ['33', '34', '56', '61'], 'name': 'SET BÁSICO', 'icon': 'fa-file-text'},
            'guias': {'types': ['52'], 'name': 'SET GUÍAS DE DESPACHO', 'icon': 'fa-truck'},
            'exportacion1': {'types': ['110'], 'name': 'SET EXPORTACIÓN 1', 'icon': 'fa-globe'},
            'exportacion2': {'types': ['111', '112'], 'name': 'SET EXPORTACIÓN 2', 'icon': 'fa-globe'},
        }
        
        available_sets = {}
        
        for set_key, set_info in doc_type_mappings.items():
            # Contar casos de este tipo
            matching_cases = all_cases.filtered(lambda c: c.document_type_code in set_info['types'])
            if matching_cases:
                available_sets[set_key] = {
                    'name': set_info['name'],
                    'icon': set_info['icon'],
                    'count': len(matching_cases),
                    'doc_types': list(set(matching_cases.mapped('document_type_code')))
                }
        
        # Agregar libros IECV si hay documentos generados
        if all_cases:
            # Libro de ventas
            sales_cases = all_cases.filtered(lambda c: c.document_type_code in ['33', '34', '56', '61'])
            if sales_cases:
                available_sets['ventas'] = {
                    'name': 'LIBRO DE VENTAS (IEV)',
                    'icon': 'fa-book',
                    'count': len(sales_cases),
                    'doc_types': list(set(sales_cases.mapped('document_type_code')))
                }
            
            # Libro de compras (simulado)
            available_sets['compras'] = {
                'name': 'LIBRO DE COMPRAS (IEC)',
                'icon': 'fa-book',
                'count': len(all_cases),  # Simula entradas de compra
                'doc_types': ['simulated']
            }
            
            # Libro de guías
            guide_cases = all_cases.filtered(lambda c: c.document_type_code in ['52'])
            if guide_cases:
                available_sets['libro_guias'] = {
                    'name': 'LIBRO DE GUÍAS',
                    'icon': 'fa-book',
                    'count': len(guide_cases),
                    'doc_types': list(set(guide_cases.mapped('document_type_code')))
                }
        
        return available_sets
    
    def get_batch_documents(self, document_types=None):
        """Obtiene documentos batch generados para envío consolidado
        
        Args:
            document_types (list): Lista de tipos de documento a filtrar (ej: ['33', '34'])
            
        Returns:
            recordset: Documentos batch (account.move) con nuevos folios CAF
        """
        # Obtener todos los casos DTE con documentos batch
        cases_with_batch = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.id),
            ('generated_batch_account_move_id', '!=', False)
        ])
        
        # Filtrar por tipos de documento si se especifica
        if document_types:
            cases_with_batch = cases_with_batch.filtered(
                lambda c: c.document_type_code in document_types
            )
        
        # Retornar los documentos batch
        batch_documents = cases_with_batch.mapped('generated_batch_account_move_id')
        
        _logger.info(f"Obtenidos {len(batch_documents)} documentos batch para tipos {document_types}")
        return batch_documents
    
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
        
        # 3. ELIMINADO: Partner del SII (error arquitectónico resuelto)
        # Ya no creamos un partner único del SII para todos los documentos.
        # Los partners de certificación únicos se cargan desde datos precargados.
        
        # 4. Asignar el diario creado al proceso
        self.write({
            'certification_journal_id': certification_journal.id,
        })
        
        # 5. Verificar estado automáticamente (no forzar estado)
        self.check_certification_status()
        
        # 6. Recargar la vista
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
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
        vals = {
            'name': 'Certificación SII',
            'code': 'CERT',
            'type': 'sale',
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
    
    # ELIMINADO: _create_certification_partner() ya no es necesario
    # El error arquitectónico del partner único del SII (60803000-K) ha sido resuelto.
    # Ahora cada DTE individual usa un partner de certificación único del pool de partners precargados.
    
    def action_view_iecv_books(self):
        """Acción para ver los libros IECV generados"""
        self.ensure_one()
        return {
            'name': _('Libros IECV'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.iecv_book',
            'view_mode': 'list,form',
            'domain': [('certification_process_id', '=', self.id)],
            'context': {'default_certification_process_id': self.id},
        }
    
    def action_view_delivery_guide_books(self):
        """Acción para ver los libros de guías de despacho generados"""
        self.ensure_one()
        return {
            'name': _('Libros de Guías de Despacho'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.delivery_guide_book',
            'view_mode': 'list,form',
            'domain': [('certification_process_id', '=', self.id)],
            'context': {'default_certification_process_id': self.id},
        }
    
    def action_create_delivery_guide_book(self):
        """Acción para crear un nuevo libro de guías de despacho"""
        self.ensure_one()
        return {
            'name': _('Crear Libro de Guías de Despacho'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.delivery_guide_book_generator_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_certification_process_id': self.id},
        }
    
    def action_recover_relationships(self):
        """Acción para recuperar relaciones perdidas manualmente"""
        self.ensure_one()
        
        # Ejecutar recuperación
        result = self._recover_lost_relationships()
        
        # Mostrar resultado
        if result['recovered_count'] > 0:
            message = f"Se recuperaron {result['recovered_count']} relaciones. "
            message += f"Total de facturas: {result['total_invoices']}, "
            message += f"Casos vinculados: {result['linked_cases']}"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Recuperación Exitosa'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Recuperación Completada'),
                    'message': 'No se encontraron relaciones perdidas para recuperar',
                    'type': 'info',
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
            # ELIMINADO: certification_partner_id (error arquitectónico resuelto)
            # Ya no validamos el partner único del SII, ahora usamos pool de partners de certificación
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

    def action_generate_iecv_books(self):
        """Abre el wizard para generar libros IECV"""
        self.ensure_one()
        
        if self.state != 'generation':
            raise UserError(_('Debe completar la generación de DTEs antes de crear los libros IECV'))
        
        if not self.test_invoice_ids:
            raise UserError(_('No hay documentos generados para incluir en los libros IECV'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Libros IECV'),
            'res_model': 'l10n_cl_edi.certification.iecv_generator_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_certification_process_id': self.id,
            }
        }
    
    def action_create_sample_purchase_entries(self):
        """Crea entradas de ejemplo para el libro de compras"""
        self.ensure_one()
        
        # Limpiar entradas existentes
        self.purchase_entry_ids.unlink()
        
        # Crear entradas de ejemplo
        self.env['l10n_cl_edi.certification.purchase_entry'].create_sample_purchase_entries(self.id)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Entradas de Compras Creadas'),
                'message': _('Se han creado %s entradas de ejemplo para el libro de compras') % len(self.purchase_entry_ids),
                'type': 'success',
                'sticky': False,
            }
        }

    # ==================== MÉTODOS DE GENERACIÓN BATCH ====================

    def action_generate_batch_basico(self):
        """Generar SET BÁSICO - Facturas y notas de crédito"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_basico(self.id)

    def action_generate_batch_guias(self):
        """Generar SET GUÍAS DE DESPACHO"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_guias(self.id)

    def action_generate_batch_ventas(self):
        """Generar LIBRO DE VENTAS (IEV)"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_ventas(self.id)

    def action_generate_batch_compras(self):
        """Generar LIBRO DE COMPRAS (IEC)"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_compras(self.id)

    def action_generate_batch_libro_guias(self):
        """Generar LIBRO DE GUÍAS"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_libro_guias(self.id)

    def action_generate_batch_exportacion1(self):
        """Generar SET EXPORTACIÓN 1"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_exportacion1(self.id)

    def action_generate_batch_exportacion2(self):
        """Generar SET EXPORTACIÓN 2"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file'].generate_batch_exportacion2(self.id)

    def action_view_batch_files(self):
        """Ver archivos de envío consolidado generados"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Archivos de Envío Consolidado'),
            'res_model': 'l10n_cl_edi.certification.batch_file',
            'view_mode': 'list,form',
            'domain': [('certification_id', '=', self.id)],
            'context': {'default_certification_id': self.id},
            'target': 'current',
        }