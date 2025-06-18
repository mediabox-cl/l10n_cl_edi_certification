# -*- coding: utf-8 -*-
from odoo import models, _
from lxml import etree
import logging

_logger = logging.getLogger(__name__)

class CertificationDeliveryGuideBookXMLBuilder(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.delivery_guide_book.xml_builder'
    _description = 'Constructor XML para Libro de Guías de Despacho'
    
    def _build_delivery_guide_book_xml(self):
        """
        Construye el XML completo del libro de guías de despacho.
        Basado en especificaciones SII v1.0 actualizadas.
        """
        self.ensure_one()
        
        _logger.info(f"Iniciando construcción XML libro guías para período {self.period_display}")
        
        # Crear elemento raíz con namespace correcto
        root = etree.Element("LibroGuia", 
                           version="1.0",
                           nsmap={None: "http://www.sii.cl/SiiDte"})
        
        # Agregar declaración de schema
        root.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", 
                "http://www.sii.cl/SiiDte LibroGuia_v10.xsd")
        
        # Crear EnvioLibro con ID
        envio_libro = etree.SubElement(root, "EnvioLibro", ID="LibroGuia")
        
        # 1. Carátula (obligatoria)
        caratula = etree.SubElement(envio_libro, "Caratula")
        self._add_delivery_guide_cover(caratula)
        
        # 2. Resumen Período (obligatorio para TOTAL)
        self._add_resumen_periodo(envio_libro)
        
        # 3. Detalle de guías
        self._add_delivery_guide_details(envio_libro)
        
        xml_string = etree.tostring(root, pretty_print=True, encoding='UTF-8', xml_declaration=True)
        
        _logger.info(f"XML libro guías construido exitosamente, tamaño: {len(xml_string)} bytes")
        
        return xml_string
    
    def _add_delivery_guide_cover(self, caratula):
        """
        Añade la carátula del libro de guías según especificación SII.
        """
        company = self.certification_process_id.company_id
        
        # RUT emisor (empresa que emite las guías)
        rut_emisor = self._format_rut(company.vat) if company.vat else "76354771-K"
        etree.SubElement(caratula, "RutEmisor").text = rut_emisor
        
        # RUT envía (usuario autorizado - mismo que emisor para certificación)
        etree.SubElement(caratula, "RutEnvia").text = rut_emisor
        
        # Período tributario (AAAA-MM)
        etree.SubElement(caratula, "PeriodoTributario").text = f"{self.period_year}-{self.period_month:02d}"
        
        # Fecha resolución SII
        if company.l10n_cl_dte_resolution_date:
            fecha_resolucion = company.l10n_cl_dte_resolution_date.strftime('%Y-%m-%d')
        else:
            fecha_resolucion = "2006-02-14"  # Fecha por defecto SII
        etree.SubElement(caratula, "FchResol").text = fecha_resolucion
        
        # Número resolución SII
        numero_resolucion = company.l10n_cl_dte_resolution_number or "102006"
        etree.SubElement(caratula, "NroResol").text = str(numero_resolucion)
        
        # Tipo de libro: ESPECIAL (para certificación)
        etree.SubElement(caratula, "TipoLibro").text = "ESPECIAL"
        
        # Tipo de envío: TOTAL (envío completo del período)
        etree.SubElement(caratula, "TipoEnvio").text = "TOTAL"
        
        # Folio notificación (simulado para certificación)
        etree.SubElement(caratula, "FolioNotificacion").text = "001"
        
        _logger.info(f"Carátula agregada - RUT Emisor: {rut_emisor}, Período: {self.period_year}-{self.period_month:02d}")
    
    def _add_resumen_periodo(self, envio_libro):
        """
        Añade ResumenPeriodo según especificación SII.
        Obligatorio para envíos TOTAL.
        """
        _logger.info("Generando ResumenPeriodo")
        
        classified_guides = self._classify_delivery_guides()
        
        # Crear elemento ResumenPeriodo
        resumen_periodo = etree.SubElement(envio_libro, "ResumenPeriodo")
        
        # Calcular totales por categoría
        guides_venta = []
        guides_no_venta = []
        folios_anulados = 0
        guias_anuladas = 0
        
        for status, guides in classified_guides.items():
            for guide in guides:
                case_dte = self._get_case_dte_for_guide(guide)
                if not case_dte:
                    continue
                    
                # Clasificar según tipo de operación
                if status == 'cancelled':
                    if case_dte.case_number_raw == '4329507-3':  # Anulada
                        guias_anuladas += 1
                    else:
                        folios_anulados += 1
                elif self._is_sale_operation(case_dte):
                    guides_venta.append(guide)
                else:
                    guides_no_venta.append(guide)
        
        # Totales de folios anulados
        etree.SubElement(resumen_periodo, "TotFoliosAnulados").text = str(folios_anulados)
        
        # Totales de guías anuladas
        etree.SubElement(resumen_periodo, "TotGuiasAnuladas").text = str(guias_anuladas)
        
        # Totales de guías de venta
        etree.SubElement(resumen_periodo, "TotGuiasVenta").text = str(len(guides_venta))
        
        # Monto total de guías de venta
        monto_venta = sum(self._calculate_guide_amount(guide) for guide in guides_venta)
        etree.SubElement(resumen_periodo, "TotMntGuiasVenta").text = str(int(monto_venta))
        
        # Agrupar guías no venta por tipo de traslado
        self._add_guias_no_venta_summary(resumen_periodo, guides_no_venta)
        
        _logger.info(f"ResumenPeriodo - Ventas: {len(guides_venta)}, No Ventas: {len(guides_no_venta)}, Anuladas: {guias_anuladas}")
    
    def _add_guias_no_venta_summary(self, resumen_periodo, guides_no_venta):
        """
        Añade resumen de guías no venta agrupadas por código de traslado.
        """
        # Agrupar por código de traslado (2-7)
        traslados = {}
        
        for guide in guides_no_venta:
            case_dte = self._get_case_dte_for_guide(guide)
            if not case_dte:
                continue
                
            # Determinar código de traslado
            codigo_traslado = self._get_transfer_type_code(case_dte)
            if codigo_traslado in range(2, 8):
                if codigo_traslado not in traslados:
                    traslados[codigo_traslado] = []
                traslados[codigo_traslado].append(guide)
        
        # Crear elementos TotGuiasNoVenta
        for codigo, guides in traslados.items():
            tot_no_venta = etree.SubElement(resumen_periodo, "TotGuiasNoVenta")
            etree.SubElement(tot_no_venta, "CodTraslado").text = str(codigo)
            etree.SubElement(tot_no_venta, "CantGuias").text = str(len(guides))
            
            # Monto (0 para traslados internos, calculado para otros)
            if codigo == 5:  # Traslado interno
                monto = 0
            else:
                monto = sum(self._calculate_guide_amount(guide) for guide in guides)
            etree.SubElement(tot_no_venta, "MntGuias").text = str(int(monto))
            
            _logger.info(f"TotGuiasNoVenta - Código {codigo}: {len(guides)} guías, monto: {int(monto)}")
    
    def _is_sale_operation(self, case_dte):
        """
        Determina si una guía constituye operación de venta.
        """
        motivo = (case_dte.dispatch_motive_raw or '').upper()
        return 'VENTA' in motivo
    
    def _get_transfer_type_code(self, case_dte):
        """
        Obtiene el código de tipo de traslado según SII (1-7).
        """
        motivo = (case_dte.dispatch_motive_raw or '').upper()
        
        if 'VENTA' in motivo:
            return 1  # Operación constituye venta
        elif 'TRASLADO INTERNO' in motivo or 'ENTRE BODEGAS' in motivo:
            return 5  # Traslados internos
        elif 'CONSIGNACION' in motivo:
            return 3  # Consignaciones
        elif 'DEMOSTRACION' in motivo:
            return 4  # Productos en demostración
        elif 'DEVOLUCION' in motivo:
            return 7  # Guía de devolución
        else:
            return 6  # Otros traslados no venta
    
    def _add_delivery_guide_details(self, envio_libro):
        """
        Añade detalle de cada guía según especificación SII.
        Una línea por cada guía de despacho.
        """
        _logger.info("Agregando detalle de guías")
        
        classified_guides = self._classify_delivery_guides()
        total_guides = 0
        
        # Procesar todas las guías sin importar su estado
        for status, guides in classified_guides.items():
            _logger.info(f"Procesando {len(guides)} guías en estado '{status}'")
            
            for guide in guides:
                detalle = etree.SubElement(envio_libro, "Detalle")
                self._add_single_guide_detail(detalle, guide, status)
                total_guides += 1
        
        _logger.info(f"Total {total_guides} líneas de detalle agregadas")
    
    def _add_single_guide_detail(self, detalle, guide, status):
        """
        Añade detalle de una guía individual según especificación SII.
        """
        case_dte = self._get_case_dte_for_guide(guide)
        
        # Folio de la guía (obligatorio)
        folio = self._get_guide_folio(guide, case_dte)
        etree.SubElement(detalle, "Folio").text = str(folio)
        
        # Tipo de operación (1-7 según SII)
        tipo_operacion = self._get_transfer_type_code(case_dte) if case_dte else 1
        etree.SubElement(detalle, "TipoOper").text = str(tipo_operacion)
        
        # Fecha de emisión (AAAA-MM-DD)
        fecha = self._get_guide_date(guide, case_dte)
        etree.SubElement(detalle, "FchDoc").text = fecha
        
        # RUT receptor (obligatorio para ventas)
        if guide.partner_id and guide.partner_id.vat:
            rut_receptor = self._format_rut(guide.partner_id.vat)
            etree.SubElement(detalle, "RUTDoc").text = rut_receptor
            
            # Razón social receptor
            etree.SubElement(detalle, "RznSoc").text = guide.partner_id.name[:50]  # Máximo 50 caracteres
        
        # Montos (solo para ventas - tipo operación 1)
        if tipo_operacion == 1:
            monto_total = self._calculate_guide_amount(guide)
            if monto_total > 0:
                # Calcular montos con IVA
                monto_neto = int(monto_total / 1.19)
                iva = int(monto_total - monto_neto)
                
                etree.SubElement(detalle, "MntNeto").text = str(monto_neto)
                etree.SubElement(detalle, "TasaImp").text = "19.00"
                etree.SubElement(detalle, "IVA").text = str(iva)
                etree.SubElement(detalle, "MntTotal").text = str(int(monto_total))
        
        # Estado de anulación (0=Normal, 1=Anulado previo, 2=Anulado posterior)
        anulado = self._get_anulado_status(guide, case_dte, status)
        if anulado != '0':
            etree.SubElement(detalle, "Anulado").text = anulado
        
        # Referencias a facturas (si fue facturada posteriormente)
        if status == 'invoiced':
            self._add_invoice_reference(detalle, guide, case_dte)
        
        _logger.info(f"Detalle agregado - Folio: {folio}, TipoOper: {tipo_operacion}, Status: {status}")
    
    def _get_anulado_status(self, guide, case_dte, status):
        """
        Determina el estado de anulación según especificación SII.
        """
        if status == 'cancelled':
            if case_dte and case_dte.case_number_raw == '4329507-3':
                return '2'  # Anulado posterior al envío
            else:
                return '1'  # Anulado previo al envío
        return '0'  # Normal
    
    def _add_invoice_reference(self, detalle, guide, case_dte):
        """
        Añade referencia a factura relacionada (si existe).
        """
        # En contexto de certificación, simular referencia a factura
        if case_dte and case_dte.case_number_raw == '4329507-2':
            # Simular factura relacionada para caso específico
            etree.SubElement(detalle, "TpoDocRef").text = "33"  # Factura electrónica
            etree.SubElement(detalle, "FolioDocRef").text = f"F{case_dte.id}"
            etree.SubElement(detalle, "FchDocRef").text = f"{self.period_year}-{self.period_month:02d}-20"
    
    def _get_guide_folio(self, guide, case_dte):
        """
        Obtiene el folio de la guía.
        """
        # Intentar obtener el número de documento oficial
        if hasattr(guide, 'l10n_latam_document_number') and guide.l10n_latam_document_number:
            return guide.l10n_latam_document_number
        
        # Usar ID del caso DTE como folio para certificación
        if case_dte:
            return case_dte.id
        
        # Fallback: usar ID del picking
        return guide.id
    
    def _get_guide_date(self, guide, case_dte):
        """
        Obtiene la fecha de emisión de la guía.
        """
        # Usar fecha de creación del picking
        if guide.create_date:
            return guide.create_date.strftime('%Y-%m-%d')
        
        # Fecha por defecto dentro del período
        return self._get_default_date()
    
    
    def _format_rut(self, vat):
        """
        Formatea un RUT al formato requerido por SII (sin puntos, con guión).
        """
        if not vat:
            return ""
        
        # Limpiar el RUT de caracteres no deseados
        rut = str(vat).replace(".", "").replace(" ", "").upper()
        
        # Si no tiene guión, agregarlo antes del último dígito
        if "-" not in rut and len(rut) > 1:
            rut = rut[:-1] + "-" + rut[-1]
        
        return rut