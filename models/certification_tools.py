from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CertificationTools(models.Model):
    _name = 'l10n_cl.certification.tools'
    _description = 'Herramientas de Certificación SII'

    name = fields.Char(string='Nombre', default='Herramientas de Certificación')

    def prepare_database_for_certification(self):
        """Prepara la base de datos para el proceso de certificación SII"""
        self.ensure_one()
        
        # Crear o actualizar tipo de documento SET
        doc_type_set = self._create_document_type_set()
        
        # Mostrar mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Base de datos preparada para certificación'),
                'message': _('Se ha creado/actualizado el tipo de documento SET para referencias.'),
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