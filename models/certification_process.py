from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging

_logger = logging.getLogger(__name__)

class CertificationProcess(models.Model):
    _name = 'l10n_cl.certification.process'
    _description = 'Proceso de Certificación SII'
    _rec_name = 'company_id'
    
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('setup', 'Configuración'),
        ('basic_test', 'Set Básico'),
        ('simulation', 'Simulación'),
        ('exchange', 'Intercambio'),
        ('printing', 'Muestras Impresión'),
        ('finished', 'Certificado')
    ], string='Estado', default='draft')
    
    # Información de certificación
    dte_email = fields.Char(related='company_id.l10n_cl_dte_email', readonly=False, string='Email DTE')
    resolution_number = fields.Char(related='company_id.l10n_cl_dte_resolution_number', readonly=False, string='Número Resolución SII')
    resolution_date = fields.Date(related='company_id.l10n_cl_dte_resolution_date', readonly=False, string='Fecha Resolución SII')
    sii_regional_office = fields.Selection(related='company_id.l10n_cl_sii_regional_office', readonly=False, string='Oficina Regional SII')
    dte_service_provider = fields.Selection(related='company_id.l10n_cl_dte_service_provider', readonly=False, string='Proveedor Servicio DTE')
    company_activity_ids = fields.Many2many(related='company_id.l10n_cl_company_activity_ids', readonly=False, string='Actividades Económicas')
    
    # Contador de documentos
    caf_count = fields.Integer(compute='_compute_caf_count', string='CAFs')
    document_count = fields.Integer(compute='_compute_document_count', string='Documentos')
    
    # Seguimiento de set de pruebas
    set_prueba_file = fields.Binary(string='Archivo Set de Pruebas')
    set_prueba_filename = fields.Char(string='Nombre del archivo')
    test_invoice_ids = fields.One2many('account.move', 'l10n_cl_certification_id', string='Documentos de Prueba')
    
    # Checklists
    has_digital_signature = fields.Boolean(compute='_compute_has_digital_signature', string='Firma Digital')
    has_company_activities = fields.Boolean(compute='_compute_has_company_activities', string='Actividades Económicas')
    has_required_cafs = fields.Boolean(compute='_compute_has_required_cafs', string='CAFs Requeridos')
    
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Crear un registro automáticamente si no existe y se solicita desde la acción del menú"""
        if self.env.context.get('create_if_not_exist'):
            existing = self.search([('company_id', '=', self.env.company.id)], limit=1)
            if not existing:
                self.create({'company_id': self.env.company.id})
        
        return super(CertificationProcess, self).search_read(domain=domain, fields=fields, 
                                                            offset=offset, limit=limit, order=order)
    @api.model
    def default_get(self, fields_list):
        # Asegurar que solo haya un registro por compañía
        res = super(CertificationProcess, self).default_get(fields_list)
        res['company_id'] = self.env.company.id
        return res
        
    def _compute_caf_count(self):
        for record in self:
            record.caf_count = self.env['l10n_cl.dte.caf'].search_count([
                ('company_id', '=', record.company_id.id)
            ])
    
    def _compute_document_count(self):
        for record in self:
            record.document_count = len(record.test_invoice_ids)
    
    def _compute_has_digital_signature(self):
        for record in self:
            record.has_digital_signature = bool(self.env['certificate.certificate'].search([
                ('company_id', '=', record.company_id.id),
                ('is_valid', '=', True)
            ], limit=1))
    
    def _compute_has_company_activities(self):
        for record in self:
            record.has_company_activities = bool(record.company_id.l10n_cl_company_activity_ids)
    
    def _compute_has_required_cafs(self):
        for record in self:
            # Verificar CAFs para los tipos de documento requeridos (33, 61, 56, 52)
            required_doc_types = ['33', '61', '56', '52']
            record.has_required_cafs = all(
                self.env['l10n_cl.dte.caf'].search_count([
                    ('company_id', '=', record.company_id.id),
                    ('l10n_latam_document_type_id.code', '=', doc_type),
                    ('status', '=', 'in_use')
                ]) > 0
                for doc_type in required_doc_types
            )
    
    def action_prepare_certification(self):
        """Prepara la base de datos para el proceso de certificación"""
        self.ensure_one()
        
        # 1. Crear/actualizar tipo de documento SET
        self._create_document_type_set()
        
        # 2. Actualizar estado
        self.state = 'setup'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Base de datos preparada'),
                'message': _('Se ha configurado el tipo de documento SET para referencias.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _create_document_type_set(self):
        """Crea o actualiza el tipo de documento SET para referencias de certificación"""
        doc_type_set = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if doc_type_set:
            # Actualizar el existente
            doc_type_set.write({
                'code': 'SET',
                'name': 'SET',
                'internal_type': 'invoice',
                'l10n_cl_active': True,
                'doc_code_prefix': 'SET'
            })
        else:
            # Crear nuevo
            chile = self.env.ref('base.cl')
            doc_type_set = self.env['l10n_latam.document.type'].create({
                'name': 'SET',
                'code': 'SET',
                'country_id': chile.id,
                'internal_type': 'invoice',
                'l10n_cl_active': True,
                'doc_code_prefix': 'SET',
                'sequence': 100
            })
        
        return doc_type_set
    
    def action_create_demo_cafs(self):
        """Crea CAFs de demostración para los tipos de documento requeridos"""
        self.ensure_one()
        
        # Verificar que estamos en modo SIIDEMO
        if self.company_id.l10n_cl_dte_service_provider != 'SIIDEMO':
            raise UserError(_('Para crear CAFs de demostración, primero debe configurar el Proveedor de Servicio DTE a SIIDEMO'))
        
        # Crear CAFs para los tipos de documento necesarios
        self.company_id._create_demo_caf_files()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('CAFs creados'),
                'message': _('Se han creado CAFs de demostración para los documentos requeridos.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_process_set_prueba(self):
        """Procesa el archivo de set de pruebas para crear los documentos solicitados"""
        self.ensure_one()
        
        if not self.set_prueba_file:
            raise UserError(_('Debe cargar un archivo de Set de Pruebas primero'))
        
        # Aquí iría la lógica para procesar el set de pruebas
        # Por ahora, simulamos que se crearon los documentos de prueba
        
        self.state = 'basic_test'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Set de Pruebas procesado'),
                'message': _('Se han creado los documentos requeridos para el Set de Pruebas.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_view_cafs(self):
        """Abre la vista de CAFs filtrada por la compañía actual"""
        self.ensure_one()
        return {
            'name': _('CAFs'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cl.dte.caf',
            'view_mode': 'tree,form',
            'domain': [('company_id', '=', self.company_id.id)],
            'context': {'default_company_id': self.company_id.id},
        }
    
    def action_view_test_documents(self):
        """Abre la vista de documentos de prueba"""
        self.ensure_one()
        return {
            'name': _('Documentos de Prueba'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.test_invoice_ids.ids)],
            'context': {'default_l10n_cl_certification_id': self.id},
        }
