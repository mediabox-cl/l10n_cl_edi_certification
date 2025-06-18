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
        
        # Determinar si es partner de empresa
        is_company_partner = self._is_company_partner()
        giro_limit = 80 if is_company_partner else 40
        partner_type = "empresa" if is_company_partner else "partner"
        
        # Validar razón social (100 chars)
        if self.name and len(self.name) > 100:
            self.name = self.name[:97] + '...'
            warnings.append('Razón social truncada a 100 caracteres')
        
        # Validar giro (80 chars empresa / 40 chars partner)
        if self.l10n_cl_activity_description and len(self.l10n_cl_activity_description) > giro_limit:
            self.l10n_cl_activity_description = self.l10n_cl_activity_description[:giro_limit-3] + '...'
            warnings.append(f'Giro de {partner_type} truncado a {giro_limit} caracteres')
        
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
        
        Límites aplicados según especificación SII (FORMATOS_DTE.md):
        - name (razón social): 100 caracteres
        - l10n_cl_activity_description (giro): 
          * 80 caracteres para empresas (GiroEmisor) - Línea 58 especificación
          * 40 caracteres para partners/receptores (GiroRecep) - Línea 61 especificación  
        - street (dirección): 60 caracteres
        """
        # Determinar si este partner es de una empresa
        is_company_partner = self._is_company_partner(vals)
        
        # Límites según esquema XSD del SII
        field_limits = {
            'name': 100,                                                # Razón social
            'l10n_cl_activity_description': 80 if is_company_partner else 40,  # Giro diferenciado
            'street': 60,                                               # Dirección
        }
        
        for field_name, max_length in field_limits.items():
            if field_name in vals and vals[field_name]:
                field_value = vals[field_name]
                if len(field_value) > max_length:
                    original_length = len(field_value)
                    # Truncar dejando espacio para "..."
                    vals[field_name] = field_value[:max_length-3] + '...'
                    partner_type = "empresa" if is_company_partner else "partner"
                    _logger.info(
                        f"✂️  Campo {field_name} truncado para {partner_type}: {original_length} → {max_length} caracteres"
                    )
        
        return vals
    
    def _is_company_partner(self, vals=None):
        """
        Determina si este partner pertenece a una empresa (res.company).
        
        Los partners de empresa son aquellos que están vinculados como partner_id
        de algún registro res.company, por lo que requieren límites diferentes
        según especificación SII (80 chars vs 40 chars para giro).
        
        Args:
            vals (dict): Valores que se están escribiendo/creando (opcional)
            
        Returns:
            bool: True si es partner de empresa, False si es partner normal
        """
        # Para nuevos registros, verificar si se está creando como empresa
        if vals and vals.get('is_company', False):
            return True
            
        # Para registros existentes, verificar si ya es partner de alguna empresa
        if self.id:
            company_count = self.env['res.company'].search_count([
                ('partner_id', '=', self.id)
            ])
            return company_count > 0
            
        # Para registros nuevos sin flag is_company, asumir partner normal
        return False

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