# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    l10n_cl_edi_certification_id = fields.Many2one(
        'l10n_cl_edi.certification.process', 
        string='Proceso Certificación SII',
        help='Proceso de certificación al que pertenece esta guía de despacho'
    )

    def _l10n_cl_create_dte_envelope(self, receiver_rut='60803000-K'):
        """
        Override para procesos de certificación DTE.
        Mantiene el XML original sin modificaciones de encoding para guías de despacho.
        """
        # Llamar al método original
        dte_signed, file_name = super()._l10n_cl_create_dte_envelope(receiver_rut)
        
        # Log para certificación
        if hasattr(self, 'l10n_cl_edi_certification_id') or self._context.get('l10n_cl_edi_certification'):
            _logger.info("✓ Guía de Despacho DTE generada para certificación - XML original mantenido")
            
        return dte_signed, file_name
