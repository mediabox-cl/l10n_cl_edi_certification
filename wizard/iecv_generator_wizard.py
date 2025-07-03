# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)

class IECVGeneratorWizard(models.TransientModel):
    _name = 'l10n_cl_edi.certification.iecv_generator_wizard'
    _description = 'Asistente para Generar Libros IECV'
    
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True
    )
    
    generate_iev = fields.Boolean(
        string='Generar Libro de Ventas (IEV)',
        default=True
    )
    
    generate_iec = fields.Boolean(
        string='Generar Libro de Compras (IEC)',
        default=True
    )
    
    period_date = fields.Date(
        string='Período',
        default=fields.Date.today,
        required=True
    )
    
    # Tipo de proceso (individual vs definitivo)
    process_type = fields.Selection([
        ('individual', 'Libros Individuales (Proceso Normal)'),
        ('definitivo', 'Libros Definitivos (Consolidado)')
    ], string='Tipo de Proceso', required=True, default='individual')
    
    # Información del proceso
    sales_documents_count = fields.Integer(
        string='Documentos de Venta Individuales',
        compute='_compute_process_info'
    )
    
    batch_documents_count = fields.Integer(
        string='Documentos de Venta Batch/Consolidados',
        compute='_compute_process_info'
    )
    
    purchase_entries_count = fields.Integer(
        string='Entradas de Compra',
        compute='_compute_process_info'
    )
    
    @api.depends('certification_process_id')
    def _compute_process_info(self):
        for record in self:
            if record.certification_process_id:
                # Contar documentos de venta individuales
                sales_docs = record.certification_process_id.test_invoice_ids.filtered(
                    lambda x: x.move_type in ('out_invoice', 'out_refund') and x.state == 'posted'
                )
                record.sales_documents_count = len(sales_docs)
                
                # Contar documentos batch/consolidados
                batch_docs = record.certification_process_id.get_batch_documents(['33', '34', '56', '61'])
                record.batch_documents_count = len(batch_docs) if batch_docs else 0
                
                # Contar entradas de compra
                record.purchase_entries_count = len(record.certification_process_id.purchase_entry_ids)
            else:
                record.sales_documents_count = 0
                record.batch_documents_count = 0
                record.purchase_entries_count = 0
    
    def action_generate_books(self):
        """Genera los libros IECV"""
        self.ensure_one()
        
        if not self.generate_iev and not self.generate_iec:
            raise UserError(_('Debe seleccionar al menos un tipo de libro para generar'))
        
        # Validaciones según tipo de proceso
        if self.process_type == 'definitivo':
            if self.generate_iev and self.batch_documents_count == 0:
                raise UserError(_('No hay documentos batch/consolidados disponibles para generar libros definitivos de venta'))
        
        generated_books = self.env['l10n_cl_edi.certification.iecv_book']
        
        try:
            # Generar Libro de Ventas (IEV)
            if self.generate_iev:
                iev_book = self._create_book('IEV')
                iev_book.action_generate_xml()
                generated_books |= iev_book
            
            # Generar Libro de Compras (IEC)
            if self.generate_iec:
                iec_book = self._create_book('IEC')
                iec_book.action_generate_xml()
                generated_books |= iec_book
            
            # Mostrar resultado
            book_names = ', '.join(generated_books.mapped('book_type'))
            process_label = 'DEFINITIVOS' if self.process_type == 'definitivo' else 'INDIVIDUALES'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Libros IECV Generados'),
                    'message': _('Se han generado exitosamente los libros %s: %s') % (process_label, book_names),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error generando libros IECV: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error generando libros IECV: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _create_book(self, book_type):
        """Crea un libro IECV del tipo especificado"""
        vals = {
            'certification_process_id': self.certification_process_id.id,
            'book_type': book_type,
            'period_year': self.period_date.year,
            'period_month': self.period_date.month,
            'process_type': self.process_type,
        }
        
        return self.env['l10n_cl_edi.certification.iecv_book'].create(vals)
