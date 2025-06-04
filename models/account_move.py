# -*- coding: utf-8 -*-
from odoo import models, fields, api
import base64
import logging
import re

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl_edi.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece este documento')

    def _l10n_cl_create_dte_envelope(self, receiver_rut='60803000-K'):
        """
        Override para corregir problemas de encoding en XML DTE.
        Aplica correcciones selectivas: entidades HTML para productos, 
        normalización para campos específicos.
        """
        # Llamar al método original
        dte_signed, file_name = super()._l10n_cl_create_dte_envelope(receiver_rut)
        
        # Aplicar corrección de encoding si estamos en proceso de certificación
        if hasattr(self, 'l10n_cl_edi_certification_id') or self._context.get('l10n_cl_edi_certification'):
            _logger.info("Aplicando correcciones para certificación DTE")
            
            # Corregir caracteres especiales EN LÍNEAS DE PRODUCTOS (mantener entidades HTML)
            dte_signed = self._fix_encoding_issues_for_dte(dte_signed)
            
            # Corregir longitudes de campos
            dte_signed = self._fix_field_lengths_for_dte(dte_signed)
            
        return dte_signed, file_name

    def _fix_encoding_issues_for_dte(self, xml_content):
        """
        NORMALIZACIÓN DESHABILITADA - Solo mantiene el XML original.
        
        Anteriormente aplicaba normalización de caracteres especiales,
        pero se deshabilitó para probar si el SII acepta caracteres originales.
        """
        if not xml_content:
            return xml_content
        
        # NORMALIZACIÓN DESHABILITADA
        # No aplicar reemplazos de caracteres especiales
        _logger.info("⚠️  Normalización de caracteres DESHABILITADA - manteniendo caracteres originales")
        
        return xml_content

    def _fix_field_lengths_for_dte(self, xml_content):
        """
        Trunca automáticamente campos que excedan los límites del esquema XSD del SII.
        """
        if not xml_content:
            return xml_content
        
        # Límites según esquema XSD del SII
        field_limits = {
            'GiroEmis': 40,    # Giro del emisor
            'GiroRecep': 40,   # Giro del receptor  
            'DirOrigen': 60,   # Dirección origen
            'DirRecep': 70,    # Dirección receptor
            'NmbItem': 80,     # Nombre del item
            'DscItem': 1000,   # Descripción del item
            'RznSoc': 100,     # Razón social emisor
            'RznSocRecep': 100, # Razón social receptor
        }
        
        for field, max_length in field_limits.items():
            xml_content = self._truncate_xml_field(xml_content, field, max_length)
        
        return xml_content

    def _truncate_xml_field(self, xml_content, field_name, max_length):
        """
        Trunca un campo específico del XML si excede la longitud máxima.
        """
        pattern = f'<{field_name}>(.*?)</{field_name}>'
        matches = re.findall(pattern, xml_content, re.DOTALL)
        
        for match in matches:
            # Calcular longitud real (decodificando entidades HTML)
            real_length = self._calculate_real_length(match)
            
            if real_length > max_length:
                # Truncar inteligentemente
                truncated = self._smart_truncate(match, max_length)
                xml_content = xml_content.replace(
                    f'<{field_name}>{match}</{field_name}>', 
                    f'<{field_name}>{truncated}</{field_name}>'
                )
                _logger.warning(f"Campo {field_name} truncado: {real_length} → {max_length} caracteres")
        
        return xml_content

    def _calculate_real_length(self, text):
        """
        Calcula la longitud real del texto decodificando entidades HTML.
        """
        # Decodificar entidades HTML comunes
        decoded = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
        # Reemplazar otras entidades con un caracter para contar
        decoded = re.sub(r'&[a-zA-Z]+;', 'X', decoded)
        return len(decoded)

    def _smart_truncate(self, text, max_length):
        """
        Trunca texto de forma inteligente, respetando entidades HTML.
        """
        if self._calculate_real_length(text) <= max_length:
            return text
        
        # Estrategia: truncar palabra por palabra hasta que quepa
        words = text.split()
        truncated_words = []
        
        for word in words:
            test_text = ' '.join(truncated_words + [word])
            if self._calculate_real_length(test_text) <= max_length - 3:  # -3 para "..."
                truncated_words.append(word)
            else:
                break
        
        result = ' '.join(truncated_words)
        if self._calculate_real_length(result) < self._calculate_real_length(text):
            result += '...'
        
        return result

    @api.model
    def normalize_giro_for_sii(self, giro_text):
        """
        Normaliza un giro para cumplir con los estándares del SII:
        - MANTIENE mayúsculas y minúsculas originales
        - Elimina tildes y caracteres especiales
        - Cambia Ñ por N
        - Limita a 40 caracteres máximo
        - Trunca inteligentemente por palabras
        """
        if not giro_text:
            return giro_text
        
        # Mapeo de caracteres especiales a caracteres básicos (MANTENIENDO CASO)
        char_map = {
            'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a',
            'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e',
            'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i',
            'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o',
            'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u',
            'ñ': 'n',
            'ç': 'c',
            'Á': 'A', 'À': 'A', 'Ä': 'A', 'Â': 'A',
            'É': 'E', 'È': 'E', 'Ë': 'E', 'Ê': 'E',
            'Í': 'I', 'Ì': 'I', 'Ï': 'I', 'Î': 'I',
            'Ó': 'O', 'Ò': 'O', 'Ö': 'O', 'Ô': 'O',
            'Ú': 'U', 'Ù': 'U', 'Ü': 'U', 'Û': 'U',
            'Ñ': 'N',
            'Ç': 'C',
        }
        
        # Aplicar normalizaciones
        normalized = giro_text
        
        # 1. Reemplazar caracteres especiales (MANTENIENDO MAYÚSCULAS/MINÚSCULAS)
        for special_char, basic_char in char_map.items():
            normalized = normalized.replace(special_char, basic_char)
        
        # 2. NO convertir a mayúsculas - mantener formato original
        
        # 3. Limpiar caracteres no alfanuméricos (excepto espacios y puntos)
        # Permitir mayúsculas, minúsculas, números, espacios y puntos
        normalized = re.sub(r'[^A-Za-z0-9\s\.]', '', normalized)
        
        # 4. Limpiar espacios múltiples
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 5. Truncar a 40 caracteres máximo (por palabras)
        if len(normalized) > 40:
            words = normalized.split()
            truncated_words = []
            
            for word in words:
                test_text = ' '.join(truncated_words + [word])
                if len(test_text) <= 37:  # 37 + 3 ("...") = 40
                    truncated_words.append(word)
                else:
                    break
            
            normalized = ' '.join(truncated_words)
            if len(normalized) < len(giro_text):
                normalized += '...'
        
        return normalized