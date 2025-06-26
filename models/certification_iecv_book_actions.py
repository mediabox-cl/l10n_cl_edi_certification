# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from odoo.exceptions import UserError
import base64
import logging

_logger = logging.getLogger(__name__)

class CertificationIECVBookActions(models.AbstractModel):
    _name = 'l10n_cl_edi.certification.iecv_book.actions'
    _description = 'Acciones y Validaciones para Libro IECV'
    
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
        
        # Validar certificado digital obligatorio
        certificate = self.env['certificate.certificate'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('is_valid', '=', True)
        ], limit=1)
        
        if not certificate:
            raise UserError(_('No hay certificado digital válido para la empresa. Es obligatorio para firmar libros electrónicos.'))
        
        # Validar datos de resolución SII (en modo certificación son valores fijos)
        company = self.certification_process_id.company_id
        if not company.l10n_cl_dte_resolution_number or not company.l10n_cl_dte_resolution_date:
            _logger.info("Usando valores por defecto para certificación SII")
        
        # Validar datos específicos según tipo de libro
        if self.book_type == 'IEV':
            self._validate_sales_requirements()
        elif self.book_type == 'IEC':
            self._validate_purchase_requirements()
    
    def _validate_sales_requirements(self):
        """Validaciones específicas para libro de ventas"""
        documents = self._get_sales_documents()
        if not documents:
            # Verificar si hay documentos batch o individuales
            batch_docs = self.certification_process_id.get_batch_documents(['33', '34', '56', '61'])
            all_invoices = self.certification_process_id.test_invoice_ids
            
            if not batch_docs and not all_invoices:
                raise UserError(_('''No hay documentos de venta para incluir en el libro IEV.
                
Esto puede deberse a:
                1. Las facturas no están vinculadas al proceso de certificación
                2. No se han generado aún los DTEs
                3. No se han generado documentos batch para consolidación
                
Solución: 
- Para proceso normal: Use el botón "Recuperar Facturas" en la pestaña Libros IECV
- Para consolidación: Genere primero los sets consolidados en la pestaña Finalización'''))
            else:
                available_docs = len(batch_docs) if batch_docs else len(all_invoices)
                doc_type = "batch" if batch_docs else "individuales"
                raise UserError(_(f'Los {available_docs} documentos {doc_type} no coinciden con el período {self.period_display}'))
    
    def _validate_purchase_requirements(self):
        """Validaciones específicas para libro de compras"""
        entries = self._get_purchase_entries()
        if not entries:
            raise UserError(_('''No hay entradas de compra para incluir en el libro IEC.
            
Solución: Use el botón "Crear Datos de Compras" en la pestaña Libros IECV'''))
        
        # Validar consistencia de montos según requisitos SII
        self._validate_purchase_entries_consistency(entries)
    
    def _validate_purchase_entries_consistency(self, entries):
        """Valida consistencia de montos en entradas de compra según requisitos SII"""
        for entry in entries:
            # Validación 1: Consistencia de IVA calculado
            expected_tax = entry.amount_net_affected * (entry.tax_rate / 100)
            if abs(entry.amount_tax - expected_tax) > 1:  # Tolerancia de 1 peso por redondeo
                raise UserError(_(f'Error en cálculo de IVA para documento {entry.document_folio}: '
                                f'Calculado: {expected_tax:.0f}, Registrado: {entry.amount_tax:.0f}'))
            
            # Validación 2: Consistencia de monto total
            expected_total = entry.amount_exempt + entry.amount_net_affected + entry.amount_tax
            if abs(entry.amount_total - expected_total) > 1:  # Tolerancia de 1 peso por redondeo
                raise UserError(_(f'Error en monto total para documento {entry.document_folio}: '
                                f'Calculado: {expected_total:.0f}, Registrado: {entry.amount_total:.0f}'))
            
            # Validación 3: Monto neto debe existir si hay IVA
            if entry.amount_tax > 0 and entry.amount_net_affected <= 0:
                raise UserError(_(f'Documento {entry.document_folio}: Si hay IVA debe existir monto neto afecto'))
            
            # Validación 4: Total debe ser distinto de cero si hay montos
            if (entry.amount_exempt > 0 or entry.amount_net_affected > 0 or entry.amount_tax > 0) and entry.amount_total <= 0:
                raise UserError(_(f'Documento {entry.document_folio}: Monto total debe ser mayor a cero'))
    
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
