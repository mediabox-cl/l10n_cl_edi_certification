# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    # Campo para identificar partners usados exclusivamente para certificación SII
    l10n_cl_edi_certification_partner = fields.Boolean(
        string='Partner de Certificación SII',
        default=False,
        help='Indica si este partner es usado exclusivamente para el proceso de certificación SII'
    )
    
    # Campo para trackear a qué caso fue asignado este partner
    l10n_cl_edi_assigned_case_number = fields.Char(
        string='Caso Asignado',
        help='Número de caso DTE al que fue asignado este partner de certificación'
    )

    @api.model
    def create(self, vals):
        """Override create con validación preventiva de longitudes."""
        vals = self._validate_field_lengths(vals)
        return super().create(vals)

    def write(self, vals):
        """Override write con validación preventiva de longitudes."""
        vals = self._validate_field_lengths(vals)
        return super().write(vals)

    @api.onchange('name', 'l10n_cl_activity_description', 'street')
    def _onchange_validate_lengths(self):
        """Validación en tiempo real de longitudes de campos."""
        warnings = []
        
        # Validar razón social (100 chars)
        if self.name and len(self.name) > 100:
            self.name = self.name[:97] + '...'
            warnings.append('Razón social truncada a 100 caracteres')
        
        # Validar giro (40 chars)
        if self.l10n_cl_activity_description and len(self.l10n_cl_activity_description) > 40:
            self.l10n_cl_activity_description = self.l10n_cl_activity_description[:37] + '...'
            warnings.append('Giro truncado a 40 caracteres')
        
        # Validar dirección (60 chars)
        if self.street and len(self.street) > 60:
            self.street = self.street[:57] + '...'
            warnings.append('Dirección truncada a 60 caracteres')
        
        # Mostrar warning si hubo truncados
        if warnings:
            return {
                'warning': {
                    'title': 'Campos Truncados',
                    'message': 'Los siguientes campos fueron truncados para cumplir límites SII:\n• ' + '\n• '.join(warnings)
                }
            }

    def _validate_field_lengths(self, vals):
        """
        Valida y trunca campos que excedan los límites del esquema XSD del SII.
        
        Límites aplicados:
        - name (razón social): 100 caracteres
        - l10n_cl_activity_description (giro): 40 caracteres  
        - street (dirección): 60 caracteres
        """
        # Límites según esquema XSD del SII
        field_limits = {
            'name': 100,                           # Razón social
            'l10n_cl_activity_description': 40,    # Giro/actividad
            'street': 60,                          # Dirección
        }
        
        for field_name, max_length in field_limits.items():
            if field_name in vals and vals[field_name]:
                field_value = vals[field_name]
                if len(field_value) > max_length:
                    original_length = len(field_value)
                    # Truncar dejando espacio para "..."
                    vals[field_name] = field_value[:max_length-3] + '...'
                    _logger.info(
                        f"✂️  Campo {field_name} truncado: {original_length} → {max_length} caracteres"
                    )
        
        return vals

    def _get_giro_for_certification_case(self, case_number=None):
        """
        Retorna el giro apropiado según el caso de certificación.
        
        Para casos específicos como corrección de giro, retorna un giro alternativo.
        """
        # Caso especial: 4267228-5 (CORRIGE GIRO DEL RECEPTOR)
        if case_number == '4267228-5':
            return 'Servicios de Consultoría Empresarial'  # Giro corregido (37 chars)
        
        # Giro normal
        return self.l10n_cl_activity_description or 'Servicios Empresariales'  # Fallback (22 chars) 