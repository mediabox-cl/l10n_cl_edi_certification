# -*- coding: utf-8 -*-
"""
Constantes para el proceso de certificación IECV SII Chile
"""

# Constantes para proceso de certificación SII
SII_RUT = "60803000-K"  # RUT del SII para certificación
DEFAULT_PROPORTIONALITY_FACTOR = 0.60  # Factor de proporcionalidad IVA uso común

# Valores de resolución SII para certificación IECV
SII_RESOLUTION_DATE = "2006-01-20"
SII_RESOLUTION_NUMBER = "102006"

# Configuración de libros para certificación
BOOK_TYPE_SPECIAL = "ESPECIAL"
SEND_TYPE_TOTAL = "TOTAL"

# Folios de notificación específicos para certificación
FOLIO_NOTIFICATION_IEV = "1"  # Libro de ventas
FOLIO_NOTIFICATION_IEC = "2"  # Libro de compras

# Namespaces XML para libros IECV
XML_NAMESPACES = {
    None: 'http://www.sii.cl/SiiDte',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

XML_SCHEMA_LOCATION = "http://www.sii.cl/SiiDte LibroCV_v10.xsd"
