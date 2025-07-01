from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class CertificationAvailableSet(models.Model):
    _name = 'l10n_cl_edi.certification.available_set'
    _description = 'Set Disponible para Consolidación'
    _order = 'sequence, name'
    
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True
    )
    
    name = fields.Char(
        string='Nombre del Set',
        required=True
    )
    
    set_type = fields.Selection([
        ('basico', 'SET BÁSICO'),
        ('guias', 'SET GUÍAS DE DESPACHO'),
        ('ventas', 'LIBRO DE VENTAS (IEV)'),
        ('compras', 'LIBRO DE COMPRAS (IEC)'),
        ('libro_guias', 'LIBRO DE GUÍAS'),
        ('exportacion1', 'SET EXPORTACIÓN 1'),
        ('exportacion2', 'SET EXPORTACIÓN 2'),
    ], string='Tipo de Set', required=True)
    
    state = fields.Selection([
        ('available', 'Disponible para Generar'),
        ('generated', 'Generado'),
        ('error', 'Error')
    ], string='Estado', compute='_compute_state')
    
    # Campos de progreso (computed dinámicamente)
    total_cases = fields.Integer(
        string='Total Casos',
        compute='_compute_progress_stats',
        help='Número total de casos en el set'
    )
    
    docs_generated = fields.Integer(
        string='Documentos Generados',
        compute='_compute_progress_stats',
        help='Número de documentos ya generados'
    )
    
    docs_accepted = fields.Integer(
        string='Documentos Aceptados',
        compute='_compute_progress_stats',
        help='Número de documentos aceptados por SII'
    )
    
    docs_rejected = fields.Integer(
        string='Documentos Rechazados',
        compute='_compute_progress_stats',
        help='Número de documentos rechazados por SII'
    )
    
    docs_pending = fields.Integer(
        string='Documentos Pendientes',
        compute='_compute_progress_stats',
        help='Número de documentos pendientes en SII'
    )
    
    doc_types = fields.Char(
        string='Tipos de Documento',
        compute='_compute_progress_stats',
        help='Códigos de tipos de documento incluidos'
    )
    
    progress_display = fields.Char(
        string='Progreso',
        compute='_compute_progress_stats',
        help='Progreso en formato X/Y'
    )
    
    parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set',
        string='Set de Pruebas Original',
        help='Referencia al parsed set original'
    )
    
    attention_number = fields.Char(
        string='Número de Atención',
        help='Número de atención SII del set'
    )
    
    icon = fields.Char(
        string='Icono',
        default='fa-file'
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )
    
    # Campos relacionados al archivo generado
    batch_file_id = fields.Many2one(
        'l10n_cl_edi.certification.batch_file',
        string='Archivo Generado',
        compute='_compute_batch_file'
    )
    
    filename = fields.Char(
        related='batch_file_id.filename',
        string='Nombre del Archivo'
    )
    
    generation_date = fields.Datetime(
        related='batch_file_id.generation_date',
        string='Fecha de Generación'
    )
    
    error_message = fields.Text(
        related='batch_file_id.error_message',
        string='Mensaje de Error'
    )
    
    # Campo para verificar si existe archivo batch generado
    batch_file_exists = fields.Boolean(
        string='Archivo Batch Existe',
        compute='_compute_batch_file_exists',
        help='Indica si ya existe un archivo batch generado para este set'
    )
    
    @api.depends('certification_process_id', 'set_type')
    def _compute_batch_file(self):
        """Busca el archivo batch generado para este set"""
        for record in self:
            if record.certification_process_id and record.set_type:
                batch_file = self.env['l10n_cl_edi.certification.batch_file'].search([
                    ('certification_id', '=', record.certification_process_id.id),
                    ('set_type', '=', record.set_type)
                ], limit=1, order='create_date desc')
                record.batch_file_id = batch_file
            else:
                record.batch_file_id = False
    
    @api.depends('batch_file_id', 'batch_file_id.state')
    def _compute_batch_file_exists(self):
        """Verifica si existe un archivo batch generado"""
        for record in self:
            record.batch_file_exists = bool(record.batch_file_id and record.batch_file_id.state == 'generated')
    
    @api.depends('parsed_set_id', 'parsed_set_id.dte_case_ids', 'parsed_set_id.dte_case_ids.generated_account_move_id', 'parsed_set_id.dte_case_ids.generated_account_move_id.l10n_cl_dte_status', 'parsed_set_id.dte_case_ids.generated_stock_picking_id', 'parsed_set_id.dte_case_ids.generated_stock_picking_id.l10n_cl_dte_status')
    def _compute_progress_stats(self):
        """Calcula estadísticas de progreso dinámicamente"""
        for record in self:
            if not record.parsed_set_id:
                # Valores por defecto si no hay parsed_set
                record.total_cases = 0
                record.docs_generated = 0
                record.docs_accepted = 0
                record.docs_rejected = 0
                record.docs_pending = 0
                record.doc_types = ''
                record.progress_display = '0/0'
                continue
            
            # Analizar todos los casos del set
            total_cases = len(record.parsed_set_id.dte_case_ids)
            docs_generated = 0
            docs_accepted = 0
            docs_rejected = 0
            docs_pending = 0
            doc_types_set = set()
            
            for case in record.parsed_set_id.dte_case_ids:
                # Determinar el documento generado (account.move o stock.picking)
                document = None
                if case.generated_account_move_id:
                    document = case.generated_account_move_id
                elif case.generated_stock_picking_id:
                    document = case.generated_stock_picking_id
                
                if not document:
                    continue
                
                docs_generated += 1
                
                # Obtener estado SII y tipo de documento
                status = document.l10n_cl_dte_status
                
                # Para account.move usar l10n_latam_document_type_id, para stock.picking usar l10n_latam_document_type_id también
                if hasattr(document, 'l10n_latam_document_type_id') and document.l10n_latam_document_type_id:
                    doc_type = document.l10n_latam_document_type_id.code
                else:
                    # Fallback al código del caso
                    doc_type = case.document_type_code
                
                doc_types_set.add(doc_type)
                
                # Para certificación, considerar documentos en estados válidos como "aceptados"
                if status in ['draft', 'sent', 'accepted']:
                    docs_accepted += 1
                elif status in ['rejected', 'cancelled']:
                    docs_rejected += 1
                else:
                    docs_pending += 1
            
            # Asignar valores calculados
            record.total_cases = total_cases
            record.docs_generated = docs_generated
            record.docs_accepted = docs_accepted
            record.docs_rejected = docs_rejected
            record.docs_pending = docs_pending
            record.doc_types = ', '.join(sorted(doc_types_set))
            record.progress_display = f"{docs_accepted}/{total_cases}"
    
    @api.depends('docs_accepted', 'total_cases', 'docs_rejected', 'docs_pending', 'batch_file_id', 'batch_file_id.state')
    def _compute_state(self):
        """Calcula el estado basado en el progreso de documentos y archivo batch"""
        for record in self:
            # Si ya hay archivo batch generado, mostrar su estado
            if record.batch_file_id:
                if record.batch_file_id.state == 'generated':
                    record.state = 'generated'
                elif record.batch_file_id.state == 'error':
                    record.state = 'error'
                else:
                    record.state = 'available'
            else:
                # Estado basado en progreso de documentos
                if record.docs_accepted == record.total_cases and record.total_cases > 0:
                    record.state = 'available'  # Listo para generar
                else:
                    record.state = 'error'  # No disponible para generar
    
    def action_generate_set(self):
        """Genera el set consolidado"""
        self.ensure_one()
        
        # Mapear tipos de set a métodos de generación
        generation_methods = {
            'basico': 'action_generate_batch_basico',
            'guias': 'action_generate_batch_guias',
            'ventas': 'action_generate_batch_ventas',
            'compras': 'action_generate_batch_compras',
            'libro_guias': 'action_generate_batch_libro_guias',
            'exportacion1': 'action_generate_batch_exportacion1',
            'exportacion2': 'action_generate_batch_exportacion2',
        }
        
        method_name = generation_methods.get(self.set_type)
        if not method_name:
            raise UserError(_('Método de generación no encontrado para el tipo de set: %s') % self.set_type)
        
        # Llamar al método de generación en el proceso de certificación
        generation_method = getattr(self.certification_process_id, method_name)
        return generation_method()
    
    def action_download_file(self):
        """Descarga el archivo generado"""
        self.ensure_one()
        
        if not self.batch_file_id:
            raise UserError(_('No hay archivo generado para este set'))
        
        return self.batch_file_id.action_download_file()
    
    def action_regenerate(self):
        """Regenera el set"""
        self.ensure_one()
        
        if self.batch_file_id:
            # Eliminar archivo existente
            self.batch_file_id.unlink()
        
        # Generar nuevamente
        return self.action_generate_set()
    
    # Métodos alias para botones de la vista principal
    def action_regenerate_batch(self):
        """Alias para regenerar desde vista principal"""
        return self.action_regenerate()
    
    def action_download_batch(self):
        """Alias para descargar desde vista principal"""
        return self.action_download_file()
    
    def action_reset_batch(self):
        """Resetea solo documentos batch y permite regenerar con nueva lógica"""
        self.ensure_one()
        
        if not self.parsed_set_id:
            raise UserError(_('No hay set de pruebas asociado para resetear'))
        
        # Contar documentos batch antes del reset
        cases_with_batch = self.parsed_set_id.dte_case_ids.filtered(
            lambda c: c.generated_batch_account_move_id or c.generated_batch_stock_picking_id
        )
        
        _logger.info(f"🔄 RESET BATCH: Procesando {len(cases_with_batch)} casos con documentos batch")
        
        # Desvincular solo campos batch (no individuales)
        for case in cases_with_batch:
            case_updates = {}
            
            # Desvincular documento batch de facturas/notas
            if case.generated_batch_account_move_id:
                _logger.info(f"  ⚠️  Desvinculando factura batch: {case.generated_batch_account_move_id.name} del caso {case.case_number_raw}")
                case_updates['generated_batch_account_move_id'] = False
            
            # Desvincular documento batch de guías  
            if case.generated_batch_stock_picking_id:
                _logger.info(f"  ⚠️  Desvinculando guía batch: {case.generated_batch_stock_picking_id.name} del caso {case.case_number_raw}")
                case_updates['generated_batch_stock_picking_id'] = False
            
            # Aplicar cambios al caso
            if case_updates:
                case.write(case_updates)
        
        # Eliminar archivo batch existente si existe
        if self.batch_file_id:
            _logger.info(f"🗑️  Eliminando archivo batch: {self.batch_file_id.filename}")
            self.batch_file_id.unlink()
        
        _logger.info(f"✅ RESET BATCH COMPLETADO: Set {self.name} listo para regenerar")
        
        # Mostrar mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reset Completado'),
                'message': _('Documentos batch desvinculados. Puede generar nuevamente el XML.'),
                'type': 'success',
                'sticky': False,
            }
        }