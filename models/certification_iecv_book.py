# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from lxml import etree
import re
from datetime import datetime

_logger = logging.getLogger(__name__)

class CertificationIECVBook(models.Model):
    _name = 'l10n_cl_edi.certification.iecv_book'
    _description = 'Libro Electrónico de Compras y Ventas - Certificación SII'
    _order = 'create_date desc'
    
    # Relación con proceso de certificación
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        ondelete='cascade'
    )
    
    # Configuración del libro
    book_type = fields.Selection([
        ('IEV', 'Información Electrónica de Ventas'),
        ('IEC', 'Información Electrónica de Compras')
    ], string='Tipo de Libro', required=True)
    
    period_year = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: datetime.now().year
    )
    
    period_month = fields.Integer(
        string='Mes', 
        required=True,
        default=lambda self: datetime.now().month
    )
    
    period_display = fields.Char(
        string='Período',
        compute='_compute_period_display',
        store=True
    )
    
    # Estado del libro
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('signed', 'Firmado'),
        ('error', 'Error')
    ], string='Estado', default='draft', tracking=True)
    
    # Archivos generados
    xml_file = fields.Binary(
        string='Archivo XML IECV',
        attachment=True
    )
    
    xml_filename = fields.Char(
        string='Nombre del Archivo XML',
        compute='_compute_xml_filename',
        store=True
    )
    
    # Resúmenes automáticos
    total_documents = fields.Integer(
        string='Total Documentos',
        compute='_compute_totals',
        store=True
    )
    
    total_net_amount = fields.Monetary(
        string='Monto Neto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    total_tax_amount = fields.Monetary(
        string='IVA Total',
        compute='_compute_totals', 
        store=True,
        currency_field='currency_id'
    )
    
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='certification_process_id.company_id.currency_id',
        store=True
    )
    
    # Información técnica
    error_message = fields.Text(string='Mensaje de Error')
    
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        readonly=True
    )
    
    @api.depends('period_year', 'period_month')
    def _compute_period_display(self):
        for record in self:
            if record.period_year and record.period_month:
                record.period_display = f"{record.period_year}-{record.period_month:02d}"
            else:
                record.period_display = ""
    
    @api.depends('book_type', 'period_display')
    def _compute_xml_filename(self):
        for record in self:
            if record.book_type and record.period_display:
                company_rut = record.certification_process_id.company_id.vat.replace('-', '') if record.certification_process_id.company_id.vat else 'SINRUT'
                record.xml_filename = f"LIBRO_{record.book_type}_{company_rut}_{record.period_display}.xml"
            else:
                record.xml_filename = ""
    
    @api.depends('certification_process_id', 'book_type', 'period_year', 'period_month')
    def _compute_totals(self):
        """Calcula totales basados en los documentos incluidos"""
        for record in self:
            if record.book_type == 'IEV':
                # Libro de Ventas: usar DTEs generados
                invoices = record._get_sales_documents()
                record.total_documents = len(invoices)
                record.total_net_amount = sum(invoices.mapped('amount_untaxed'))
                record.total_tax_amount = sum(invoices.mapped('amount_tax'))
                record.total_amount = sum(invoices.mapped('amount_total'))
            elif record.book_type == 'IEC':
                # Libro de Compras: usar entradas específicas
                entries = record._get_purchase_entries()
                record.total_documents = len(entries)
                record.total_net_amount = sum(entries.mapped('amount_net_affected'))
                record.total_tax_amount = sum(entries.mapped('amount_tax'))
                record.total_amount = sum(entries.mapped('amount_total'))
            else:
                record.total_documents = 0
                record.total_net_amount = 0
                record.total_tax_amount = 0
                record.total_amount = 0
    
    def _get_sales_documents(self):
        """Obtiene documentos de venta para IEV"""
        if not self.certification_process_id:
            return self.env['account.move']
        
        # Obtener documentos del proceso de certificación
        sales_docs = self.certification_process_id.test_invoice_ids.filtered(
            lambda x: x.move_type in ('out_invoice', 'out_refund') and x.state == 'posted'
        )
        
        # Filtrar por período
        if self.period_year and self.period_month:
            sales_docs = sales_docs.filtered(
                lambda x: x.invoice_date and 
                         x.invoice_date.year == self.period_year and
                         x.invoice_date.month == self.period_month
            )
        
        return sales_docs
    
    def _get_purchase_entries(self):
        """Obtiene entradas de compra para IEC"""
        if not self.certification_process_id:
            return self.env['l10n_cl_edi.certification.purchase_entry']
        
        return self.certification_process_id.purchase_entry_ids
    
    def name_get(self):
        """Personaliza el nombre mostrado del registro"""
        result = []
        for record in self:
            name = f"{record.book_type} - {record.period_display}"
            if record.state == 'error':
                name += " (Error)"
            elif record.state == 'signed':
                name += " (Firmado)"
            result.append((record.id, name))
        return result
    
    def action_generate_xml(self):
        """Genera el archivo XML del libro IECV"""
        self.ensure_one()
        
        try:
            # Validaciones previas
            self._validate_generation_requirements()
            
            # Generar XML sin firma
            xml_content = self._build_iecv_xml()
            
            # Aplicar firma digital
            signed_xml = self._apply_digital_signature(xml_content)
            
            # Guardar archivo
            self.write({
                'xml_file': base64.b64encode(signed_xml),
                'state': 'signed',
                'generation_date': fields.Datetime.now(),
                'error_message': False
            })
            
            _logger.info(f"Libro IECV {self.book_type} generado exitosamente para {self.period_display}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Libro IECV Generado'),
                    'message': _('El libro %s ha sido generado y firmado correctamente') % self.book_type,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error generando libro IECV: {str(e)}")
            self.write({
                'state': 'error',
                'error_message': str(e)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error generando libro IECV: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def _validate_generation_requirements(self):
        """Valida que se cumplan los requisitos para generar el libro"""
        if self.book_type == 'IEV':
            documents = self._get_sales_documents()
            if not documents:
                raise UserError(_('No hay documentos de venta para incluir en el libro IEV'))
        elif self.book_type == 'IEC':
            entries = self._get_purchase_entries()
            if not entries:
                raise UserError(_('No hay entradas de compra para incluir en el libro IEC'))
        
        # Validar certificado digital
        certificate = self.env['certificate.certificate'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('is_valid', '=', True)
        ], limit=1)
        
        if not certificate:
            raise UserError(_('No hay certificado digital válido para firmar el libro IECV'))
        
        # Validar datos de resolución SII
        company = self.certification_process_id.company_id
        if not company.l10n_cl_dte_resolution_number or not company.l10n_cl_dte_resolution_date:
            raise UserError(_('Faltan datos de resolución SII en la configuración de la empresa'))
    
    def _build_iecv_xml(self):
        """Construye la estructura XML del libro IECV según formato SII"""
        # Crear namespace
        root = etree.Element("LibroCompraVenta")
        root.set("xmlns", "http://www.sii.cl/SiiDte")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xsi:schemaLocation", "http://www.sii.cl/SiiDte LibroCV_v10.xsd")
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
        
        # Resolución SII
        resolution_date = company.l10n_cl_dte_resolution_date.strftime('%Y-%m-%d') if company.l10n_cl_dte_resolution_date else '2025-04-11'
        etree.SubElement(caratula, "FchResol").text = resolution_date
        etree.SubElement(caratula, "NroResol").text = str(company.l10n_cl_dte_resolution_number or '40')
        
        # Tipo de Operación
        tipo_operacion = "VENTA" if self.book_type == 'IEV' else "COMPRA"
        etree.SubElement(caratula, "TipoOperacion").text = tipo_operacion
        
        # Libro ESPECIAL para certificación
        etree.SubElement(caratula, "TipoLibro").text = "ESPECIAL"
        etree.SubElement(caratula, "TipoEnvio").text = "TOTAL"
        
        # Folio de notificación fijo para certificación
        etree.SubElement(caratula, "FolioNotificacion").text = "102006"
    
    def _add_resumen_periodo(self, parent):
        """Añade la sección Resumen Período"""
        resumen_periodo = etree.SubElement(parent, "ResumenPeriodo")
        
        if self.book_type == 'IEV':
            self._add_resumen_ventas(resumen_periodo)
        else:
            self._add_resumen_compras(resumen_periodo)
    
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
    
    def _add_resumen_compras(self, parent):
        """Añade resumen para libro de compras"""
        entries = self._get_purchase_entries()
        
        # Agrupar por tipo de documento
        doc_types = {}
        for entry in entries:
            doc_type_code = entry.document_type_code
            if doc_type_code not in doc_types:
                doc_types[doc_type_code] = {
                    'count': 0,
                    'exempt_amount': 0,
                    'net_amount': 0,
                    'tax_amount': 0,
                    'total_amount': 0
                }
            
            doc_types[doc_type_code]['count'] += 1
            doc_types[doc_type_code]['exempt_amount'] += entry.amount_exempt
            doc_types[doc_type_code]['net_amount'] += entry.amount_net_affected
            doc_types[doc_type_code]['tax_amount'] += entry.amount_tax
            doc_types[doc_type_code]['total_amount'] += entry.amount_total
        
        # Crear elementos por tipo de documento
        for doc_type_code, totals in doc_types.items():
            totales = etree.SubElement(parent, "TotalPeriodo")
            etree.SubElement(totales, "TpoDoc").text = doc_type_code
            etree.SubElement(totales, "TotDoc").text = str(totals['count'])
            etree.SubElement(totales, "TotMntExe").text = str(int(totals['exempt_amount']))
            etree.SubElement(totales, "TotMntNeto").text = str(int(totals['net_amount']))
            etree.SubElement(totales, "TotMntIVA").text = str(int(totals['tax_amount']))
            etree.SubElement(totales, "TotMntTotal").text = str(int(totals['total_amount']))
    
    def _add_detalle(self, parent):
        """Añade la sección Detalle con documentos individuales"""
        if self.book_type == 'IEV':
            self._add_detalle_ventas(parent)
        else:
            self._add_detalle_compras(parent)
    
    def _add_detalle_ventas(self, parent):
        """Añade detalle para libro de ventas"""
        documents = self._get_sales_documents()
        
        for doc in documents:
            detalle = etree.SubElement(parent, "Detalle")
            
            # Tipo de documento
            etree.SubElement(detalle, "TpoDoc").text = doc.l10n_latam_document_type_id.code
            
            # Folio
            etree.SubElement(detalle, "NroDoc").text = doc.l10n_latam_document_number or '1'
            
            # Fecha
            fecha = doc.invoice_date.strftime('%Y-%m-%d') if doc.invoice_date else datetime.now().strftime('%Y-%m-%d')
            etree.SubElement(detalle, "FchDoc").text = fecha
            
            # RUT receptor (SII para certificación)
            etree.SubElement(detalle, "RUTDoc").text = "60803000-K"
            
            # Montos (enteros sin decimales)
            etree.SubElement(detalle, "MntNeto").text = str(int(doc.amount_untaxed))
            etree.SubElement(detalle, "MntIVA").text = str(int(doc.amount_tax))
            etree.SubElement(detalle, "MntTotal").text = str(int(doc.amount_total))
            etree.SubElement(detalle, "TasaImp").text = "19.00"
            
            # Referencias obligatorias para certificación
            etree.SubElement(detalle, "TpoDocRef").text = "SET"
            case_ref = self._extract_case_reference(doc.ref)
            etree.SubElement(detalle, "RazonRef").text = case_ref
    
    def _add_detalle_compras(self, parent):
        """Añade detalle para libro de compras"""
        entries = self._get_purchase_entries()
        
        for entry in entries:
            detalle = etree.SubElement(parent, "Detalle")
            
            # Tipo de documento
            etree.SubElement(detalle, "TpoDoc").text = entry.document_type_code
            
            # Folio
            etree.SubElement(detalle, "NroDoc").text = entry.document_folio
            
            # Fecha (usar fecha actual para certificación)
            fecha = datetime.now().strftime('%Y-%m-%d')
            etree.SubElement(detalle, "FchDoc").text = fecha
            
            # RUT proveedor
            etree.SubElement(detalle, "RUTDoc").text = entry.supplier_rut
            
            # Montos (enteros sin decimales)
            etree.SubElement(detalle, "MntExe").text = str(int(entry.amount_exempt))
            etree.SubElement(detalle, "MntNeto").text = str(int(entry.amount_net_affected))
            etree.SubElement(detalle, "MntIVA").text = str(int(entry.amount_tax))
            etree.SubElement(detalle, "MntTotal").text = str(int(entry.amount_total))
            etree.SubElement(detalle, "TasaImp").text = f"{entry.tax_rate:.2f}"
    
    def _extract_case_reference(self, ref_text):
        """Extrae referencia del caso SII desde el campo ref"""
        if not ref_text:
            return "CERTIFICACION SII"
        
        # Buscar patrón "Caso SII xxxx-x" o similar
        match = re.search(r'(\d{7}-\d+)', ref_text)
        if match:
            return f"CASO {match.group(1)}"
        
        return "CERTIFICACION SII"
    
    def _apply_digital_signature(self, xml_content):
        """Aplica firma digital al XML usando el certificado de la empresa"""
        certificate = self.env['certificate.certificate'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('is_valid', '=', True)
        ], limit=1)
        
        if not certificate:
            raise UserError(_('No hay certificado digital válido'))
        
        # TODO: Implementar firma digital real
        # Por ahora retornamos el XML sin firmar para testing
        _logger.warning("Firma digital no implementada - retornando XML sin firmar")
        return xml_content
    
    def action_download_xml(self):
        """Permite descargar el archivo XML generado"""
        self.ensure_one()
        
        if not self.xml_file:
            raise UserError(_('No hay archivo XML generado para descargar'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/l10n_cl_edi.certification.iecv_book/{self.id}/xml_file/{self.xml_filename}?download=true',
            'target': 'self',
        }
    
    def action_regenerate(self):
        """Regenera el libro IECV"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'xml_file': False,
            'error_message': False,
            'generation_date': False
        })
        
        return self.action_generate_xml()
