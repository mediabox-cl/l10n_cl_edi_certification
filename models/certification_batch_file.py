from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_repr
import base64
import logging
from lxml import etree
from datetime import datetime
import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)

class CertificationBatchFile(models.Model):
    _name = 'l10n_cl_edi.certification.batch_file'
    _description = 'Archivo de Envío Consolidado SII'
    _order = 'create_date desc'
    
    certification_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        ondelete='cascade'
    )
    
    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo del archivo consolidado'
    )
    
    set_type = fields.Selection([
        ('basico', 'SET BÁSICO'),
        ('guias', 'SET GUÍAS DE DESPACHO'),
        ('facturas_compra', 'SET FACTURAS DE COMPRA'),
        ('ventas', 'LIBRO DE VENTAS (IEV)'),
        ('compras', 'LIBRO DE COMPRAS (IEC)'),
        ('libro_guias', 'LIBRO DE GUÍAS'),
        ('exportacion1', 'SET EXPORTACIÓN 1'),
        ('exportacion2', 'SET EXPORTACIÓN 2'),
    ], string='Tipo de Set', required=True)
    
    xml_content = fields.Text(
        string='Contenido XML',
        help='Contenido XML del archivo consolidado'
    )
    
    file_data = fields.Binary(
        string='Archivo XML',
        attachment=True,
        help='Archivo XML codificado en base64'
    )
    
    filename = fields.Char(
        string='Nombre del Archivo',
        help='Nombre del archivo XML para descarga'
    )
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('error', 'Error')
    ], string='Estado', default='draft')
    
    document_count = fields.Integer(
        string='Cantidad de Documentos',
        help='Número de DTEs incluidos en el envío consolidado'
    )
    
    error_message = fields.Text(
        string='Mensaje de Error',
        help='Detalle del error si la generación falló'
    )
    
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        default=fields.Datetime.now
    )
    
    def action_download_file(self):
        """Acción para descargar el archivo XML consolidado"""
        self.ensure_one()
        
        if not self.file_data:
            raise UserError(_('No hay archivo disponible para descargar.'))
        
        # Sin cambio de estado - mantener 'generated' para permitir múltiples descargas
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&download=true&filename={self.filename}',
            'target': 'self',
        }
    
    def action_regenerate(self):
        """Regenerar el archivo consolidado recuperando automáticamente documentos faltantes"""
        self.ensure_one()
        _logger.info(f"=== REGENERANDO CONSOLIDADO {self.set_type.upper()} ===")
        
        # 1. Primero intentar recuperar documentos batch faltantes automáticamente
        _logger.info("PASO 1: Recuperando documentos batch faltantes...")
        try:
            self._recover_missing_batch_documents(
                self.certification_id.id, 
                self.set_type, 
                parsed_set_id=getattr(self, 'parsed_set_id', None)
            )
        except Exception as e:
            _logger.warning(f"Advertencia en recuperación automática: {str(e)}")
        
        # 2. Luego regenerar el consolidado con todos los documentos disponibles
        _logger.info("PASO 2: Regenerando consolidado...")
        generation_method = getattr(self.certification_id, f'action_generate_batch_{self.set_type}', None)
        if generation_method:
            parsed_set_id = getattr(self, 'parsed_set_id', None)
            if parsed_set_id:
                return generation_method(parsed_set_id=parsed_set_id)
            else:
                return generation_method()
        else:
            raise UserError(_('Método de generación no encontrado para el tipo de set: %s') % self.set_type)

    def action_recover_missing_batch_documents(self):
        """Recuperar documentos batch faltantes sin regenerar"""
        self.ensure_one()
        return self.env['l10n_cl_edi.certification.batch_file']._recover_missing_batch_documents(
            self.certification_id.id, self.set_type, parsed_set_id=getattr(self, 'parsed_set_id', None)
        )
    
    @api.model
    def create(self, vals):
        """Override create para generar nombre del archivo automáticamente"""
        if not vals.get('filename') and vals.get('set_type'):
            company = self.env['l10n_cl_edi.certification.process'].browse(vals.get('certification_id')).company_id
            rut = company.vat.replace('-', '').replace('.', '') if company.vat else 'UNKNOWN'
            set_type_upper = vals['set_type'].upper()
            vals['filename'] = f"{set_type_upper}_{rut}.xml"
        
        return super().create(vals)

    # ==================== MÉTODOS DE GENERACIÓN BATCH ====================

    @api.model
    def generate_batch_basico(self, certification_process_id, parsed_set_id=None):
        """Generar SET BÁSICO - Facturas y notas de crédito"""
        return self._generate_batch_file(certification_process_id, 'basico', 'SET BÁSICO', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_guias(self, certification_process_id, parsed_set_id=None):
        """Generar SET GUÍAS DE DESPACHO"""
        return self._generate_batch_file(certification_process_id, 'guias', 'SET GUÍAS DE DESPACHO', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_facturas_compra(self, certification_process_id, parsed_set_id=None):
        """Generar SET FACTURAS DE COMPRA"""
        return self._generate_batch_file(certification_process_id, 'facturas_compra', 'SET FACTURAS DE COMPRA', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_ventas(self, certification_process_id, parsed_set_id=None):
        """Generar LIBRO DE VENTAS (IEV)"""
        return self._generate_iecv_book(certification_process_id, 'ventas', 'LIBRO DE VENTAS (IEV)', 'IEV', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_compras(self, certification_process_id, parsed_set_id=None):
        """Generar LIBRO DE COMPRAS (IEC)"""
        return self._generate_iecv_book(certification_process_id, 'compras', 'LIBRO DE COMPRAS (IEC)', 'IEC', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_libro_guias(self, certification_process_id, parsed_set_id=None):
        """Generar LIBRO DE GUÍAS"""
        return self._generate_iecv_book(certification_process_id, 'libro_guias', 'LIBRO DE GUÍAS', 'LIBRO_GUIAS', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_exportacion1(self, certification_process_id, parsed_set_id=None):
        """Generar SET EXPORTACIÓN 1"""
        return self._generate_batch_file(certification_process_id, 'exportacion1', 'SET EXPORTACIÓN 1', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_exportacion2(self, certification_process_id, parsed_set_id=None):
        """Generar SET EXPORTACIÓN 2"""
        return self._generate_batch_file(certification_process_id, 'exportacion2', 'SET EXPORTACIÓN 2', parsed_set_id=parsed_set_id)

    @api.model
    def generate_batch_facturas_compra(self, certification_process_id, parsed_set_id=None):
        """Generar CONSOLIDADO FACTURAS DE COMPRA"""
        return self._generate_batch_file(certification_process_id, 'facturas_compra', 'CONSOLIDADO FACTURAS DE COMPRA', parsed_set_id=parsed_set_id)

    def _generate_batch_file(self, certification_process_id, set_type, name, parsed_set_id=None):
        """Motor principal de generación de archivos consolidados"""
        _logger.info(f"=== INICIANDO GENERACIÓN BATCH {set_type.upper()} ===")
        
        # Obtener proceso de certificación
        process = self.env['l10n_cl_edi.certification.process'].browse(certification_process_id)
        if not process.exists():
            raise UserError(_('Proceso de certificación no encontrado'))

        try:
            # 1. Validar prerequisitos
            self._validate_ready_for_batch_generation(process, set_type, parsed_set_id=parsed_set_id)
            
            # 2. Regenerar documentos del set con nuevos folios
            regenerated_documents = self._regenerate_test_documents(process, set_type, parsed_set_id=parsed_set_id)
            
            # 3. Generar nodos DTE frescos para el consolidado
            dte_nodes = self._generate_fresh_dte_nodes(regenerated_documents)
            
            # 4. Construir XML consolidado
            consolidated_xml = self._build_consolidated_setdte(process, dte_nodes, set_type)
            
            # 5. Crear archivo batch
            batch_file = self.create({
                'certification_id': certification_process_id,
                'name': name,
                'set_type': set_type,
                'xml_content': consolidated_xml,
                'file_data': base64.b64encode(consolidated_xml.encode('ISO-8859-1')),
                'document_count': len(dte_nodes),
                'state': 'generated'
            })
            
            _logger.info(f"Archivo batch {set_type} generado exitosamente con {len(dte_nodes)} documentos")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Archivo Consolidado Generado'),
                    'message': _('Se generó exitosamente %s con %d documentos') % (name, len(dte_nodes)),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error generando archivo batch {set_type}: {str(e)}")
            
            # Crear registro de error
            self.create({
                'certification_id': certification_process_id,
                'name': f"{name} (Error)",
                'set_type': set_type,
                'state': 'error',
                'error_message': str(e)
            })
            
            raise UserError(_('Error generando archivo consolidado: %s') % str(e))

    def _validate_ready_for_batch_generation(self, process, set_type, parsed_set_id=None):
        """Validar que los documentos estén aceptados por SII para consolidación"""
        _logger.info(f"Validando prerequisitos SII para set {set_type}")
        
        # 1. Obtener casos DTE con documentos para este tipo de set
        relevant_cases = self._get_relevant_cases_for_set_type(process, set_type, parsed_set_id=parsed_set_id)
        if not relevant_cases:
            raise UserError(_('No se encontraron casos DTE para el tipo de set: %s') % set_type)
        
        # 2. Verificar que tienen documentos individuales generados (factura O guía)
        cases_without_docs = relevant_cases.filtered(
            lambda c: not c.generated_account_move_id and not c.generated_stock_picking_id
        )
        if cases_without_docs:
            case_numbers = ', '.join(cases_without_docs.mapped('case_number_raw'))
            raise UserError(_('Los siguientes casos no tienen documentos generados: %s') % case_numbers)
        
        # 3. CRÍTICO: Verificar estado SII - solo aceptados pueden ir a batch
        accepted_docs = []
        rejected_docs = []
        pending_docs = []
        
        for case in relevant_cases:
            # Obtener el documento correcto (factura o guía)
            doc = case.generated_account_move_id or case.generated_stock_picking_id
            if not doc:
                continue
                
            status = doc.l10n_cl_dte_status
            
            # Para certificación, considerar documentos en estados válidos como "aceptados"
            if status in ['not_sent', 'accepted', 'objected', 'manual']:
                accepted_docs.append(case)
            elif status in ['rejected', 'cancelled']:
                rejected_docs.append(case)
            else:
                pending_docs.append(case)
        
        # Solo permitir si TODOS están aceptados
        if rejected_docs:
            case_numbers = ', '.join([c.case_number_raw for c in rejected_docs])
            doc_statuses = [c.generated_account_move_id.l10n_cl_dte_status if c.generated_account_move_id else c.generated_stock_picking_id.l10n_cl_dte_status for c in rejected_docs]
            raise UserError(_(
                'Los siguientes documentos están RECHAZADOS por SII y deben corregirse antes de la consolidación: %s\n\n'
                'Estado SII: %s'
            ) % (case_numbers, ', '.join(doc_statuses)))
        
        if pending_docs:
            case_numbers = ', '.join([c.case_number_raw for c in pending_docs])
            doc_statuses = [c.generated_account_move_id.l10n_cl_dte_status if c.generated_account_move_id else c.generated_stock_picking_id.l10n_cl_dte_status for c in pending_docs]
            raise UserError(_(
                'Los siguientes documentos están PENDIENTES de aprobación SII: %s\n\n'
                'Estado SII: %s\n\n'
                'Debe esperar a que SII los acepte antes de generar envío consolidado.'
            ) % (case_numbers, ', '.join(doc_statuses)))
        
        _logger.info(f"Validación exitosa: {len(accepted_docs)} documentos aceptados por SII para set {set_type}")

    def _get_relevant_cases_for_set_type(self, process, set_type, parsed_set_id=None):
        """Obtener casos DTE relevantes según el tipo de set basado en sets de pruebas reales"""
        _logger.info(f"Obteniendo casos para set tipo: {set_type}")
        
        # Si se especifica un parsed_set_id, usar solo ese set específico
        if parsed_set_id:
            parsed_set = self.env['l10n_cl_edi.certification.parsed_set'].browse(parsed_set_id)
            if not parsed_set.exists():
                _logger.warning(f"Set específico no encontrado: {parsed_set_id}")
                return self.env['l10n_cl_edi.certification.case.dte']
            
            _logger.info(f"Usando set específico: {parsed_set.name}")
            all_relevant_cases = parsed_set.dte_case_ids
        else:
            # Lógica original para compatibilidad con otros métodos
            # Mapeo inverso: de tipos de consolidación a tipos de set normalizados
            consolidation_to_normalized = {
                'basico': ['basic', 'exempt_invoice'],
                'guias': ['dispatch_guide'],
                'facturas_compra': ['purchase_invoice'],  # Para consolidado SetDTE de facturas de compra
                'exportacion1': ['export_documents'],  # Todos los documentos del set de exportación 1
                'exportacion2': ['export_documents'],  # Todos los documentos del set de exportación 2
                'ventas': ['basic', 'exempt_invoice'],  # Para libro de ventas
                'compras': ['basic', 'exempt_invoice'],  # Para libro de compras (independiente)
                'libro_guias': ['dispatch_guide'],  # Para libro de guías
            }
            
            normalized_types = consolidation_to_normalized.get(set_type, [])
            if not normalized_types:
                _logger.warning(f"Tipo de set no mapeado: {set_type}")
                return self.env['l10n_cl_edi.certification.case.dte']
            
            # Obtener parsed sets del tipo normalizado
            parsed_sets = self.env['l10n_cl_edi.certification.parsed_set'].search([
                ('certification_process_id', '=', process.id),
                ('set_type_normalized', 'in', normalized_types)
            ])
            _logger.info(f"Sets encontrados para {set_type}: {len(parsed_sets)} ({[s.name for s in parsed_sets]})")
            
            # Obtener todos los casos de esos sets
            all_relevant_cases = self.env['l10n_cl_edi.certification.case.dte']
            for parsed_set in parsed_sets:
                all_relevant_cases |= parsed_set.dte_case_ids
        
        # CAMBIO: No filtrar por tipos de documento - incluir TODOS los documentos del set
        # Los consolidados deben contener todos los documentos que correspondan al set completo
        relevant_cases = all_relevant_cases
        
        _logger.info(f"Casos relevantes para {set_type}: {len(relevant_cases)}")
        for case in relevant_cases:
            _logger.info(f"  - Caso {case.case_number_raw}: tipo {case.document_type_code} ({case.document_type_name})")
        
        return relevant_cases

    def _recover_missing_batch_documents(self, certification_process_id, set_type, parsed_set_id=None):
        """Recupera documentos batch faltantes buscando documentos existentes por nombre de caso"""
        _logger.info(f"=== RECUPERANDO DOCUMENTOS BATCH FALTANTES PARA {set_type.upper()} ===")
        
        # Obtener proceso de certificación
        process = self.env['l10n_cl_edi.certification.process'].browse(certification_process_id)
        if not process.exists():
            raise UserError(_('Proceso de certificación no encontrado'))

        # Obtener casos relevantes sin documentos batch
        relevant_cases = self._get_relevant_cases_for_set_type(process, set_type, parsed_set_id=parsed_set_id)
        missing_cases = relevant_cases.filtered(lambda c: not c.generated_batch_account_move_id)
        
        _logger.info(f"Casos sin documento batch: {len(missing_cases)} de {len(relevant_cases)}")
        
        recovered_count = 0
        for case in missing_cases:
            _logger.info(f"Intentando recuperar documento para caso: {case.case_number_raw}")
            
            # Buscar documento BATCH existente con criterios estrictos para evitar documentos individuales
            existing_docs = self.env['account.move'].search([
                ('company_id', '=', process.company_id.id),
                ('l10n_cl_edi_certification_id', '=', process.id),  # SOLO documentos de este proceso de certificación
                ('journal_id', '=', process.certification_journal_id.id),  # SOLO diario de certificación
                ('l10n_cl_reference_ids.reason', 'ilike', case.case_number_raw),  # Referencia al caso
                ('state', '=', 'posted'),
                ('l10n_latam_document_type_id.code', '=', case.document_type_code),
                # Excluir documentos que ya están vinculados a otros casos
                ('id', 'not in', relevant_cases.mapped('generated_batch_account_move_id').ids)
            ])
            
            if existing_docs:
                # Tomar el más reciente
                latest_doc = existing_docs.sorted('create_date', reverse=True)[0]
                _logger.info(f"  ✓ Documento encontrado: {latest_doc.name} (ID: {latest_doc.id})")
                
                # Verificar que sea el documento correcto comparando referencias
                case_ref_found = any(
                    case.case_number_raw in ref.reason for ref in latest_doc.l10n_cl_reference_ids
                )
                
                # Verificación adicional: que tenga referencia SET (primera referencia debe ser SET)
                has_set_reference = any(
                    ref.l10n_cl_reference_doc_type_selection == 'SET' for ref in latest_doc.l10n_cl_reference_ids
                )
                
                if case_ref_found and has_set_reference:
                    # Vincular al caso
                    case.write({'generated_batch_account_move_id': latest_doc.id})
                    recovered_count += 1
                    _logger.info(f"  ✓ Vinculado caso {case.case_number_raw} → {latest_doc.name}")
                else:
                    _logger.warning(f"  ⚠️  Documento {latest_doc.name} no es un documento batch válido")
            else:
                _logger.warning(f"  ❌ No se encontró documento para caso {case.case_number_raw}")
        
        _logger.info(f"✅ RECUPERACIÓN COMPLETADA: {recovered_count} documentos vinculados")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documentos Recuperados'),
                'message': _('Se recuperaron %d documentos batch faltantes') % recovered_count,
                'type': 'success' if recovered_count > 0 else 'warning',
            }
        }

    def _generate_iecv_book(self, certification_process_id, set_type, name, book_type, parsed_set_id=None):
        """Genera libros IECV usando documentos batch con nuevos folios CAF"""
        _logger.info(f"=== INICIANDO GENERACIÓN LIBRO {book_type.upper()} ===")
        
        # Obtener proceso de certificación
        process = self.env['l10n_cl_edi.certification.process'].browse(certification_process_id)
        if not process.exists():
            raise UserError(_('Proceso de certificación no encontrado'))

        try:
            # 1. Validar prerequisitos
            self._validate_ready_for_batch_generation(process, set_type)
            
            # 2. Asegurar que existan documentos batch para libros
            if set_type in ['ventas', 'compras']:
                relevant_cases = self._get_relevant_cases_for_set_type(process, set_type, parsed_set_id=parsed_set_id)
                # Para libros, necesitamos generar documentos batch si no existen
                for case in relevant_cases:
                    if not case.generated_batch_account_move_id:
                        _logger.info(f"Generando documento batch faltante para caso {case.case_number_raw}")
                        # Generar documento batch para este caso
                        generator = self.env['l10n_cl_edi.certification.document.generator'].create({
                            'dte_case_id': case.id,
                            'certification_process_id': process.id,
                            'for_batch': True
                        })
                        generator.generate_document(for_batch=True)
            
            # 3. Usar el sistema IECV existente para generar el libro con documentos batch
            iecv_book = self.env['l10n_cl_edi.certification.iecv_book'].create({
                'certification_process_id': certification_process_id,
                'book_type': book_type,
                'period_year': process.test_invoice_ids[0].invoice_date.year if process.test_invoice_ids else 2024,
                'period_month': process.test_invoice_ids[0].invoice_date.month if process.test_invoice_ids else 12,
            })
            
            # 4. Generar el XML del libro (usará automáticamente documentos batch)
            iecv_book.action_generate_xml()
            
            # 5. Crear archivo batch con el contenido del libro IECV
            if iecv_book.xml_file:
                xml_content = base64.b64decode(iecv_book.xml_file).decode('ISO-8859-1')
                
                batch_file = self.create({
                    'certification_id': certification_process_id,
                    'name': name,
                    'set_type': set_type,
                    'xml_content': xml_content,
                    'file_data': iecv_book.xml_file,  # Ya está en base64
                    'document_count': len(iecv_book._get_sales_documents()) if book_type == 'IEV' else len(iecv_book._get_purchase_entries()),
                    'state': 'generated'
                })
                
                _logger.info(f"Libro {book_type} generado exitosamente")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Libro Generado'),
                        'message': _('Se generó exitosamente %s') % name,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Error: No se pudo generar el XML del libro IECV'))
                
        except Exception as e:
            _logger.error(f"Error generando libro {book_type}: {str(e)}")
            
            # Crear registro de error
            self.create({
                'certification_id': certification_process_id,
                'name': f"{name} (Error)",
                'set_type': set_type,
                'state': 'error',
                'error_message': str(e)
            })
            
            raise UserError(_('Error generando libro: %s') % str(e))

    def _regenerate_test_documents(self, process, set_type, parsed_set_id=None):
        """Regenerar documentos del set con nuevos folios CAF"""
        _logger.info(f"Regenerando documentos para set {set_type}")
        
        relevant_cases = self._get_relevant_cases_for_set_type(process, set_type, parsed_set_id=parsed_set_id)
        
        # Ordenar casos para generar facturas antes que notas de crédito/débito
        # Esto es crucial para evitar errores de referencia
        def sort_key(case):
            doc_type = case.document_type_code
            # Facturas y guías primero (códigos 33, 34, 52, 110, etc.)
            if doc_type in ['33', '34', '52', '110']:
                return 1
            # Notas de crédito/débito después (códigos 56, 61, 111, 112)
            elif doc_type in ['56', '61', '111', '112']:
                return 2
            # Otros tipos al final
            else:
                return 3
        
        relevant_cases = relevant_cases.sorted(key=sort_key)
        _logger.info(f"Casos ordenados para generación: {[f'{c.case_number_raw}({c.document_type_code})' for c in relevant_cases]}")
        
        regenerated_documents = []
        
        for case in relevant_cases:
            try:
                # Utilizar el generador de documentos en modo batch
                generator = self.env['l10n_cl_edi.certification.document.generator'].create({
                    'dte_case_id': case.id,
                    'certification_process_id': process.id,
                    'for_batch': True
                })
                
                # Generar documento batch con nuevos folios CAF
                result = generator.generate_document(for_batch=True)
                
                # Obtener el documento generado para batch
                document = None
                if case.document_type_code == '52': # Guía de Despacho
                    document = case.generated_batch_stock_picking_id
                else:
                    document = case.generated_batch_account_move_id

                if not document:
                    _logger.warning(f"No se pudo obtener documento batch para caso {case.case_number_raw}")
                    continue
                
                # Asegurar que el documento esté confirmado (solo para account.move)
                if document._name == 'account.move' and document.state == 'draft':
                    document.action_post()
                
                # Verificar que tenga XML DTE (l10n_cl_dte_file existe en ambos modelos)
                if document.l10n_cl_dte_file:
                    regenerated_documents.append(document)
                    _logger.info(f"Documento regenerado para caso {case.case_number_raw}")
                else:
                    _logger.warning(f"Documento sin XML DTE para caso {case.case_number_raw}")
                
            except Exception as e:
                _logger.error(f"Error regenerando documento para caso {case.case_number_raw}: {str(e)}")
                continue
        
        if not regenerated_documents:
            raise UserError(_('No se pudieron regenerar documentos para el set %s') % set_type)
        
        return regenerated_documents

    def _generate_fresh_dte_nodes(self, documents):
        """Generar nodos DTE frescos para consolidado usando templates de Odoo"""
        _logger.info(f"Generando DTEs frescos para {len(documents)} documentos en consolidado")
        
        dte_nodes = []
        
        for document in documents:
            try:
                _logger.info(f"Generando DTE fresco para documento {document.name}")
                
                # Generar DTE fresco usando el template base de Odoo
                fresh_dte_xml = self._generate_single_dte_for_consolidado(document)
                
                # DEBUG: Log del XML generado para entender la estructura
                _logger.info(f"XML generado para {document.name} (primeros 500 chars): {fresh_dte_xml[:500]}")
                
                # Parsear el DTE generado
                dte_root = etree.fromstring(fresh_dte_xml.encode('ISO-8859-1'))
                
                # DEBUG: Log de la estructura del XML parseado
                _logger.info(f"Root tag: {dte_root.tag}")
                _logger.info(f"Root children: {[child.tag for child in dte_root]}")
                
                # Buscar el nodo DTE con múltiples estrategias
                dte_node = None
                
                # 1. Con namespace SiiDte
                dte_node = dte_root.find('.//{http://www.sii.cl/SiiDte}DTE')
                if dte_node is None:
                    # 2. Sin namespace específico
                    dte_node = dte_root.find('.//DTE')
                if dte_node is None:
                    # 3. Buscar por tag local
                    for elem in dte_root.iter():
                        if elem.tag.endswith('DTE'):
                            dte_node = elem
                            break
                if dte_node is None:
                    # 4. Si el root es un DTE directamente
                    if dte_root.tag.endswith('DTE'):
                        dte_node = dte_root
                
                if dte_node is not None:
                    dte_nodes.append(dte_node)
                    _logger.info(f"✓ DTE fresco generado para documento {document.name}")
                else:
                    _logger.warning(f"⚠️ No se pudo extraer nodo DTE del documento fresco {document.name}")
                    _logger.warning(f"Estructura XML completa: {[elem.tag for elem in dte_root.iter()][:20]}")
                    
            except Exception as e:
                _logger.error(f"Error generando DTE fresco para documento {document.name}: {str(e)}")
                continue
        
        if not dte_nodes:
            raise UserError(_('No se pudieron generar DTEs frescos para el consolidado'))
        
        return dte_nodes
    
    def _generate_single_dte_for_consolidado(self, document):
        """Generar un DTE individual fresco para uso en consolidado"""
        # Usar el método estándar de Odoo para generar DTE
        # pero en el contexto del consolidado
        folio = int(document.l10n_latam_document_number)
        doc_id_number = 'F{}T{}'.format(folio, document.l10n_latam_document_type_id.code)
        
        # Generar barcode XML necesario para el DTE
        dte_barcode_xml = document._l10n_cl_get_dte_barcode_xml()
        
        # Renderizar DTE usando template base de Odoo
        dte_xml = self.env['ir.qweb']._render('l10n_cl_edi.dte_template', {
            'move': document,
            'format_vat': document._l10n_cl_format_vat,
            'get_cl_current_strftime': document._get_cl_current_strftime,
            'format_length': document._format_length,
            'format_uom': document._format_uom,
            'float_repr': float_repr,
            'float_rr': document._float_repr_float_round,
            'doc_id': doc_id_number,
            'caf': document.l10n_latam_document_type_id._get_caf_file(document.company_id.id, folio),
            'amounts': document._l10n_cl_get_amounts(),
            'withholdings': document._l10n_cl_get_withholdings(),
            'dte': dte_barcode_xml['ted'],
            '__keep_empty_lines': True,
        })
        
        # Firmar el DTE individual
        digital_signature = document.company_id.sudo()._get_digital_signature(user_id=self.env.user.id)
        signed_dte = document._sign_full_xml(
            dte_xml, 
            digital_signature, 
            doc_id_number,
            'env',  # Tipo de envío
            False   # No es voucher
        )
        
        return signed_dte
    
    def _extract_dte_nodes(self, documents):
        """OBSOLETO: Método anterior que extraía DTEs existentes"""
        # Ahora usamos _generate_fresh_dte_nodes en su lugar
        return self._generate_fresh_dte_nodes(documents)

    def _build_consolidated_setdte(self, process, dte_nodes, set_type):
        """Construir XML consolidado con carátula y múltiples DTEs"""
        _logger.info(f"Construyendo XML consolidado para {len(dte_nodes)} DTEs")
        
        # Crear estructura base del EnvioDTE con namespaces correctos
        nsmap = {
            None: 'http://www.sii.cl/SiiDte',  # Namespace por defecto
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
        
        envio_root = etree.Element('EnvioDTE', nsmap=nsmap)
        envio_root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation', 
                       'http://www.sii.cl/SiiDte EnvioDTE_v10.xsd')
        envio_root.set('version', '1.0')
        
        # Crear SetDTE
        set_dte = etree.SubElement(envio_root, 'SetDTE')
        set_dte.set('ID', 'SetDoc')
        
        # Crear carátula consolidada
        caratula = self._build_consolidated_caratula(process, dte_nodes, set_type)
        set_dte.append(caratula)
        
        # Agregar todos los nodos DTE
        for dte_node in dte_nodes:
            set_dte.append(dte_node)
        
        # Construir XML consolidado manualmente (bypass template incompatible)
        company = process.company_id
        digital_signature_sudo = company.sudo()._get_digital_signature(user_id=self.env.user.id)
        
        # Convertir estructura lxml a string SIN declaración XML
        try:
            xml_string = etree.tostring(
                envio_root, 
                encoding='ISO-8859-1', 
                xml_declaration=False, 
                pretty_print=True
            ).decode('ISO-8859-1')
            _logger.info(f"XML consolidado generado exitosamente con {len(dte_nodes)} DTEs")
        except Exception as e:
            _logger.error(f"Error generando XML consolidado: {str(e)}")
            raise UserError(_('Error al construir XML consolidado: %s') % str(e))
        
        # Firmar usando el método estándar de Odoo (que agregará la declaración XML)
        signed_xml = self.env['account.move']._sign_full_xml(
            xml_string, 
            digital_signature_sudo, 
            'SetDoc',
            'env',  # Tipo de envío
            False   # No es voucher
        )
        
        _logger.info("XML consolidado firmado digitalmente")
        
        return signed_xml

    def _build_consolidated_caratula(self, process, dte_nodes, set_type):
        """Generar carátula consolidada con SubTotDTE"""
        caratula = etree.Element('Caratula')
        caratula.set('version', '1.0')
        
        company = process.company_id
        
        # RutEmisor
        rut_emisor = etree.SubElement(caratula, 'RutEmisor')
        rut_emisor.text = self.env['account.move']._l10n_cl_format_vat(company.vat)
        
        # RutEnvia (del certificado digital)
        digital_signature_sudo = company.sudo()._get_digital_signature(user_id=self.env.user.id)
        rut_envia = etree.SubElement(caratula, 'RutEnvia')
        rut_envia.text = digital_signature_sudo.subject_serial_number if digital_signature_sudo else company.vat
        
        # RutReceptor (siempre SII)
        rut_receptor = etree.SubElement(caratula, 'RutReceptor')
        rut_receptor.text = '60803000-K'
        
        # FchResol y NroResol (datos de certificación)
        if company.l10n_cl_dte_resolution_date:
            fch_resol = etree.SubElement(caratula, 'FchResol')
            fch_resol.text = company.l10n_cl_dte_resolution_date.strftime('%Y-%m-%d')
        
        if company.l10n_cl_dte_resolution_number:
            nro_resol = etree.SubElement(caratula, 'NroResol')
            nro_resol.text = str(company.l10n_cl_dte_resolution_number)
        
        # TmstFirmaEnv
        tmst_firma = etree.SubElement(caratula, 'TmstFirmaEnv')
        tmst_firma.text = self.env['account.move']._get_cl_current_strftime()
        
        # Contar documentos por tipo para SubTotDTE usando método existente
        doc_counts = self._get_doc_counts(dte_nodes)
        
        # Agregar SubTotDTE para cada tipo
        for doc_type, count in doc_counts.items():
            subtot_dte = etree.SubElement(caratula, 'SubTotDTE')
            
            tipo_dte_elem = etree.SubElement(subtot_dte, 'TpoDTE')
            tipo_dte_elem.text = doc_type
            
            nro_doc_elem = etree.SubElement(subtot_dte, 'NroDTE')
            nro_doc_elem.text = str(count)
        
        return caratula
    
    def _get_doc_counts(self, dte_nodes):
        """
        Count documents by type for SubTotDTE elements.
        Returns dict with document type as key and count as value.
        """
        doc_counts = {}
        for dte_node in dte_nodes:
            # Extract document type from DTE node
            doc_encabezado = dte_node.find('.//{http://www.sii.cl/SiiDte}Encabezado')
            if doc_encabezado is not None:
                id_doc = doc_encabezado.find('.//{http://www.sii.cl/SiiDte}IdDoc')
                if id_doc is not None:
                    tipo_dte = id_doc.find('.//{http://www.sii.cl/SiiDte}TipoDTE')
                    if tipo_dte is not None:
                        doc_type = tipo_dte.text
                        doc_counts[doc_type] = doc_counts.get(doc_type, 0) + 1
        
        return doc_counts