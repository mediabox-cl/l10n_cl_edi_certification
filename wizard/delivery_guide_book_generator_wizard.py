# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class DeliveryGuideBookGeneratorWizard(models.TransientModel):
    _name = 'l10n_cl_edi.certification.delivery_guide_book_generator_wizard'
    _description = 'Wizard para Generar Libro de Guías de Despacho'
    
    # Campos principales
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        default=lambda self: self._get_default_certification_process()
    )
    
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
        compute='_compute_period_display'
    )
    
    # Vista previa
    guide_preview = fields.Html(
        compute='_compute_guide_preview',
        string='Vista Previa de Guías'
    )
    
    guides_found = fields.Integer(
        compute='_compute_guide_stats',
        string='Guías Encontradas'
    )
    
    guides_normal = fields.Integer(
        compute='_compute_guide_stats',
        string='Guías Normales'
    )
    
    guides_invoiced = fields.Integer(
        compute='_compute_guide_stats',
        string='Guías Facturadas'
    )
    
    guides_cancelled = fields.Integer(
        compute='_compute_guide_stats',
        string='Guías Anuladas'
    )
    
    # Estados
    can_generate = fields.Boolean(
        compute='_compute_can_generate',
        string='Puede Generar'
    )
    
    validation_message = fields.Text(
        compute='_compute_can_generate',
        string='Mensaje de Validación'
    )
    
    @api.model
    def _get_default_certification_process(self):
        """Obtiene el proceso de certificación por defecto"""
        process = self.env['l10n_cl_edi.certification.process'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        return process.id if process else False
    
    @api.depends('period_year', 'period_month')
    def _compute_period_display(self):
        for record in self:
            if record.period_year and record.period_month:
                record.period_display = f"{record.period_year}-{record.period_month:02d}"
            else:
                record.period_display = ""
    
    @api.depends('certification_process_id')
    def _compute_guide_stats(self):
        for record in self:
            if not record.certification_process_id:
                record.update({
                    'guides_found': 0,
                    'guides_normal': 0,
                    'guides_invoiced': 0,
                    'guides_cancelled': 0,
                })
                continue
            
            # Crear un libro temporal para obtener estadísticas
            temp_book = self.env['l10n_cl_edi.certification.delivery_guide_book'].new({
                'certification_process_id': record.certification_process_id.id,
                'period_year': record.period_year,
                'period_month': record.period_month,
            })
            
            try:
                _logger.info(f"WIZARD DEBUG: Iniciando cálculo para proceso {record.certification_process_id.id}")
                _logger.info(f"WIZARD DEBUG: Período {record.period_year}-{record.period_month:02d}")
                
                classified_guides = temp_book._classify_delivery_guides()
                
                record.guides_normal = len(classified_guides.get('normal', []))
                record.guides_invoiced = len(classified_guides.get('invoiced', []))
                record.guides_cancelled = len(classified_guides.get('cancelled', []))
                record.guides_found = record.guides_normal + record.guides_invoiced + record.guides_cancelled
                
                _logger.info(f"WIZARD DEBUG: Resultado - Normal: {record.guides_normal}, Facturadas: {record.guides_invoiced}, Anuladas: {record.guides_cancelled}, Total: {record.guides_found}")
                
            except Exception as e:
                _logger.error(f"WIZARD DEBUG: Error calculando estadísticas de guías: {str(e)}")
                import traceback
                _logger.error(f"WIZARD DEBUG: Traceback: {traceback.format_exc()}")
                record.update({
                    'guides_found': 0,
                    'guides_normal': 0,
                    'guides_invoiced': 0,
                    'guides_cancelled': 0,
                })
    
    @api.depends('certification_process_id', 'guides_found')
    def _compute_can_generate(self):
        for record in self:
            if not record.certification_process_id:
                record.can_generate = False
                record.validation_message = "Debe seleccionar un proceso de certificación"
                continue
            
            if record.guides_found == 0:
                record.can_generate = False
                record.validation_message = "No se encontraron guías de despacho para el período seleccionado"
                continue
            
            # Verificar que exista certificado digital
            certificate = self.env['certificate.certificate'].search([
                ('company_id', '=', record.certification_process_id.company_id.id),
                ('is_valid', '=', True)
            ], limit=1)
            
            if not certificate:
                record.can_generate = False
                record.validation_message = "No hay certificado digital válido para la empresa"
                continue
            
            record.can_generate = True
            record.validation_message = f"Listo para generar libro con {record.guides_found} guías"
    
    @api.depends('certification_process_id', 'guides_found', 'guides_normal', 'guides_invoiced', 'guides_cancelled')
    def _compute_guide_preview(self):
        for record in self:
            if not record.certification_process_id or record.guides_found == 0:
                record.guide_preview = "<p>No hay guías para mostrar</p>"
                continue
            
            # Crear un libro temporal para vista previa
            temp_book = self.env['l10n_cl_edi.certification.delivery_guide_book'].new({
                'certification_process_id': record.certification_process_id.id,
                'period_year': record.period_year,
                'period_month': record.period_month,
            })
            
            try:
                classified_guides = temp_book._classify_delivery_guides()
                record.guide_preview = record._build_preview_html(classified_guides, temp_book)
                
            except Exception as e:
                _logger.error(f"Error generando vista previa: {str(e)}")
                record.guide_preview = f"<p>Error generando vista previa: {str(e)}</p>"
    
    def _build_preview_html(self, classified_guides, temp_book):
        """Construye HTML de vista previa"""
        html = ["<div style='font-family: Arial, sans-serif; font-size: 12px;'>"]
        
        # Resumen
        total_guides = sum(len(guides) for guides in classified_guides.values())
        html.append(f"<h4>Resumen del Libro de Guías</h4>")
        html.append(f"<p><strong>Período:</strong> {self.period_display}</p>")
        html.append(f"<p><strong>Total de guías:</strong> {total_guides}</p>")
        
        # Tabla de clasificación
        html.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #ddd;'>")
        html.append("<tr style='background-color: #f5f5f5;'>")
        html.append("<th style='border: 1px solid #ddd; padding: 8px;'>Categoría</th>")
        html.append("<th style='border: 1px solid #ddd; padding: 8px;'>Cantidad</th>")
        html.append("<th style='border: 1px solid #ddd; padding: 8px;'>Casos</th>")
        html.append("</tr>")
        
        categories = {
            'normal': 'Guías Normales',
            'invoiced': 'Guías Facturadas',
            'cancelled': 'Guías Anuladas'
        }
        
        for status, name in categories.items():
            guides = classified_guides.get(status, [])
            count = len(guides)
            
            # Obtener números de casos
            case_numbers = []
            for guide in guides:
                case_dte = temp_book._get_case_dte_for_guide(guide)
                if case_dte:
                    case_numbers.append(case_dte.case_number_raw)
            
            html.append(f"<tr>")
            html.append(f"<td style='border: 1px solid #ddd; padding: 8px;'>{name}</td>")
            html.append(f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{count}</td>")
            html.append(f"<td style='border: 1px solid #ddd; padding: 8px;'>{', '.join(case_numbers) if case_numbers else 'Ninguno'}</td>")
            html.append(f"</tr>")
        
        html.append("</table>")
        
        # Notas importantes
        html.append("<div style='margin-top: 15px; padding: 10px; background-color: #fff3cd; border: 1px solid #ffeaa7;'>")
        html.append("<h5>Notas Importantes del SET 4:</h5>")
        html.append("<ul>")
        html.append("<li><strong>Caso 4329507-1:</strong> Traslado interno entre bodegas (Normal)</li>")
        html.append("<li><strong>Caso 4329507-2:</strong> Venta que se facturó en el período (Facturada)</li>")
        html.append("<li><strong>Caso 4329507-3:</strong> Venta que fue anulada (Anulada)</li>")
        html.append("</ul>")
        html.append("</div>")
        
        html.append("</div>")
        
        return ''.join(html)
    
    def action_generate_delivery_guide_book(self):
        """Genera el libro de guías de despacho"""
        self.ensure_one()
        
        if not self.can_generate:
            raise UserError(self.validation_message)
        
        _logger.info(f"=== INICIANDO GENERACIÓN LIBRO GUÍAS DESDE WIZARD ===")
        _logger.info(f"Proceso: {self.certification_process_id.id}")
        _logger.info(f"Período: {self.period_display}")
        _logger.info(f"Guías encontradas: {self.guides_found}")
        
        # Verificar si ya existe un libro para este período
        existing_book = self.env['l10n_cl_edi.certification.delivery_guide_book'].search([
            ('certification_process_id', '=', self.certification_process_id.id),
            ('period_year', '=', self.period_year),
            ('period_month', '=', self.period_month)
        ], limit=1)
        
        if existing_book:
            # Preguntar al usuario si quiere sobrescribir
            return {
                'type': 'ir.actions.act_window',
                'name': _('Libro Existente'),
                'res_model': 'l10n_cl_edi.certification.delivery_guide_book',
                'res_id': existing_book.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'message': _('Ya existe un libro para este período. Puede regenerarlo o modificarlo.')
                }
            }
        
        # Crear nuevo libro
        book = self.env['l10n_cl_edi.certification.delivery_guide_book'].create({
            'certification_process_id': self.certification_process_id.id,
            'period_year': self.period_year,
            'period_month': self.period_month,
        })
        
        _logger.info(f"Libro creado con ID: {book.id}")
        
        # Generar XML automáticamente
        book.action_generate_xml()
        
        _logger.info(f"✅ Libro de guías generado exitosamente")
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Libro de Guías Generado'),
            'res_model': 'l10n_cl_edi.certification.delivery_guide_book',
            'res_id': book.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_preview_only(self):
        """Solo muestra la vista previa sin generar"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vista Previa - Libro de Guías'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }