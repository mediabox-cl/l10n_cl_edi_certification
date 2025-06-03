# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CertificationCaseDte(models.Model):
    _name = 'l10n_cl_edi.certification.case.dte'
    _description = 'Caso DTE de Certificación'
    _rec_name = 'case_number_display'

    # Campos básicos
    case_number_raw = fields.Char(string='Número de Caso (Raw)', required=True)
    case_number_display = fields.Char(string='Número de Caso', compute='_compute_case_number_display', store=True)
    document_type_code = fields.Char(string='Código Tipo Documento', required=True)
    document_type_name = fields.Char(string='Nombre Tipo Documento', compute='_compute_document_type_name', store=True)
    
    # Relaciones
    parsed_set_id = fields.Many2one(
        'l10n_cl_edi.certification.parsed_set',
        string='Set de Pruebas',
        required=True,
        ondelete='cascade'
    )
    partner_id = fields.Many2one(
        'res.partner', 
        string='Cliente',
        compute='_compute_partner_id',
        store=True,
        help='Partner asociado al proceso de certificación'
    )
    
    # Estado de generación
    generation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('generated', 'Generado'),
        ('error', 'Error')
    ], string='Estado Generación', default='pending', tracking=True)
    
    # Factura generada
    generated_account_move_id = fields.Many2one(
        'account.move',
        string='Factura Generada',
        readonly=True,
        help='Factura generada desde este caso DTE'
    )
    
    # Campos adicionales
    error_message = fields.Text(string='Mensaje de Error')
    notes = fields.Text(string='Notas')
    
    # Campos computados
    invoice_state = fields.Selection(
        related='generated_account_move_id.state',
        string='Estado Factura',
        readonly=True
    )
    
    @api.depends('case_number_raw')
    def _compute_case_number_display(self):
        for record in self:
            if record.case_number_raw:
                record.case_number_display = f"Caso {record.case_number_raw}"
            else:
                record.case_number_display = "Sin número"

    @api.depends('document_type_code')
    def _compute_document_type_name(self):
        for record in self:
            if record.document_type_code:
                # Buscar el tipo de documento en Odoo
                doc_type = self.env['l10n_latam.document.type'].search([
                    ('code', '=', record.document_type_code),
                    ('country_id.code', '=', 'CL')
                ], limit=1)
                
                if doc_type:
                    record.document_type_name = doc_type.name
                else:
                    record.document_type_name = f"Tipo {record.document_type_code}"
            else:
                record.document_type_name = "Sin tipo"

    @api.depends('parsed_set_id')
    def _compute_partner_id(self):
        for record in self:
            if record.parsed_set_id:
                record.partner_id = record.parsed_set_id.partner_id
            else:
                record.partner_id = False

    def action_reset_case(self):
        """
        Resetea el caso DTE para permitir regeneración.
        Maneja la desvinculación de facturas existentes.
        """
        self.ensure_one()
        
        if self.generated_account_move_id:
            invoice = self.generated_account_move_id
            
            if invoice.state == 'draft':
                # Si la factura está en borrador, preguntar qué hacer
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Confirmar Reset',
                    'res_model': 'l10n_cl_edi.certification.reset.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_case_id': self.id,
                        'default_invoice_id': invoice.id,
                        'default_invoice_name': invoice.name,
                        'default_invoice_state': invoice.state,
                    }
                }
            elif invoice.state in ['posted', 'cancel']:
                # Si la factura está validada o cancelada, solo desvincular
                self.generated_account_move_id = False
                self.generation_status = 'pending'
                self.message_post(
                    body=f"Caso reseteado. Factura {invoice.name} desvinculada (estado: {invoice.state})",
                    subject="Caso Reseteado"
                )
            else:
                raise UserError(f"No se puede resetear: la factura {invoice.name} está en estado {invoice.state}")
        else:
            # Si no hay factura vinculada, simplemente resetear estado
            self.generation_status = 'pending'
            self.message_post(
                body="Caso reseteado a estado 'pending'",
                subject="Caso Reseteado"
            )
        
        return True

    def action_view_invoice(self):
        """Abrir la factura vinculada si existe"""
        self.ensure_one()
        
        if not self.generated_account_move_id:
            raise UserError("Este caso DTE no tiene una factura vinculada")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factura Vinculada',
            'res_model': 'account.move',
            'res_id': self.generated_account_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_generate_document(self):
        """Generar documento desde el caso DTE"""
        self.ensure_one()
        
        # Crear el generador y ejecutar
        generator = self.env['l10n_cl_edi.certification.document.generator'].create({
            'dte_case_id': self.id,
        })
        
        return generator.generate_document() 