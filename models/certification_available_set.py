from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class CertificationAvailableSet(models.TransientModel):
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
    
    document_count = fields.Integer(
        string='Cantidad de Documentos',
        help='Número de documentos que incluirá este set'
    )
    
    doc_types = fields.Char(
        string='Tipos de Documento',
        help='Códigos de tipos de documento incluidos'
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
    def _compute_state(self):
        """Calcula el estado basado en el archivo batch"""
        for record in self:
            if record.batch_file_id:
                if record.batch_file_id.state == 'generated':
                    record.state = 'generated'
                elif record.batch_file_id.state == 'error':
                    record.state = 'error'
                else:
                    record.state = 'available'
            else:
                record.state = 'available'
    
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