# -*- coding: utf-8 -*-
"""
Modelo principal que combina todas las funcionalidades del libro IECV
Hereda de todos los mixins especializados
"""
from odoo import models

class CertificationIECVBook(models.Model):
    _name = 'l10n_cl_edi.certification.iecv_book'
    _inherit = [
        'l10n_cl_edi.certification.iecv_book.base',
        'l10n_cl_edi.certification.iecv_book.actions', 
        'l10n_cl_edi.certification.iecv_book.xml_builder',
        'l10n_cl_edi.certification.iecv_book.sales_processor',
        'l10n_cl_edi.certification.iecv_book.purchase_processor'
    ]
    _description = 'Libro Electrónico de Compras y Ventas - Certificación SII'
