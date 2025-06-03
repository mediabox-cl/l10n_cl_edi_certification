# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CertificationResetWizard(models.TransientModel):
    _name = 'l10n_cl_edi.certification.reset.wizard'
    _description = 'Wizard para Reset de Casos DTE'

    case_id = fields.Many2one('l10n_cl_edi.certification.case.dte', string='Caso DTE', required=True)
    invoice_id = fields.Many2one('account.move', string='Factura Vinculada')
    invoice_name = fields.Char(string='Nombre Factura', readonly=True)
    invoice_state = fields.Char(string='Estado Factura', readonly=True)
    
    action = fields.Selection([
        ('unlink_only', 'Solo desvincular (mantener factura)'),
        ('delete_draft', 'Eliminar factura en borrador'),
    ], string='Acción', default='unlink_only', required=True)

    def action_confirm_reset(self):
        """Confirmar el reset del caso"""
        self.ensure_one()
        
        case = self.case_id
        invoice = self.invoice_id
        
        if self.action == 'delete_draft' and invoice and invoice.state == 'draft':
            # Eliminar la factura en borrador
            invoice_name = invoice.name
            invoice.unlink()
            case.generated_account_move_id = False
            case.generation_status = 'pending'
            _logger.info(f"Caso {case.id} reseteado. Factura {invoice_name} eliminada.")
        else:
            # Solo desvincular
            case.generated_account_move_id = False
            case.generation_status = 'pending'
            _logger.info(f"Caso {case.id} reseteado. Factura {invoice.name if invoice else 'N/A'} desvinculada.")
        
        return {'type': 'ir.actions.act_window_close'} 