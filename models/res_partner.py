# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def create(self, vals):
        """Override create para normalizar giro automáticamente."""
        if 'l10n_cl_activity_description' in vals and vals['l10n_cl_activity_description']:
            original_giro = vals['l10n_cl_activity_description']
            normalized_giro = self.env['account.move'].normalize_giro_for_sii(original_giro)
            
            if original_giro != normalized_giro:
                vals['l10n_cl_activity_description'] = normalized_giro
                _logger.info(f"Giro normalizado automáticamente: '{original_giro}' → '{normalized_giro}'")
        
        return super().create(vals)

    def write(self, vals):
        """Override write para normalizar giro automáticamente."""
        if 'l10n_cl_activity_description' in vals and vals['l10n_cl_activity_description']:
            original_giro = vals['l10n_cl_activity_description']
            normalized_giro = self.env['account.move'].normalize_giro_for_sii(original_giro)
            
            if original_giro != normalized_giro:
                vals['l10n_cl_activity_description'] = normalized_giro
                _logger.info(f"Giro normalizado automáticamente: '{original_giro}' → '{normalized_giro}'")
        
        return super().write(vals)

    @api.onchange('l10n_cl_activity_description')
    def _onchange_giro_normalize(self):
        """Normaliza el giro en tiempo real mientras el usuario escribe."""
        if self.l10n_cl_activity_description:
            original_giro = self.l10n_cl_activity_description
            normalized_giro = self.env['account.move'].normalize_giro_for_sii(original_giro)
            
            if original_giro != normalized_giro:
                self.l10n_cl_activity_description = normalized_giro
                
                # Mostrar mensaje informativo al usuario
                return {
                    'warning': {
                        'title': 'Giro Normalizado',
                        'message': f'El giro ha sido normalizado automáticamente para cumplir con los estándares del SII:\n\n'
                                 f'Original: {original_giro}\n'
                                 f'Normalizado: {normalized_giro}\n\n'
                                 f'Cambios aplicados:\n'
                                 f'• Convertido a mayúsculas\n'
                                 f'• Eliminadas tildes y caracteres especiales\n'
                                 f'• Ñ cambiada por N\n'
                                 f'• Limitado a 40 caracteres máximo'
                    }
                } 