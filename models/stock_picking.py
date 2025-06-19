# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    l10n_cl_edi_certification_id = fields.Many2one(
        'l10n_cl_edi.certification.process', 
        string='Proceso Certificación SII',
        help='Proceso de certificación al que pertenece esta guía de despacho'
    )
    
    # Campo para vincular con caso DTE específico
    l10n_cl_edi_certification_case_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte',
        string='Caso DTE Certificación',
        help='Caso DTE específico que genera esta guía de despacho'
    )

    def _prepare_dte_values(self):
        """
        Override para agregar referencias de certificación y corregir campos específicos.
        """
        values = super()._prepare_dte_values()
        
        # SIEMPRE agregar una referencia para evitar error SII
        if self.l10n_cl_edi_certification_case_id:
            # Agregar referencias de certificación
            cert_refs = self._get_certification_references()
            values['certification_references'] = cert_refs
            values['delivery_guide_reason'] = self.l10n_cl_delivery_guide_reason
            
            _logger.info("✓ Aplicando configuración específica de certificación para guía")
            _logger.info(f"  - Referencias SET: {len(cert_refs)}")
            _logger.info(f"  - Detalle referencias: {cert_refs}")
            _logger.info(f"  - Motivo traslado: {self.l10n_cl_delivery_guide_reason}")
        else:
            # Forzar una referencia básica si no hay certificación
            values['certification_references'] = [{
                'sequence': 1,
                'document_type': 'SET',
                'folio': 'CERT-001',
                'date': fields.Date.today().strftime('%Y-%m-%d'),
                'reason': 'Documento de Certificación',
            }]
            _logger.info("⚠️ Guía sin certificación - aplicando referencia por defecto")
        
        return values
    
    def _get_certification_references(self):
        """
        Genera referencias SET para certificación SII.
        """
        if not self.l10n_cl_edi_certification_case_id:
            return []
        
        case = self.l10n_cl_edi_certification_case_id
        
        # El folio debe ser el caso completo (formato: 4244621-1)
        # NO extraer solo el número SET, usar el caso específico completo
        folio_ref = case.case_number_raw
        
        references = [{
            'sequence': 1,
            'document_type': 'SET',
            'folio': folio_ref,
            'date': fields.Date.today().strftime('%Y-%m-%d'),  # Usar fecha actual para certificación
            'reason': f'CASO {case.case_number_raw}',
        }]
        
        _logger.info(f"Generando referencia SET: {references[0]}")
        return references
    
    
    def _l10n_cl_create_dte_envelope(self, receiver_rut='60803000-K'):
        """
        Override para procesos de certificación DTE.
        Mantiene el XML original sin modificaciones de encoding para guías de despacho.
        """
        # Llamar al método original
        dte_signed, file_name = super()._l10n_cl_create_dte_envelope(receiver_rut)
        
        # Log para certificación
        if self.l10n_cl_edi_certification_id or self._context.get('l10n_cl_edi_certification'):
            _logger.info("✓ Guía de Despacho DTE generada para certificación - XML original mantenido")
            
        return dte_signed, file_name
