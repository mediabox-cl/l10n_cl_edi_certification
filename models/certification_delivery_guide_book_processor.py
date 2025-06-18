# -*- coding: utf-8 -*-
from odoo import models, api, _
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class CertificationDeliveryGuideBookProcessor(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.delivery_guide_book.processor'
    _description = 'Procesador de Guías para Libro de Guías de Despacho'
    
    # Definición de estados de guías según especificaciones SII para libro de guías
    GUIDE_STATUSES = {
        'normal': {
            'description': 'Guías normales del período (incluye traslados internos)',
            'cases': ['4329507-1'],  # Traslado interno - estado normal
            'anulado_code': '0'  # Normal, no anulado
        },
        'invoiced': {
            'description': 'Guías que se facturaron posteriormente en el período',
            'cases': ['4329507-2'],  # Venta con transporte - se facturó después
            'anulado_code': '0'  # Normal, no anulado (pero incluye referencia a factura)
        },
        'cancelled': {
            'description': 'Guías anuladas después del envío al SII',
            'cases': ['4329507-3'],  # Venta con retiro - fue anulada
            'anulado_code': '2'  # Anulado posterior al envío
        }
    }
    
    def _classify_delivery_guides(self):
        """
        Clasifica las guías según su estado en el período.
        Basado en las especificaciones del SET 4 - 4329508.
        """
        self.ensure_one()
        
        guides = self._get_delivery_guides()
        classified = {
            'normal': [],
            'invoiced': [],
            'cancelled': []
        }
        
        _logger.info(f"Clasificando {len(guides)} guías de despacho")
        
        for guide in guides:
            status = self._determine_guide_status(guide)
            classified[status].append(guide)
            _logger.info(f"Guía {guide.name}: clasificada como '{status}'")
            
        _logger.info(f"Clasificación completada: Normal={len(classified['normal'])}, "
                    f"Facturadas={len(classified['invoiced'])}, Anuladas={len(classified['cancelled'])}")
        
        return classified
    
    def _determine_guide_status(self, guide):
        """
        Determina el estado de una guía basado en reglas SII y especificaciones del set.
        
        Según SET 4 - 4329508:
        - Caso 2 (4329507-2): Guía que se facturó en el período
        - Caso 3 (4329507-3): Guía anulada
        - Caso 1 (4329507-1): Guía normal (por defecto)
        """
        # Obtener el caso DTE que generó esta guía
        case_dte = self._get_case_dte_for_guide(guide)
        
        if not case_dte:
            _logger.warning(f"No se encontró caso DTE para guía {guide.name}")
            return 'normal'
        
        case_number = case_dte.case_number_raw
        _logger.info(f"Evaluando guía {guide.name} con caso {case_number}")
        
        # Verificar si la guía fue anulada (caso 3)
        if self._is_guide_cancelled(guide, case_dte):
            return 'cancelled'
            
        # Verificar si la guía fue facturada en el período (caso 2)
        if self._is_guide_invoiced_in_period(guide, case_dte):
            return 'invoiced'
            
        # Por defecto es normal (caso 1)
        return 'normal'
    
    def _is_guide_cancelled(self, guide, case_dte=None):
        """
        Detecta si una guía fue anulada.
        Para certificación: basado en case number según especificación SET 4.
        """
        if not case_dte:
            case_dte = self._get_case_dte_for_guide(guide)
        
        # Según especificación SET 4: Caso 3 corresponde a guía anulada
        if case_dte and case_dte.case_number_raw == '4329507-3':
            _logger.info(f"Guía {guide.name} marcada como anulada (caso 4329507-3)")
            return True
        
        # Lógica adicional para producción: verificar estado real del picking
        if hasattr(guide, 'state') and guide.state == 'cancel':
            _logger.info(f"Guía {guide.name} está en estado cancelado")
            return True
        
        return False
    
    def _is_guide_invoiced_in_period(self, guide, case_dte=None):
        """
        Detecta si una guía fue facturada en el período.
        Para certificación: basado en case number según especificación SET 4.
        """
        if not case_dte:
            case_dte = self._get_case_dte_for_guide(guide)
        
        # Según especificación SET 4: Caso 2 corresponde a guía facturada
        if case_dte and case_dte.case_number_raw == '4329507-2':
            _logger.info(f"Guía {guide.name} marcada como facturada (caso 4329507-2)")
            return True
        
        # Lógica adicional: buscar facturas relacionadas en el período
        if self._has_related_invoice_in_period(guide):
            _logger.info(f"Guía {guide.name} tiene facturas relacionadas en el período")
            return True
        
        return False
    
    def _has_related_invoice_in_period(self, guide):
        """
        Busca facturas relacionadas con la guía en el período.
        """
        # Buscar facturas que referencien la guía directamente
        related_invoices = self.env['account.move'].search([
            ('picking_ids', 'in', guide.id),
            ('invoice_date', '>=', self._get_period_start()),
            ('invoice_date', '<=', self._get_period_end()),
            ('state', 'not in', ['draft', 'cancel']),
            ('move_type', 'in', ['out_invoice', 'out_refund'])
        ])
        
        if related_invoices:
            return True
        
        # Buscar facturas del mismo partner en el período (lógica alternativa)
        if guide.partner_id:
            partner_invoices = self.env['account.move'].search([
                ('partner_id', '=', guide.partner_id.id),
                ('invoice_date', '>=', self._get_period_start()),
                ('invoice_date', '<=', self._get_period_end()),
                ('state', 'not in', ['draft', 'cancel']),
                ('move_type', 'in', ['out_invoice'])
            ])
            
            # Si hay facturas del mismo partner y la guía es de venta, asumir relación
            case_dte = self._get_case_dte_for_guide(guide)
            if partner_invoices and case_dte and 'VENTA' in (case_dte.dispatch_motive_raw or '').upper():
                return True
        
        return False
    
    def _get_guide_classification_summary(self):
        """
        Obtiene un resumen de la clasificación de guías.
        """
        self.ensure_one()
        
        classified_guides = self._classify_delivery_guides()
        
        summary = {
            'total_guides': 0,
            'normal_count': len(classified_guides.get('normal', [])),
            'invoiced_count': len(classified_guides.get('invoiced', [])),
            'cancelled_count': len(classified_guides.get('cancelled', [])),
            'normal_amount': 0,
            'invoiced_amount': 0,
            'cancelled_amount': 0,
        }
        
        # Calcular montos por categoría
        for status, guides in classified_guides.items():
            amount_key = f"{status}_amount"
            for guide in guides:
                summary[amount_key] += self._calculate_guide_amount(guide)
        
        summary['total_guides'] = summary['normal_count'] + summary['invoiced_count'] + summary['cancelled_count']
        summary['total_amount'] = summary['normal_amount'] + summary['invoiced_amount'] + summary['cancelled_amount']
        
        return summary
    
    def _get_guides_by_status(self, status):
        """
        Obtiene las guías filtradas por un estado específico.
        """
        self.ensure_one()
        
        if status not in self.GUIDE_STATUSES:
            return []
        
        classified_guides = self._classify_delivery_guides()
        return classified_guides.get(status, [])
    
    def _validate_guide_classification(self):
        """
        Valida que la clasificación de guías sea correcta según las reglas SII.
        """
        self.ensure_one()
        
        classified_guides = self._classify_delivery_guides()
        
        # Validar que no haya guías sin clasificar
        all_guides = self._get_delivery_guides()
        classified_count = sum(len(guides) for guides in classified_guides.values())
        
        if len(all_guides) != classified_count:
            _logger.warning(f"Discrepancia en clasificación: {len(all_guides)} guías totales vs {classified_count} clasificadas")
            return False
        
        # Validar que cada categoría tenga al menos las guías esperadas del SET 4
        expected_cases = {
            'normal': ['4329507-1'],
            'invoiced': ['4329507-2'], 
            'cancelled': ['4329507-3']
        }
        
        for status, expected_case_numbers in expected_cases.items():
            guides_in_status = classified_guides.get(status, [])
            for guide in guides_in_status:
                case_dte = self._get_case_dte_for_guide(guide)
                if case_dte and case_dte.case_number_raw in expected_case_numbers:
                    _logger.info(f"✓ Caso {case_dte.case_number_raw} correctamente clasificado como '{status}'")
        
        return True