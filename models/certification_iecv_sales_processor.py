# -*- coding: utf-8 -*-
from odoo import models
from lxml import etree
from .certification_iecv_constants import SII_RUT

class CertificationIECVBookSalesProcessor(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.iecv_book.sales_processor'
    _description = 'Procesador de Ventas para Libro IEV'
    
    def _add_resumen_ventas(self, parent):
        """Añade resumen para libro de ventas"""
        documents = self._get_sales_documents()
        
        # Agrupar por tipo de documento
        doc_types = {}
        for doc in documents:
            doc_type_code = doc.l10n_latam_document_type_id.code
            if doc_type_code not in doc_types:
                doc_types[doc_type_code] = {
                    'count': 0,
                    'net_amount': 0,
                    'tax_amount': 0,
                    'total_amount': 0
                }
            
            doc_types[doc_type_code]['count'] += 1
            doc_types[doc_type_code]['net_amount'] += doc.amount_untaxed
            doc_types[doc_type_code]['tax_amount'] += doc.amount_tax
            doc_types[doc_type_code]['total_amount'] += doc.amount_total
        
        # Crear elementos por tipo de documento
        for doc_type_code, totals in doc_types.items():
            totales = etree.SubElement(parent, "TotalPeriodo")
            etree.SubElement(totales, "TpoDoc").text = doc_type_code
            etree.SubElement(totales, "TotDoc").text = str(totals['count'])
            etree.SubElement(totales, "TotMntExe").text = "0"  # Por ahora sin exentos
            etree.SubElement(totales, "TotMntNeto").text = str(int(totals['net_amount']))
            etree.SubElement(totales, "TotMntIVA").text = str(int(totals['tax_amount']))
            etree.SubElement(totales, "TotMntTotal").text = str(int(totals['total_amount']))
    
    def _add_detalle_ventas(self, parent):
        """Añade detalle para libro de ventas"""
        documents = self._get_sales_documents()
        
        for doc in documents:
            detalle = etree.SubElement(parent, "Detalle")
            
            # Tipo de documento
            etree.SubElement(detalle, "TpoDoc").text = doc.l10n_latam_document_type_id.code
            
            # Folio
            etree.SubElement(detalle, "NroDoc").text = doc.l10n_latam_document_number or '1'
            
            # Fecha (usar fecha del período tributario para certificación)
            # Para certificación SII: usar fechas consistentes del período
            if doc.invoice_date:
                fecha = doc.invoice_date.strftime('%Y-%m-%d')
            else:
                # Fecha por defecto dentro del período tributario
                fecha = f"{self.period_year}-{self.period_month:02d}-15"
            etree.SubElement(detalle, "FchDoc").text = fecha
            
            # RUT receptor (SII para proceso de certificación)
            etree.SubElement(detalle, "RUTDoc").text = SII_RUT
            
            # Montos (enteros sin decimales)
            etree.SubElement(detalle, "MntNeto").text = str(int(doc.amount_untaxed))
            etree.SubElement(detalle, "MntIVA").text = str(int(doc.amount_tax))
            etree.SubElement(detalle, "MntTotal").text = str(int(doc.amount_total))
            etree.SubElement(detalle, "TasaImp").text = "19.00"
