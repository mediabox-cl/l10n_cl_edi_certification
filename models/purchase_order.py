# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl_edi.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece esta orden de compra')