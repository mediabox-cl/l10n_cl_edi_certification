from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    l10n_cl_edi_certification_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación SII',
        readonly=True,
        help='Proceso de certificación SII al que pertenece este pedido de venta'
    ) 