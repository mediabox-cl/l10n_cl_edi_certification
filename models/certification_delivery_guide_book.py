# -*- coding: utf-8 -*-
"""
Modelo principal para el Libro de Guías de Despacho de Certificación SII
Combina todas las funcionalidades especializadas mediante herencia múltiple
"""
from odoo import models

class CertificationDeliveryGuideBook(models.Model):
    _name = 'l10n_cl_edi.certification.delivery_guide_book'
    _inherit = [
        'l10n_cl_edi.certification.delivery_guide_book.base',
        'l10n_cl_edi.certification.delivery_guide_book.actions', 
        'l10n_cl_edi.certification.delivery_guide_book.xml_builder',
        'l10n_cl_edi.certification.delivery_guide_book.processor'
    ]
    _description = 'Libro de Guías de Despacho - Certificación SII'
    
    # No necesita campos adicionales, todo viene de los mixins