# Añadir en models/account_move.py
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece este documento')