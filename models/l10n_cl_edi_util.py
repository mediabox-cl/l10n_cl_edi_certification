# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class L10nClEdiUtilMixin(models.AbstractModel):
    _inherit = 'l10n_cl.edi.util'

    def _send_xml_to_sii(self, mode, company_website, params, digital_signature, post='/cgi_dte/UPL/DTEUpload'):
        """
        Override para interceptar y loggear respuestas del SII en formato raw.
        """
        _logger.info("=== INTERCEPTANDO ENVÍO AL SII ===")
        _logger.info(f"Mode: {mode}")
        _logger.info(f"Company website: {company_website}")
        _logger.info(f"Post endpoint: {post}")
        
        # Llamar al método original
        response = super()._send_xml_to_sii(mode, company_website, params, digital_signature, post)
        
        # Loggear la respuesta raw
        if response:
            _logger.info("=== RESPUESTA RAW DEL SII ===")
            _logger.info(f"Tipo de respuesta: {type(response)}")
            _logger.info(f"Longitud de respuesta: {len(response) if response else 'None'}")
            
            # Convertir a string si es bytes
            if isinstance(response, bytes):
                try:
                    response_str = response.decode('utf-8')
                    _logger.info("Respuesta decodificada como UTF-8:")
                    _logger.info(response_str)
                except UnicodeDecodeError:
                    try:
                        response_str = response.decode('iso-8859-1')
                        _logger.info("Respuesta decodificada como ISO-8859-1:")
                        _logger.info(response_str)
                    except UnicodeDecodeError:
                        _logger.info("No se pudo decodificar la respuesta. Contenido raw:")
                        _logger.info(repr(response))
            else:
                _logger.info("Respuesta como string:")
                _logger.info(str(response))
            
            _logger.info("=== FIN RESPUESTA RAW ===")
        else:
            _logger.info("=== RESPUESTA VACÍA O NONE ===")
        
        return response

    def _send_xml_to_sii_rest(self, mode, company_vat, file_name, xml_message, digital_signature):
        """
        Override para interceptar respuestas REST del SII.
        """
        _logger.info("=== INTERCEPTANDO ENVÍO REST AL SII ===")
        _logger.info(f"Mode: {mode}")
        _logger.info(f"Company VAT: {company_vat}")
        _logger.info(f"File name: {file_name}")
        
        # Llamar al método original
        response = super()._send_xml_to_sii_rest(mode, company_vat, file_name, xml_message, digital_signature)
        
        # Loggear la respuesta
        if response:
            _logger.info("=== RESPUESTA REST DEL SII ===")
            _logger.info(f"Tipo de respuesta: {type(response)}")
            _logger.info(f"Contenido: {response}")
            _logger.info("=== FIN RESPUESTA REST ===")
        else:
            _logger.info("=== RESPUESTA REST VACÍA O NONE ===")
        
        return response 