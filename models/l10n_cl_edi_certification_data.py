# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CertificationParsedSet(models.Model):
    _name = 'l10n_cl_edi.certification.parsed_set'
    _description = 'Representa un Set parseado del archivo de Pruebas SII'
    _order = 'certification_process_id, sequence'

    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process', string='Proceso de Certificación',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    # ELIMINADO: Partner relacionado del proceso de certificación (error arquitectónico)
    # Ya no usamos un partner único del SII para todos los documentos.
    # Cada caso DTE individual obtiene su propio partner de certificación único.

    name = fields.Char(string='Nombre del Set', compute='_compute_name', store=True)
    set_type_raw = fields.Char(string='Tipo de Set (Raw)')
    set_type_normalized = fields.Selection([
        ('basic', 'Set Básico'),
        ('exempt_invoice', 'Set Factura Exenta'),
        ('dispatch_guide', 'Set Guía de Despacho'),
        ('export_documents', 'Set Documentos de Exportación'),
        ('sales_book', 'Set Libro de Ventas (Instruccional)'),
        ('guides_book', 'Set Libro de Guías (Instruccional)'),
        ('purchase_book', 'Set Libro de Compras'),
        ('unknown', 'Desconocido/Otro')
    ], string='Tipo de Set (Normalizado)', required=True)
    attention_number = fields.Char(string='Número de Atención SII')

    # Contenido específico del Set
    instructional_content_ids = fields.One2many(
        'l10n_cl_edi.certification.instructional_set', 'parsed_set_id',
        string='Contenido Instruccional')
    dte_case_ids = fields.One2many(
        'l10n_cl_edi.certification.case.dte', 'parsed_set_id',
        string='Casos DTE a Generar')
    purchase_book_entry_ids = fields.One2many(
        'l10n_cl_edi.certification.purchase_book.entry', 'parsed_set_id',
        string='Entradas Libro de Compras')

    raw_header_text = fields.Text(string='Texto Cabecera Original del Set')
    # Could also store the full raw text block of the set if needed for reprocessing
    
    # Campos para consolidación batch
    progress_display = fields.Char(
        string='Progreso',
        compute='_compute_batch_progress',
        help='Progreso en formato X/Y documentos aceptados'
    )
    
    batch_ready = fields.Boolean(
        string='Listo para Batch',
        compute='_compute_batch_progress',
        help='Todos los documentos están aceptados por SII'
    )
    
    # Campo para verificar si existe archivo batch generado
    batch_file_exists = fields.Boolean(
        string='Archivo Batch Existe',
        compute='_compute_batch_file_exists',
        help='Indica si ya existe un archivo batch generado para este set'
    )
    
    # Campos relacionados al archivo batch
    filename = fields.Char(
        string='Nombre del Archivo',
        compute='_compute_batch_file_exists',
        help='Nombre del archivo batch generado'
    )
    
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        compute='_compute_batch_file_exists',
        help='Fecha de generación del archivo batch'
    )

    @api.depends('set_type_raw', 'attention_number')
    def _compute_name(self):
        for record in self:
            name = record.set_type_raw or 'Set Desconocido'
            if record.attention_number:
                name += f" (Atención: {record.attention_number})"
            record.name = name
    
    @api.depends('dte_case_ids', 'dte_case_ids.generated_account_move_id', 'dte_case_ids.generated_account_move_id.l10n_cl_dte_status', 'dte_case_ids.generated_stock_picking_id', 'dte_case_ids.generated_stock_picking_id.l10n_cl_dte_status')
    def _compute_batch_progress(self):
        """Calcula el progreso de documentos aceptados por SII"""
        for record in self:
            total_cases = len(record.dte_case_ids)
            docs_accepted = 0
            
            if total_cases == 0:
                record.progress_display = '0/0'
                record.batch_ready = False
                continue
            
            for case in record.dte_case_ids:
                # Determinar el documento generado (account.move o stock.picking)
                document = None
                if case.generated_account_move_id:
                    document = case.generated_account_move_id
                elif case.generated_stock_picking_id:
                    document = case.generated_stock_picking_id
                
                # Para certificación, considerar documentos generados (no necesariamente aceptados por SII)
                # Los estados válidos incluyen: not_sent, accepted, objected (con objeciones), manual
                if document and document.l10n_cl_dte_status in ['not_sent', 'accepted', 'objected', 'manual']:
                    docs_accepted += 1
            
            record.progress_display = f"{docs_accepted}/{total_cases}"
            record.batch_ready = (docs_accepted == total_cases)

    @api.depends('certification_process_id', 'set_type_normalized')
    def _compute_batch_file_exists(self):
        """Verifica si existe un archivo batch generado para este set"""
        for record in self:
            # Mapear el tipo de set al tipo usado en batch_file
            set_type_mapping = {
                'basic': 'basico',
                'dispatch_guide': 'guias',
                'export_documents': 'exportacion1',  # Asumir exportacion1 por defecto
                'sales_book': 'ventas',
                'guides_book': 'libro_guias',
                'purchase_book': 'compras',
            }
            
            batch_set_type = set_type_mapping.get(record.set_type_normalized)
            if not batch_set_type:
                record.batch_file_exists = False
                record.filename = ''
                record.generation_date = False
                continue
            
            # Buscar archivo batch existente
            batch_file = self.env['l10n_cl_edi.certification.batch_file'].search([
                ('certification_id', '=', record.certification_process_id.id),
                ('set_type', '=', batch_set_type),
                ('state', '=', 'generated')
            ], limit=1)
            
            record.batch_file_exists = bool(batch_file)
            record.filename = batch_file.filename if batch_file else ''
            record.generation_date = batch_file.generation_date if batch_file else False

    def action_generate_batch(self):
        """Generar archivo XML consolidado para este set"""
        self.ensure_one()
        
        # Determinar el método de generación basado en el nombre del set
        # Los sets de exportación necesitan manejo especial
        if 'EXPORTACIÓN 1' in self.name.upper():
            method_name = 'action_generate_batch_exportacion1'
        elif 'EXPORTACIÓN 2' in self.name.upper():
            method_name = 'action_generate_batch_exportacion2'
        else:
            # Mapear otros tipos de set
            set_type_methods = {
                'basic': 'action_generate_batch_basico',
                'dispatch_guide': 'action_generate_batch_guias',
                'sales_book': 'action_generate_batch_ventas',
                'purchase_book': 'action_generate_batch_compras', 
                'guides_book': 'action_generate_batch_libro_guias',
                'export_documents': 'action_generate_batch_exportacion1',  # Default para export
            }
            
            method_name = set_type_methods.get(self.set_type_normalized)
            if not method_name:
                raise UserError(f'Tipo de set no soportado para consolidación: {self.set_type_normalized}')
        
        # Llamar al método en el proceso de certificación pasando el contexto del set
        certification_process = self.certification_process_id
        if hasattr(certification_process, method_name):
            method = getattr(certification_process, method_name)
            # Pasar el set específico como contexto para que solo procese SUS casos
            return method(parsed_set_id=self.id)
        else:
            raise UserError(f'Método de generación no encontrado: {method_name}')
    
    def action_reset_batch(self):
        """Resetea solo documentos batch para este set"""
        self.ensure_one()
        
        if not self.dte_case_ids:
            raise UserError(_('No hay casos DTE para resetear'))
        
        # Contar documentos batch antes del reset
        cases_with_batch = self.dte_case_ids.filtered(
            lambda c: c.generated_batch_account_move_id or c.generated_batch_stock_picking_id
        )
        
        _logger.info(f"🔄 RESET BATCH: Procesando {len(cases_with_batch)} casos con documentos batch en set {self.name}")
        
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
        set_type_mapping = {
            'basic': 'basico',
            'dispatch_guide': 'guias',
            'export_documents': 'exportacion1',
            'sales_book': 'ventas',
            'guides_book': 'libro_guias',
            'purchase_book': 'compras',
        }
        
        batch_set_type = set_type_mapping.get(self.set_type_normalized)
        if batch_set_type:
            batch_files = self.env['l10n_cl_edi.certification.batch_file'].search([
                ('certification_id', '=', self.certification_process_id.id),
                ('set_type', '=', batch_set_type)
            ])
            if batch_files:
                _logger.info(f"🗑️  Eliminando {len(batch_files)} archivo(s) batch para set {self.name}")
                batch_files.unlink()
        
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
    
    def action_regenerate_batch(self):
        """Regenera el archivo batch existente"""
        return self.action_generate_batch()
    
    def action_download_batch(self):
        """Descarga el archivo batch generado"""
        self.ensure_one()
        
        # Mapear tipo de set a tipo de batch_file
        set_type_mapping = {
            'basic': 'basico',
            'dispatch_guide': 'guias',
            'export_documents': 'exportacion1',
            'sales_book': 'ventas',
            'guides_book': 'libro_guias',
            'purchase_book': 'compras',
        }
        
        batch_set_type = set_type_mapping.get(self.set_type_normalized)
        if not batch_set_type:
            raise UserError(_('Tipo de set no soportado para descarga batch'))
        
        # Buscar archivo batch
        batch_file = self.env['l10n_cl_edi.certification.batch_file'].search([
            ('certification_id', '=', self.certification_process_id.id),
            ('set_type', '=', batch_set_type),
            ('state', '=', 'generated')
        ], limit=1)
        
        if not batch_file:
            raise UserError(_('No hay archivo batch generado para este set'))
        
        return batch_file.action_download_file()

class CertificationInstructionalSet(models.Model):
    _name = 'l10n_cl_edi.certification.instructional_set'
    _description = 'Contenido para Sets Instruccionales (Libro Ventas/Guías)'
    _order = 'parsed_set_id, sequence'

    parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set', string='Set Parseado',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    instructions_text = fields.Text(string='Instrucciones')
    general_observations = fields.Text(string='Observaciones Generales')

class CertificationCaseDTEItem(models.Model):
    _name = 'l10n_cl_edi.certification.case.dte.item'
    _description = 'Ítem para un Caso DTE del Set de Pruebas'
    _order = 'case_dte_id, sequence'

    case_dte_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte', string='Caso DTE',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    
    name = fields.Char(string='Nombre Ítem', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0)
    uom_raw = fields.Char(string='Unidad de Medida (Raw)')
    # uom_id = fields.Many2one('uom.uom', string='Unidad de Medida') # Ideal for mapping
    price_unit = fields.Float(string='Precio Unitario')
    discount_percent = fields.Float(string='Descuento (%)')
    is_exempt = fields.Boolean(string='¿Es Exento?')
    item_line_value = fields.Float(string='Valor Línea', help='Valor total de la línea (cantidad * precio unitario)')

class CertificationCaseDTEReference(models.Model):
    _name = 'l10n_cl_edi.certification.case.dte.reference'
    _description = 'Referencia para un Caso DTE del Set de Pruebas'
    _order = 'case_dte_id, sequence'

    case_dte_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte', string='Caso DTE',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    reference_document_text_raw = fields.Text(string='Texto Documento Referenciado (Raw)')
    referenced_document_type_raw = fields.Char(string='Tipo Documento Referenciado (Raw)')
    referenced_sii_case_number = fields.Char(string='Nº Caso SII Referenciado')
    # Campo de enlace directo al caso DTE referenciado
    referenced_case_dte_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte', 
        string='Caso DTE Referenciado',
        help='Enlace directo al caso DTE dentro del mismo proceso de certificación'
    )
    reason_raw = fields.Text(string='Razón Referencia (Raw)')
    reference_reason_raw = fields.Text(string='Razón Referencia (Raw - Alias)', help='Campo alternativo para compatibilidad')
    reference_code = fields.Selection([
        ('1', '1. Anula Documento Referenciado'),
        ('2', '2. Corrige Texto Documento Referenciado'),
        ('3', '3. Corrige Monto Documento Referenciado')
    ], string='Código Referencia SII', 
       help='Código SII para el tipo de referencia')

class CertificationPurchaseBookEntry(models.Model):
    _name = 'l10n_cl_edi.certification.purchase_book.entry'
    _description = 'Entrada para el Libro de Compras del Set de Pruebas'
    _order = 'parsed_set_id, sequence'
    
    parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set', string='Set Parseado',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    document_type_raw = fields.Char(string='Tipo Documento (Raw)')
    # document_type_code = fields.Char(string='Código Tipo Documento (Normalizado)') # Similar to DTE case
    folio = fields.Char(string='Folio')
    observations_raw = fields.Text(string='Observaciones (Raw)')
    amount_exempt = fields.Float(string='Monto Exento')
    amount_net_affected = fields.Float(string='Monto Afecto Neto')
    
    raw_text_lines = fields.Text(string='Líneas de Texto Originales')
    # Potentially link to a generated vendor bill if applicable
    # related_vendor_bill_id = fields.Many2one('account.move', string='Factura de Proveedor Generada')
    processing_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('processed', 'Procesado'), # If we create other records or just for data logging
        ('error', 'Error')
    ], string='Estado Procesamiento', default='pending', copy=False)