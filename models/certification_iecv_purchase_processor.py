# -*- coding: utf-8 -*-
from odoo import models
from lxml import etree
from .certification_iecv_constants import SII_RUT, DEFAULT_PROPORTIONALITY_FACTOR

class CertificationIECVBookPurchaseProcessor(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.iecv_book.purchase_processor'
    _description = 'Procesador de Compras para Libro IEC'
    
    def _add_resumen_compras(self, parent):
        """Añade resumen para libro de compras con campos especializados"""
        entries = self._get_purchase_entries()
        
        # Agrupar por tipo de documento y calcular totales especializados
        doc_types = {}
        total_iva_uso_comun = 0
        
        # Factor de proporcionalidad para IVA uso común (constante certificación SII)
        factor_proporcionalidad = DEFAULT_PROPORTIONALITY_FACTOR
        
        for entry in entries:
            doc_type_code = entry.document_type_code
            if doc_type_code not in doc_types:
                doc_types[doc_type_code] = {
                    'count': 0,
                    'exempt_amount': 0,
                    'net_amount': 0,
                    'recoverable_tax': 0,  # IVA recuperable
                    'total_amount': 0
                }
            
            doc_types[doc_type_code]['count'] += 1
            doc_types[doc_type_code]['exempt_amount'] += entry.amount_exempt
            doc_types[doc_type_code]['net_amount'] += entry.amount_net_affected
            doc_types[doc_type_code]['total_amount'] += entry.amount_total
            
            # Calcular IVA recuperable según tipo
            if entry.iva_type == 'recoverable':
                doc_types[doc_type_code]['recoverable_tax'] += entry.amount_tax
            elif entry.iva_type == 'common_use':
                # Para IVA uso común, el IVA recuperable se calcula con el factor
                total_iva_uso_comun += entry.amount_tax
                doc_types[doc_type_code]['recoverable_tax'] += 0  # Se maneja por separado
            else:
                # Para retención total, entrega gratuita, etc. - IVA recuperable = 0
                doc_types[doc_type_code]['recoverable_tax'] += 0
        
        # Crear elementos por tipo de documento
        for doc_type_code, totals in doc_types.items():
            totales = etree.SubElement(parent, "TotalPeriodo")
            etree.SubElement(totales, "TpoDoc").text = doc_type_code
            etree.SubElement(totales, "TotDoc").text = str(totals['count'])
            etree.SubElement(totales, "TotMntExe").text = str(int(totals['exempt_amount']))
            etree.SubElement(totales, "TotMntNeto").text = str(int(totals['net_amount']))
            etree.SubElement(totales, "TotMntIVA").text = str(int(totals['recoverable_tax']))
            etree.SubElement(totales, "TotMntTotal").text = str(int(totals['total_amount']))
        
        # Añadir totales de IVA uso común si aplica
        if total_iva_uso_comun > 0:
            credito_iva_uso_comun = int(total_iva_uso_comun * factor_proporcionalidad)
            etree.SubElement(parent, "FctProp").text = f"{factor_proporcionalidad:.2f}"
            etree.SubElement(parent, "TotCredIVAUsoComun").text = str(credito_iva_uso_comun)
    
    def _add_detalle_compras(self, parent):
        """Añade detalle para libro de compras"""
        entries = self._get_purchase_entries()
        
        for entry in entries:
            detalle = etree.SubElement(parent, "Detalle")
            
            # Tipo de documento
            etree.SubElement(detalle, "TpoDoc").text = entry.document_type_code
            
            # Folio
            etree.SubElement(detalle, "NroDoc").text = entry.document_folio
            
            # Fecha (usar fecha del período tributario para certificación)
            fecha = f"{self.period_year}-{self.period_month:02d}-15"
            etree.SubElement(detalle, "FchDoc").text = fecha
            
            # RUT emisor del documento (proveedor en libro de compras)
            rut_emisor = entry.supplier_rut or SII_RUT
            etree.SubElement(detalle, "RUTDoc").text = rut_emisor
            
            # Montos según tipo de IVA (enteros sin decimales)
            etree.SubElement(detalle, "MntExe").text = str(int(entry.amount_exempt))
            etree.SubElement(detalle, "MntNeto").text = str(int(entry.amount_net_affected))
            
            # Manejo especializado según tipo de IVA
            self._add_specialized_iva_fields(detalle, entry)
            
            etree.SubElement(detalle, "MntTotal").text = str(int(entry.amount_total))
            etree.SubElement(detalle, "TasaImp").text = f"{entry.tax_rate:.2f}"
    
    def _add_specialized_iva_fields(self, parent, entry):
        """Añade campos especializados de IVA según tipo de documento del Set de Prueba"""
        
        if entry.iva_type == 'recoverable':
            # IVA normal recuperable
            etree.SubElement(parent, "MntIVA").text = str(int(entry.amount_tax))
            
        elif entry.iva_type == 'common_use':
            # IVA Uso Común - Factor según constante
            total_iva = int(entry.amount_tax)
            etree.SubElement(parent, "MntIVA").text = "0"  # IVA recuperable = 0
            etree.SubElement(parent, "IVAUsoComun").text = str(total_iva)  # Todo el IVA va aquí
            
        elif entry.iva_type == 'total_retention':
            # Retención Total del IVA
            total_iva = int(entry.amount_tax)
            etree.SubElement(parent, "MntIVA").text = "0"  # IVA recuperable = 0
            etree.SubElement(parent, "IVARetTotal").text = str(total_iva)  # IVA retenido totalmente
            
        elif entry.iva_type == 'free_delivery':
            # Entrega Gratuita - IVA no recuperable
            total_iva = int(entry.amount_tax)
            etree.SubElement(parent, "MntIVA").text = "0"  # IVA recuperable = 0 
            etree.SubElement(parent, "MntIVANoRec").text = str(total_iva)  # IVA no recuperable
            etree.SubElement(parent, "CodIVANoRec").text = "4"  # Código para entrega gratuita
            
        else:
            # Caso por defecto
            etree.SubElement(parent, "MntIVA").text = str(int(entry.amount_tax))
