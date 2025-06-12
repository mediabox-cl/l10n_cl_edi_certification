# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError
from lxml import etree
from datetime import datetime
import logging
from .certification_iecv_constants import (
    XML_NAMESPACES, XML_SCHEMA_LOCATION, SII_RESOLUTION_DATE, SII_RESOLUTION_NUMBER,
    BOOK_TYPE_SPECIAL, SEND_TYPE_TOTAL, FOLIO_NOTIFICATION_IEV, FOLIO_NOTIFICATION_IEC
)

_logger = logging.getLogger(__name__)

class CertificationIECVBookXMLBuilder(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.iecv_book.xml_builder'
    _description = 'Constructor de XML para Libro IECV'
    
    def _build_iecv_xml(self):
        """Construye la estructura XML del libro IECV según formato SII"""
        # Crear elemento raíz con namespaces
        root = etree.Element("LibroCompraVenta", nsmap=XML_NAMESPACES)
        root.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", XML_SCHEMA_LOCATION)
        root.set("version", "1.0")
        
        # Crear EnvioLibro con ID
        envio_libro = etree.SubElement(root, "EnvioLibro")
        envio_libro.set("ID", "SetDoc")
        
        # 1. CARÁTULA (obligatoria)
        self._add_caratula(envio_libro)
        
        # 2. RESUMEN PERÍODO (obligatorio)
        self._add_resumen_periodo(envio_libro)
        
        # 3. DETALLE (documentos individuales)
        self._add_detalle(envio_libro)
        
        # 4. TIMESTAMP DE FIRMA (obligatorio)
        self._add_timestamp_firma(envio_libro)
        
        # Convertir a string XML
        xml_string = etree.tostring(root, pretty_print=True, encoding='ISO-8859-1', xml_declaration=True)
        return xml_string
    
    def _add_caratula(self, parent):
        """Añade la sección Carátula del XML"""
        caratula = etree.SubElement(parent, "Caratula")
        
        company = self.certification_process_id.company_id
        
        # RUT Emisor (empresa)
        rut_emisor = company.vat.replace('CL', '') if company.vat else ''
        etree.SubElement(caratula, "RutEmisorLibro").text = rut_emisor
        
        # RUT Enviador (usuario actual - simplificado)
        etree.SubElement(caratula, "RutEnvia").text = rut_emisor
        
        # Período Tributario
        etree.SubElement(caratula, "PeriodoTributario").text = self.period_display
        
        # Resolución SII - Valores específicos para certificación IECV
        etree.SubElement(caratula, "FchResol").text = SII_RESOLUTION_DATE
        etree.SubElement(caratula, "NroResol").text = SII_RESOLUTION_NUMBER
        
        # Tipo de Operación
        tipo_operacion = "VENTA" if self.book_type == 'IEV' else "COMPRA"
        etree.SubElement(caratula, "TipoOperacion").text = tipo_operacion
        
        # Libro ESPECIAL para certificación
        etree.SubElement(caratula, "TipoLibro").text = BOOK_TYPE_SPECIAL
        etree.SubElement(caratula, "TipoEnvio").text = SEND_TYPE_TOTAL
        
        # Folio de notificación específico para certificación
        folio_notificacion = FOLIO_NOTIFICATION_IEV if self.book_type == 'IEV' else FOLIO_NOTIFICATION_IEC
        etree.SubElement(caratula, "FolioNotificacion").text = folio_notificacion
    
    def _add_resumen_periodo(self, parent):
        """Añade la sección Resumen Período"""
        resumen_periodo = etree.SubElement(parent, "ResumenPeriodo")
        
        if self.book_type == 'IEV':
            self._add_resumen_ventas(resumen_periodo)
        else:
            self._add_resumen_compras(resumen_periodo)
    
    def _add_detalle(self, parent):
        """Añade la sección Detalle con documentos individuales"""
        if self.book_type == 'IEV':
            self._add_detalle_ventas(parent)
        else:
            self._add_detalle_compras(parent)
    
    def _add_timestamp_firma(self, parent):
        """Añade el timestamp de firma obligatorio"""
        # Timestamp en formato ISO requerido por SII
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        etree.SubElement(parent, "TmstFirma").text = timestamp
    
    def _apply_digital_signature(self, xml_content):
        """Aplica firma digital real al XML del libro IECV"""
        # Obtener certificado digital de la empresa
        certificate = self.env['certificate.certificate'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('is_valid', '=', True)
        ], limit=1)
        
        if not certificate:
            raise UserError(_('No hay certificado digital válido para firmar el libro IECV'))
        
        # Convertir bytes a string y remover declaración XML si existe
        xml_string = xml_content.decode('ISO-8859-1')
        
        # Remover declaración XML si existe (fix para error de encoding)
        if xml_string.startswith('<?xml'):
            xml_end = xml_string.find('?>')
            if xml_end != -1:
                xml_string = xml_string[xml_end + 2:].lstrip()
        
        # Usar el método de firma real del mixin l10n_cl.edi.util
        # El tipo 'bol' es para libros electrónicos según la implementación de Odoo
        signed_xml = self._sign_full_xml(
            xml_string,  # String sin declaración XML
            certificate,
            'SetDoc',
            'bol',  # tipo para libros electrónicos
            False   # no es documento de boleta
        )
        
        _logger.info("Libro IECV firmado digitalmente correctamente")
        return signed_xml.encode('ISO-8859-1')
