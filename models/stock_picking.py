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
        
        # Si es una guía de certificación, agregar referencias SET y corregir campos
        if self.l10n_cl_edi_certification_case_id:
            # Agregar referencias de certificación
            values['certification_references'] = self._get_certification_references()
            
            # Corregir motivo de traslado según tipo de movimiento
            values['delivery_guide_reason'] = self._get_certification_delivery_reason()
            
            _logger.info("✓ Aplicando configuración específica de certificación para guía")
            _logger.info(f"  - Referencias SET: {len(values.get('certification_references', []))}")
            _logger.info(f"  - Motivo traslado: {values.get('delivery_guide_reason')}")
        
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
            'date': case.date_case.strftime('%Y-%m-%d') if case.date_case else fields.Date.today().strftime('%Y-%m-%d'),
            'reason': f'CASO {case.case_number_raw}',
        }]
        
        _logger.info(f"Generando referencia SET: {references[0]}")
        return references
    
    def _get_certification_delivery_reason(self):
        """
        Determina el motivo de traslado correcto según el tipo de movimiento.
        """
        if not self.l10n_cl_edi_certification_case_id:
            return '1'  # Venta por defecto
        
        # Determinar según tipo de picking y configuración
        if self.picking_type_id.code == 'internal':
            # Traslado interno entre bodegas
            return '8'  # Traslado entre bodegas
        elif self.picking_type_id.code == 'outgoing':
            # Entrega a cliente
            return '1'  # Operación constituye venta
        else:
            # Fallback a venta
            return '1'
    
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
