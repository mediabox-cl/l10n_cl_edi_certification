# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl_edi.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece este documento')