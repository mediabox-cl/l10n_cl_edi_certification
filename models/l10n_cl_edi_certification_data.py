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

    @api.depends('set_type_raw', 'attention_number')
    def _compute_name(self):
        for record in self:
            name = record.set_type_raw or 'Set Desconocido'
            if record.attention_number:
                name += f" (Atención: {record.attention_number})"
            record.name = name

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

class CertificationCaseDTE(models.Model):
    _name = 'l10n_cl_edi.certification.case.dte'
    _description = 'Define un Caso DTE a generar desde el Set de Pruebas'
    _order = 'parsed_set_id, case_number_raw'

    parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set', string='Set Parseado',
        required=True, ondelete='cascade', index=True)
    case_number_raw = fields.Char(string='Número de Caso SII (Raw)', index=True)
    
    # Document Details
    document_type_raw = fields.Char(string='Tipo Documento (Raw)')
    # Ideally, this would be a M2O to l10n_latam.document.type after ensuring all types exist
    document_type_code = fields.Char(string='Código Tipo Documento (Normalizado)', help="Ej: 33, 34, 52, 56, 61, 110, 111, 112") 

    item_ids = fields.One2many(
        'l10n_cl_edi.certification.case.dte.item', 'case_dte_id',
        string='Ítems del Documento')
    global_discount_percent = fields.Float(string='Descuento Global (%)')
    
    reference_ids = fields.One2many(
        'l10n_cl_edi.certification.case.dte.reference', 'case_dte_id',
        string='Referencias del Documento')

    # Guia de Despacho specific
    dispatch_motive_raw = fields.Text(string='Motivo Traslado (Raw)')
    dispatch_transport_type_raw = fields.Text(string='Tipo de Traslado (Raw)')

    # Export Document specific
    export_reference_text = fields.Text(string='Texto Referencia Exportación')
    export_currency_raw = fields.Char(string='Moneda Operación (Raw)')
    export_payment_terms_raw = fields.Char(string='Forma de Pago Exportación (Raw)')
    export_sale_modality_raw = fields.Text(string='Modalidad de Venta (Raw)')
    export_sale_clause_raw = fields.Char(string='Cláusula de Venta (Raw)')
    export_total_sale_clause_amount = fields.Float(string='Total Cláusula Venta')
    export_transport_way_raw = fields.Char(string='Vía de Transporte (Raw)')
    export_loading_port_raw = fields.Char(string='Puerto Embarque (Raw)')
    export_unloading_port_raw = fields.Char(string='Puerto Desembarque (Raw)')
    export_tare_uom_raw = fields.Char(string='Unidad Medida Tara (Raw)')
    export_gross_weight_uom_raw = fields.Char(string='Unidad Peso Bruto (Raw)')
    export_net_weight_uom_raw = fields.Char(string='Unidad Peso Neto (Raw)')
    # Add fields for actual weight values if they are parsed separately

    raw_text_block = fields.Text(string='Bloque de Texto Original del Caso')
    
    generated_account_move_id = fields.Many2one(
        'account.move', string='Documento Odoo Generado', readonly=True, copy=False)
    generation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('generated', 'Generado'),
        ('error', 'Error al Generar')
    ], string='Estado Generación', default='pending', copy=False)
    error_message = fields.Text(string='Mensaje de Error', readonly=True, copy=False)

    
    def action_view_case_detail(self):
        """Abre la vista detallada del caso DTE."""
        self.ensure_one()
        return {
            'name': _('Detalle del Caso DTE'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl_edi.certification.case.dte',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_generate_single_document(self):
        """Genera sólo este documento DTE específico."""
        self.ensure_one()
        
        if self.generation_status != 'pending':
            raise UserError(_("Este documento ya ha sido procesado o está en error."))
        
        certification_process = self.parsed_set_id.certification_process_id
        
        try:
            # Asegurarse que estamos en el estado correcto
            if certification_process.state not in ['data_loaded', 'generation']:
                certification_process.state = 'data_loaded'
            
            # Generar el documento
            certification_process._create_move_from_dte_case(self)
            
            # Verificar el estado del proceso de certificación
            certification_process.check_certification_status()
            
            # Notificar éxito
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('DTE generado'),
                    'message': _('El documento %s ha sido generado correctamente.') % self.case_number_raw,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            # Registrar error y notificar
            self.write({
                'generation_status': 'error',
                'error_message': str(e)
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error al generar DTE'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

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

class CertificationCaseDTEReference(models.Model):
    _name = 'l10n_cl_edi.certification.case.dte.reference'
    _description = 'Referencia para un Caso DTE del Set de Pruebas'
    _order = 'case_dte_id, sequence'

    case_dte_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte', string='Caso DTE',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    reference_document_text_raw = fields.Text(string='Texto Documento Referenciado (Raw)')
    referenced_sii_case_number = fields.Char(string='Nº Caso SII Referenciado')
    # Campo de enlace directo al caso DTE referenciado
    referenced_case_dte_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte', 
        string='Caso DTE Referenciado',
        help='Enlace directo al caso DTE dentro del mismo proceso de certificación'
    )
    reason_raw = fields.Text(string='Razón Referencia (Raw)')
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