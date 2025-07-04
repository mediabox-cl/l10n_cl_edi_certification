# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    l10n_cl_edi_certification_id = fields.Many2one('l10n_cl_edi.certification.process', 
                                               string='Proceso Certificación SII',
                                               help='Proceso de certificación al que pertenece este documento')
    
    # === CAMPOS ESPECÍFICOS DE EXPORTACIÓN ===
    # Campos adicionales no cubiertos por l10n_cl_edi_exports
    
    # Forma de pago exportación (Tag 14 DTE)
    l10n_cl_export_payment_terms = fields.Selection([
        ('ANTICIPO', 'Anticipo'),
        ('ACRED', 'Carta de Crédito'),
        ('COBRANZA', 'Cobranza'),
        ('CONTADO', 'Contado'),
        ('OTROS', 'Otros')
    ], string='Forma de Pago Exportación', help='Forma de pago específica para documentos de exportación')
    
    # Referencias documentales (GlosaRefOtra)
    l10n_cl_export_reference_text = fields.Text(string='Referencia Documental Exportación',
                                                help='Referencias como MIC, DUS, AWB, RESOLUCION SNA, etc.')
    
    # Tipo de bulto específico (TipoBulto)
    l10n_cl_export_package_type = fields.Char(string='Tipo de Bulto Exportación',
                                              help='Tipo específico de bulto según tabla SII')
    
    # Costos de transporte (MntFlete, MntSeguro)
    l10n_cl_export_freight_amount = fields.Monetary(string='Monto Flete',
                                                    help='Monto del flete en moneda de la factura',
                                                    currency_field='currency_id')
    l10n_cl_export_insurance_amount = fields.Monetary(string='Monto Seguro',
                                                      help='Monto del seguro en moneda de la factura',
                                                      currency_field='currency_id')
    
    # Comisiones extranjero (como recargo global)
    l10n_cl_export_foreign_commission_percent = fields.Float(string='% Comisiones Extranjero',
                                                             help='Porcentaje de comisiones por agentes en el extranjero',
                                                             digits=(5, 2))

    def _l10n_cl_create_dte_envelope(self, receiver_rut='60803000-K'):
        """
        Override para procesos de certificación DTE.
        """
        # Para documentos de certificación, usar flujo normal
        # El RUT genérico 55555555-5 se maneja directamente en el template XML
        dte_signed, file_name = super()._l10n_cl_create_dte_envelope(receiver_rut)
        
        # Log para certificación
        if hasattr(self, 'l10n_cl_edi_certification_id') or self._context.get('l10n_cl_edi_certification'):
            _logger.info("✓ DTE generado para certificación - XML procesado")
            
        return dte_signed, file_name
    
    def _check_l10n_latam_documents(self):
        """Override para saltar validación de documentos extranjeros en certificación"""
        # Saltar validación cuando hay contexto de bypass o es documento de certificación
        if (self.env.context.get('l10n_cl_edi_certification_bypass') or 
            any(move.l10n_cl_edi_certification_id for move in self)):
            return
            
        # Llamar validación normal para documentos no relacionados con certificación
        super()._check_l10n_latam_documents()