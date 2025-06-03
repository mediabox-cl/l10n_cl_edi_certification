# -*- coding: utf-8 -*-
from odoo import models, fields, api
import base64
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl_edi.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece este documento')

    def _l10n_cl_create_dte_envelope(self, receiver_rut='60803000-K'):
        """
        Override para corregir problemas de encoding en XML DTE.
        """
        # Llamar al método original
        dte_signed, file_name = super()._l10n_cl_create_dte_envelope(receiver_rut)
        
        # Aplicar corrección de encoding si estamos en proceso de certificación
        if hasattr(self, 'l10n_cl_edi_certification_id') or self._context.get('l10n_cl_edi_certification'):
            _logger.info("Aplicando corrección de encoding para certificación DTE")
            
            # Corregir caracteres especiales
            dte_signed = self._fix_encoding_issues_for_dte(dte_signed)
            
        return dte_signed, file_name

    def _fix_encoding_issues_for_dte(self, xml_content):
        """
        Corrige problemas de encoding en el XML DTE.
        Convierte caracteres especiales problemáticos para ISO-8859-1.
        """
        if not xml_content:
            return xml_content
        
        # Mapeo de caracteres problemáticos comunes en Chile
        char_replacements = {
            'ñ': '&ntilde;',
            'Ñ': '&Ntilde;',
            'á': '&aacute;',
            'é': '&eacute;',
            'í': '&iacute;',
            'ó': '&oacute;',
            'ú': '&uacute;',
            'Á': '&Aacute;',
            'É': '&Eacute;',
            'Í': '&Iacute;',
            'Ó': '&Oacute;',
            'Ú': '&Uacute;',
            'ü': '&uuml;',
            'Ü': '&Uuml;',
            '°': '&deg;',
        }
        
        # Aplicar reemplazos
        original_content = xml_content
        for char, replacement in char_replacements.items():
            xml_content = xml_content.replace(char, replacement)
        
        # Log solo si hubo cambios
        if xml_content != original_content:
            _logger.info("✓ Caracteres especiales corregidos en XML DTE")
            
        return xml_content