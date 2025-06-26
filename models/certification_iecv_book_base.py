# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class CertificationIECVBookBase(models.Model):
    _name = 'l10n_cl_edi.certification.iecv_book.base'
    _inherit = ['l10n_cl.edi.util']
    _description = 'Libro Electrónico de Compras y Ventas - Certificación SII'
    _order = 'create_date desc'
    
    # Relación con proceso de certificación
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        ondelete='cascade'
    )
    
    # Configuración del libro
    book_type = fields.Selection([
        ('IEV', 'Información Electrónica de Ventas'),
        ('IEC', 'Información Electrónica de Compras')
    ], string='Tipo de Libro', required=True)
    
    period_year = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: datetime.now().year
    )
    
    period_month = fields.Integer(
        string='Mes', 
        required=True,
        default=lambda self: datetime.now().month
    )
    
    period_display = fields.Char(
        string='Período',
        compute='_compute_period_display',
        store=True
    )
    
    # Estado del libro
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('signed', 'Firmado'),
        ('error', 'Error')
    ], string='Estado', default='draft', tracking=True)
    
    # Archivos generados
    xml_file = fields.Binary(
        string='Archivo XML IECV',
        attachment=True
    )
    
    xml_filename = fields.Char(
        string='Nombre del Archivo XML',
        compute='_compute_xml_filename',
        store=True
    )
    
    # Resúmenes automáticos
    total_documents = fields.Integer(
        string='Total Documentos',
        compute='_compute_totals',
        store=True
    )
    
    total_net_amount = fields.Monetary(
        string='Monto Neto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    total_tax_amount = fields.Monetary(
        string='IVA Total',
        compute='_compute_totals', 
        store=True,
        currency_field='currency_id'
    )
    
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='certification_process_id.company_id.currency_id',
        store=True
    )
    
    # Información técnica
    error_message = fields.Text(string='Mensaje de Error')
    
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        readonly=True
    )
    
    @api.depends('period_year', 'period_month')
    def _compute_period_display(self):
        for record in self:
            if record.period_year and record.period_month:
                record.period_display = f"{record.period_year}-{record.period_month:02d}"
            else:
                record.period_display = ""
    
    @api.depends('book_type', 'period_display')
    def _compute_xml_filename(self):
        for record in self:
            if record.book_type and record.period_display:
                company_rut = record.certification_process_id.company_id.vat.replace('-', '') if record.certification_process_id.company_id.vat else 'SINRUT'
                record.xml_filename = f"LIBRO_{record.book_type}_{company_rut}_{record.period_display}.xml"
            else:
                record.xml_filename = ""
    
    @api.depends('certification_process_id', 'book_type', 'period_year', 'period_month')
    def _compute_totals(self):
        """Calcula totales basados en los documentos incluidos"""
        for record in self:
            if record.book_type == 'IEV':
                # Libro de Ventas: usar DTEs generados
                invoices = record._get_sales_documents()
                record.total_documents = len(invoices)
                record.total_net_amount = sum(invoices.mapped('amount_untaxed'))
                record.total_tax_amount = sum(invoices.mapped('amount_tax'))
                record.total_amount = sum(invoices.mapped('amount_total'))
            elif record.book_type == 'IEC':
                # Libro de Compras: usar entradas específicas
                entries = record._get_purchase_entries()
                record.total_documents = len(entries)
                record.total_net_amount = sum(entries.mapped('amount_net_affected'))
                record.total_tax_amount = sum(entries.mapped('amount_tax'))
                record.total_amount = sum(entries.mapped('amount_total'))
            else:
                record.total_documents = 0
                record.total_net_amount = 0
                record.total_tax_amount = 0
                record.total_amount = 0
    
    def _get_sales_documents(self):
        """Obtiene documentos de venta para IEV
        
        IMPORTANTE: Usa documentos batch si están disponibles (con nuevos folios CAF)
        """
        if not self.certification_process_id:
            return self.env['account.move']
        
        # PRIORIDAD 1: Intentar obtener documentos batch (con nuevos folios CAF)
        batch_docs = self.certification_process_id.get_batch_documents(['33', '34', '56', '61'])
        
        if batch_docs:
            _logger.info(f"Usando {len(batch_docs)} documentos BATCH para IEV (nuevos folios CAF)")
            sales_docs = batch_docs.filtered(
                lambda x: x.move_type in ('out_invoice', 'out_refund') and x.state == 'posted'
            )
        else:
            _logger.info("No hay documentos batch, usando documentos individuales para IEV")
            # FALLBACK: Usar documentos individuales si no hay batch
            sales_docs = self.certification_process_id.test_invoice_ids.filtered(
                lambda x: x.move_type in ('out_invoice', 'out_refund') and x.state == 'posted'
            )
        
        # Filtrar por período
        if self.period_year and self.period_month:
            sales_docs = sales_docs.filtered(
                lambda x: x.invoice_date and 
                         x.invoice_date.year == self.period_year and
                         x.invoice_date.month == self.period_month
            )
        
        return sales_docs
    
    def _get_purchase_entries(self):
        """Obtiene entradas de compra para IEC del proceso de certificación activo"""
        if not self.certification_process_id:
            return self.env['l10n_cl_edi.certification.purchase_entry']
        
        # Obtener todas las entradas de compra del proceso de certificación
        purchase_entries = self.certification_process_id.purchase_entry_ids
        
        # Para entradas de certificación no aplicamos filtro por período
        # ya que son datos fijos del set de pruebas
        
        _logger.info(f"Procesando {len(purchase_entries)} entradas de compra para el libro IEC")
        return purchase_entries.sorted('sequence')
    
    def name_get(self):
        """Personaliza el nombre mostrado del registro"""
        result = []
        for record in self:
            name = f"{record.book_type} - {record.period_display}"
            if record.state == 'error':
                name += " (Error)"
            elif record.state == 'signed':
                name += " (Firmado)"
            result.append((record.id, name))
        return result
