# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def create(self, vals):
        """Override create - NORMALIZACIÓN DE GIRO DESHABILITADA."""
        # NORMALIZACIÓN DESHABILITADA
        # Mantener giro original sin modificaciones
        if 'l10n_cl_activity_description' in vals and vals['l10n_cl_activity_description']:
            _logger.info("⚠️  Normalización de giro DESHABILITADA en create - manteniendo giro original")
        
        return super().create(vals)

    def write(self, vals):
        """Override write - NORMALIZACIÓN DE GIRO DESHABILITADA."""
        # NORMALIZACIÓN DESHABILITADA
        # Mantener giro original sin modificaciones
        if 'l10n_cl_activity_description' in vals and vals['l10n_cl_activity_description']:
            _logger.info("⚠️  Normalización de giro DESHABILITADA en write - manteniendo giro original")
        
        return super().write(vals)

    @api.onchange('l10n_cl_activity_description')
    def _onchange_giro_normalize(self):
        """NORMALIZACIÓN DE GIRO DESHABILITADA - No se aplican cambios automáticos."""
        # NORMALIZACIÓN DESHABILITADA
        # No normalizar giro automáticamente
        if self.l10n_cl_activity_description:
            _logger.info("⚠️  Normalización de giro DESHABILITADA en onchange - manteniendo giro original")
        
        # No retornar warning ni modificar el campo
        return 