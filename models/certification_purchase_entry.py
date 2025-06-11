# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class CertificationPurchaseEntry(models.Model):
    _name = 'l10n_cl_edi.certification.purchase_entry'
    _description = 'Entrada de Libro de Compras - Certificación SII'
    _order = 'sequence, id'
    
    # Relación con proceso de certificación
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        ondelete='cascade'
    )
    
    sequence = fields.Integer(string='Secuencia', default=10)
    
    # Datos del documento
    document_type_code = fields.Selection([
        ('30', 'Factura'),
        ('33', 'Factura Electrónica'),
        ('60', 'Nota de Crédito'),
        ('61', 'Nota de Crédito Electrónica'),
        ('46', 'Factura de Compra Electrónica'),
    ], string='Tipo de Documento', required=True)
    
    document_folio = fields.Char(string='Folio', required=True)
    
    # RUT del proveedor (generaremos uno válido)
    supplier_rut = fields.Char(string='RUT Proveedor', required=True)
    supplier_name = fields.Char(string='Nombre Proveedor')
    
    # Observaciones del documento
    observations = fields.Text(string='Observaciones')
    
    # Montos
    amount_exempt = fields.Monetary(
        string='Monto Exento',
        currency_field='currency_id',
        default=0.0
    )
    
    amount_net_affected = fields.Monetary(
        string='Monto Neto Afecto',
        currency_field='currency_id', 
        default=0.0
    )
    
    # Campos calculados para IVA
    tax_rate = fields.Float(string='Tasa IVA (%)', default=19.0)
    
    amount_tax = fields.Monetary(
        string='Monto IVA',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    amount_total = fields.Monetary(
        string='Monto Total',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # Configuración especial de IVA
    iva_type = fields.Selection([
        ('recoverable', 'IVA Recuperable'),
        ('common_use', 'IVA Uso Común'),
        ('non_recoverable', 'IVA No Recuperable'),
        ('total_retention', 'Retención Total'),
        ('free_delivery', 'Entrega Gratuita')
    ], string='Tipo de IVA', default='recoverable')
    
    # Factor de proporcionalidad (solo para IVA uso común)
    proportionality_factor = fields.Float(
        string='Factor Proporcionalidad',
        default=0.0,
        help='Factor para IVA uso común (ej: 0.60)'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='certification_process_id.company_id.currency_id',
        store=True
    )
    
    # Campo para identificar el caso específico del set
    sii_case_reference = fields.Char(
        string='Referencia Caso SII',
        help='Referencia al caso específico del set de pruebas'
    )
    
    @api.depends('amount_net_affected', 'tax_rate', 'amount_exempt')
    def _compute_amounts(self):
        """Calcula IVA y total según el tipo de documento"""
        for record in self:
            if record.amount_net_affected and record.tax_rate:
                record.amount_tax = record.amount_net_affected * (record.tax_rate / 100)
            else:
                record.amount_tax = 0.0
            
            record.amount_total = record.amount_exempt + record.amount_net_affected + record.amount_tax
    
    def name_get(self):
        """Personaliza el nombre mostrado"""
        result = []
        for record in self:
            doc_type_name = dict(record._fields['document_type_code'].selection).get(record.document_type_code, '')
            name = f"{doc_type_name} {record.document_folio}"
            if record.supplier_name:
                name += f" - {record.supplier_name}"
            result.append((record.id, name))
        return result
    
    @api.model
    def create_sample_purchase_entries(self, certification_process_id):
        """Crea las entradas de ejemplo basadas en el SET LIBRO DE COMPRAS 4267230"""
        
        # Datos del SET LIBRO DE COMPRAS según el archivo de texto
        sample_entries = [
            {
                'sequence': 10,
                'document_type_code': '30',
                'document_folio': '234',
                'supplier_rut': '12345678-9',
                'supplier_name': 'Proveedor Con Derecho A Crédito S.A.',
                'observations': 'FACTURA DEL GIRO CON DERECHO A CREDITO',
                'amount_exempt': 0,
                'amount_net_affected': 31501,
                'iva_type': 'recoverable',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_1'
            },
            {
                'sequence': 20,
                'document_type_code': '33',
                'document_folio': '32',
                'supplier_rut': '87654321-K',
                'supplier_name': 'Proveedor Electrónico Ltda.',
                'observations': 'FACTURA DEL GIRO CON DERECHO A CREDITO',
                'amount_exempt': 9415,
                'amount_net_affected': 8107,
                'iva_type': 'recoverable',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_2'
            },
            {
                'sequence': 30,
                'document_type_code': '30',
                'document_folio': '781',
                'supplier_rut': '11223344-5',
                'supplier_name': 'Proveedor Uso Común S.A.',
                'observations': 'FACTURA CON IVA USO COMUN',
                'amount_exempt': 0,
                'amount_net_affected': 29908,
                'iva_type': 'common_use',
                'proportionality_factor': 0.60,
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_3'
            },
            {
                'sequence': 40,
                'document_type_code': '60',
                'document_folio': '451',
                'supplier_rut': '12345678-9',
                'supplier_name': 'Proveedor Con Derecho A Crédito S.A.',
                'observations': 'NOTA DE CREDITO POR DESCUENTO A FACTURA 234',
                'amount_exempt': 0,
                'amount_net_affected': 2786,
                'iva_type': 'recoverable',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_4'
            },
            {
                'sequence': 50,
                'document_type_code': '33',
                'document_folio': '67',
                'supplier_rut': '55666777-8',
                'supplier_name': 'Proveedor Entrega Gratuita Ltda.',
                'observations': 'ENTREGA GRATUITA DEL PROVEEDOR',
                'amount_exempt': 0,
                'amount_net_affected': 10699,
                'iva_type': 'free_delivery',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_5'
            },
            {
                'sequence': 60,
                'document_type_code': '46',
                'document_folio': '9',
                'supplier_rut': '99887766-1',
                'supplier_name': 'Proveedor Retención IVA S.A.',
                'observations': 'COMPRA CON RETENCION TOTAL DEL IVA',
                'amount_exempt': 0,
                'amount_net_affected': 9912,
                'iva_type': 'total_retention',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_6'
            },
            {
                'sequence': 70,
                'document_type_code': '60',
                'document_folio': '211',
                'supplier_rut': '87654321-K',
                'supplier_name': 'Proveedor Electrónico Ltda.',
                'observations': 'NOTA DE CREDITO POR DESCUENTO FACTURA ELECTRONICA 32',
                'amount_exempt': 0,
                'amount_net_affected': 5930,
                'iva_type': 'recoverable',
                'sii_case_reference': 'LIBRO_COMPRAS_ENTRY_7'
            }
        ]
        
        created_entries = []
        for entry_data in sample_entries:
            entry_data['certification_process_id'] = certification_process_id
            entry = self.create(entry_data)
            created_entries.append(entry)
            _logger.info(f"Creada entrada de compra: {entry.name_get()[0][1]}")
        
        return created_entries
