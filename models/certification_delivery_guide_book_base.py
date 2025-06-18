# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class CertificationDeliveryGuideBookBase(models.Model):
    _name = 'l10n_cl_edi.certification.delivery_guide_book.base'
    _inherit = ['l10n_cl.edi.util']
    _description = 'Libro de Guías de Despacho - Certificación SII'
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
        ('LGD', 'Libro de Guías de Despacho')
    ], string='Tipo de Libro', default='LGD', required=True)
    
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
        string='Archivo XML Libro Guías',
        attachment=True
    )
    
    xml_filename = fields.Char(
        string='Nombre del Archivo XML',
        compute='_compute_xml_filename',
        store=True
    )
    
    # Resúmenes automáticos
    total_guides = fields.Integer(
        string='Total Guías',
        compute='_compute_totals',
        store=True
    )
    
    total_normal_guides = fields.Integer(
        string='Guías Normales',
        compute='_compute_totals',
        store=True
    )
    
    total_invoiced_guides = fields.Integer(
        string='Guías Facturadas',
        compute='_compute_totals',
        store=True
    )
    
    total_cancelled_guides = fields.Integer(
        string='Guías Anuladas',
        compute='_compute_totals',
        store=True
    )
    
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    # Campos de auditoría
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        readonly=True
    )
    
    error_message = fields.Text(
        string='Mensaje de Error',
        readonly=True
    )
    
    # Campos relacionados con la empresa
    company_id = fields.Many2one(
        related='certification_process_id.company_id',
        string='Empresa',
        store=True,
        readonly=True
    )
    
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Moneda',
        readonly=True
    )
    
    # Clasificación de guías
    guide_classification = fields.Text(
        compute='_compute_guide_classification',
        string='Clasificación de Guías'
    )
    
    @api.depends('period_year', 'period_month')
    def _compute_period_display(self):
        for record in self:
            if record.period_year and record.period_month:
                record.period_display = f"{record.period_year}-{record.period_month:02d}"
            else:
                record.period_display = False
    
    @api.depends('book_type', 'period_display')
    def _compute_xml_filename(self):
        for record in self:
            if record.book_type and record.period_display:
                record.xml_filename = f"LGD_{record.period_display}.xml"
            else:
                record.xml_filename = False
    
    @api.depends('certification_process_id')
    def _compute_totals(self):
        for record in self:
            if not record.certification_process_id:
                record.update({
                    'total_guides': 0,
                    'total_normal_guides': 0,
                    'total_invoiced_guides': 0,
                    'total_cancelled_guides': 0,
                    'total_amount': 0,
                })
                continue
            
            # Obtener clasificación de guías
            classified_guides = record._classify_delivery_guides()
            
            record.total_normal_guides = len(classified_guides.get('normal', []))
            record.total_invoiced_guides = len(classified_guides.get('invoiced', []))
            record.total_cancelled_guides = len(classified_guides.get('cancelled', []))
            record.total_guides = record.total_normal_guides + record.total_invoiced_guides + record.total_cancelled_guides
            
            # Calcular monto total
            total_amount = 0
            for guides in classified_guides.values():
                for guide in guides:
                    total_amount += record._calculate_guide_amount(guide)
            
            record.total_amount = total_amount
    
    @api.depends('certification_process_id')
    def _compute_guide_classification(self):
        for record in self:
            if not record.certification_process_id:
                record.guide_classification = "No hay proceso de certificación vinculado"
                continue
            
            classified_guides = record._classify_delivery_guides()
            
            classification_text = []
            for status, guides in classified_guides.items():
                if guides:
                    status_name = {
                        'normal': 'Normales',
                        'invoiced': 'Facturadas en Período',
                        'cancelled': 'Anuladas'
                    }.get(status, status.title())
                    
                    classification_text.append(f"{status_name}: {len(guides)} guías")
            
            record.guide_classification = "\n".join(classification_text) if classification_text else "No hay guías para clasificar"
    
    def _get_delivery_guides(self):
        """
        Obtiene las guías de despacho del proceso de certificación.
        """
        self.ensure_one()
        
        # Buscar casos DTE de tipo 52 (guías de despacho)
        guide_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
            ('document_type_code', '=', '52'),
            ('generated_stock_picking_id', '!=', False)
        ])
        
        return guide_cases.mapped('generated_stock_picking_id')
    
    def _get_case_dte_for_guide(self, guide):
        """
        Obtiene el caso DTE que generó una guía.
        """
        return self.env['l10n_cl_edi.certification.case.dte'].search([
            ('generated_stock_picking_id', '=', guide.id)
        ], limit=1)
    
    def _calculate_guide_amount(self, guide):
        """
        Calcula el monto total de una guía de despacho.
        Para guías que no constituyen venta, el monto es 0.
        Para guías de venta, suma los valores de los items.
        """
        if not guide or not guide.move_ids:
            return 0
        
        # Obtener el caso DTE para determinar si es venta
        case_dte = self._get_case_dte_for_guide(guide)
        if not case_dte:
            return 0
        
        # Si es traslado interno, monto es 0
        if 'TRASLADO' in (case_dte.dispatch_motive_raw or '').upper():
            return 0
        
        # Si es venta, calcular basado en items
        total_amount = 0
        for item in case_dte.item_ids:
            total_amount += item.quantity * item.price_unit
            # Aplicar descuento si existe
            if item.discount_percent:
                total_amount *= (1 - item.discount_percent / 100)
        
        return total_amount
    
    def _get_period_start(self):
        """Obtiene la fecha de inicio del período."""
        return datetime(self.period_year, self.period_month, 1).date()
    
    def _get_period_end(self):
        """Obtiene la fecha de fin del período."""
        if self.period_month == 12:
            next_month = datetime(self.period_year + 1, 1, 1)
        else:
            next_month = datetime(self.period_year, self.period_month + 1, 1)
        
        return (next_month - timedelta(days=1)).date()
    
    def _get_default_date(self):
        """Obtiene fecha por defecto del período."""
        return f"{self.period_year}-{self.period_month:02d}-15"
    
    def _get_period_display_for_xml(self):
        """Obtiene período en formato XML (AAAA-MM)."""
        return f"{self.period_year}-{self.period_month:02d}"
    
    def name_get(self):
        result = []
        for record in self:
            name = f"Libro Guías {record.period_display or 'Sin período'}"
            if record.state == 'signed':
                name += " (Firmado)"
            elif record.state == 'error':
                name += " (Error)"
            result.append((record.id, name))
        return result