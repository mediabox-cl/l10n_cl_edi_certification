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
                
                if document and document.l10n_cl_dte_status == 'accepted':
                    docs_accepted += 1
            
            record.progress_display = f"{docs_accepted}/{total_cases}"
            record.batch_ready = (docs_accepted == total_cases)

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