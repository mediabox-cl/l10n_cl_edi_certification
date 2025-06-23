# -*- coding: utf-8 -*-
from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    # Campo para almacenar UOM raw de documentos de exportación
    uom_raw = fields.Char(string='UOM Raw (Exportación)', help='Unidad de medida raw para documentos de exportación')
    
    def _prepare_invoice_line(self, **optional_values):
        """Override para pasar uom_raw a la línea de factura"""
        vals = super()._prepare_invoice_line(**optional_values)
        if self.uom_raw:
            vals['uom_raw'] = self.uom_raw
        return vals

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    # Campo para almacenar UOM raw de documentos de exportación
    uom_raw = fields.Char(string='UOM Raw (Exportación)', help='Unidad de medida raw para documentos de exportación')

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    # Campos para flete y seguro en documentos de exportación
    export_freight_amount = fields.Float(string='Monto Flete', digits=(18, 4), help='MntFlete: Monto del flete para documentos de exportación')
    export_insurance_amount = fields.Float(string='Monto Seguro', digits=(18, 4), help='MntSeguro: Monto del seguro para documentos de exportación')
    export_total_sale_clause_amount = fields.Float(string='Total Cláusula Venta', digits=(18, 2), help='TotClauVenta: Total de la cláusula de venta para exportación')