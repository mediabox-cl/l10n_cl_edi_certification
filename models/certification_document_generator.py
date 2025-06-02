from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CertificationDocumentGenerator(models.TransientModel):
    _name = 'l10n_cl_edi.certification.document.generator'
    _description = 'Generador de Documentos para Certificación SII'

    # Campos principales
    dte_case_id = fields.Many2one(
        'l10n_cl_edi.certification.case.dte',
        string='Caso DTE',
        required=True,
        help='Caso DTE a partir del cual generar el documento'
    )
    certification_process_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        help='Proceso de certificación al que pertenece el caso'
    )

    # Campos computados para información
    document_type_code = fields.Char(
        related='dte_case_id.document_type_code',
        string='Tipo de Documento',
        readonly=True
    )
    case_number = fields.Char(
        related='dte_case_id.case_number_raw',
        string='Número de Caso',
        readonly=True
    )

    def generate_document(self):
        """
        Método principal que genera documentos usando el flujo estándar de Odoo:
        sale.order → confirm → create_invoice (solo borrador)
        
        Este enfoque elimina problemas con rating mixin y usa el flujo nativo.
        """
        self.ensure_one()
        
        # Verificar que el caso esté en estado correcto
        if self.dte_case_id.generation_status != 'pending':
            raise UserError(_("El caso DTE ya ha sido procesado"))
        
        _logger.info("=== INICIANDO GENERACIÓN CON FLUJO SALE.ORDER ===")
        _logger.info("Caso: %s, Tipo: %s", self.dte_case_id.case_number_raw, self.dte_case_id.document_type_code)
        
        try:
            # 1. Crear sale.order desde el caso DTE
            _logger.info("PASO 1: Creando sale.order desde caso DTE")
            sale_order = self._create_sale_order_from_dte_case()
            _logger.info("✓ Sale.order creado: %s (ID: %s)", sale_order.name, sale_order.id)
            
            # 2. Confirmar el sale.order
            _logger.info("PASO 2: Confirmando sale.order")
            sale_order.action_confirm()
            _logger.info("✓ Sale.order confirmado: %s", sale_order.name)
            
            # 3. Crear factura desde sale.order
            _logger.info("PASO 3: Creando factura desde sale.order")
            invoices = sale_order._create_invoices(final=False)  # Crear en borrador
            if not invoices:
                raise UserError(_("No se pudo crear la factura desde el pedido de venta"))
            
            invoice = invoices[0]
            _logger.info("✓ Factura creada en borrador: %s (ID: %s)", invoice.name, invoice.id)
            
            # 4. Configurar campos específicos del DTE en la factura
            _logger.info("PASO 4: Configurando campos específicos del DTE")
            self._configure_dte_fields_on_invoice(invoice)
            _logger.info("✓ Campos DTE configurados")
            
            # 5. Aplicar descuentos globales si corresponde
            if self.dte_case_id.global_discount_percent and self.dte_case_id.global_discount_percent > 0:
                _logger.info("PASO 5: Aplicando descuento global de %s%%", self.dte_case_id.global_discount_percent)
                self._apply_global_discount_to_invoice(invoice, self.dte_case_id.global_discount_percent)
                _logger.info("✓ Descuento global aplicado")
            
            # 6. Crear referencias entre documentos
            _logger.info("PASO 6: Creando referencias entre documentos")
            self._create_document_references_on_invoice(invoice)
            _logger.info("✓ Referencias creadas")
            
            # 7. MANTENER FACTURA EN BORRADOR (no hacer action_post)
            _logger.info("PASO 7: Factura mantenida en borrador para revisión")
            _logger.info("✓ Factura en borrador: %s", invoice.name)
            
            # 8. Actualizar el estado del caso DTE
            _logger.info("PASO 8: Actualizando estado del caso DTE")
            self.dte_case_id.write({
                'generated_account_move_id': invoice.id,
                'generation_status': 'generated',
                'error_message': False
            })
            _logger.info("✓ Estado del caso actualizado")
            
            _logger.info("=== GENERACIÓN COMPLETADA EXITOSAMENTE ===")
            _logger.info("Factura en borrador: %s (ID: %s)", invoice.name, invoice.id)
            return invoice
            
        except Exception as e:
            _logger.error("=== ERROR EN GENERACIÓN ===")
            _logger.error("Caso: %s", self.dte_case_id.case_number_raw)
            _logger.error("Error: %s", str(e))
            _logger.error("Tipo de error: %s", type(e).__name__)
            
            # Marcar el caso como error
            self.dte_case_id.write({
                'generation_status': 'error',
                'error_message': str(e)
            })
            raise

    def _create_sale_order_from_dte_case(self):
        """
        Crea un sale.order a partir del caso DTE.
        Sigue el patrón del conector de Shopify.
        """
        self.ensure_one()
        
        # Obtener partner ficticio para certificación
        partner = self.certification_process_id.certification_partner_id
        if not partner:
            raise UserError(_("No se ha configurado el partner ficticio para certificación"))
        
        # Preparar valores del sale.order
        order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'company_id': self.certification_process_id.company_id.id,
            'date_order': fields.Datetime.now(),
            'user_id': self.env.user.id,
            'team_id': False,  # Sin equipo de ventas específico
            'note': f'Documento de certificación SII - Caso {self.dte_case_id.case_number_raw}',
            # Campos específicos para certificación
            'l10n_cl_edi_certification_id': self.certification_process_id.id,
        }
        
        # Crear el sale.order
        sale_order = self.env['sale.order'].create(order_vals)
        
        # Crear las líneas del pedido
        self._create_sale_order_lines(sale_order)
        
        return sale_order

    def _create_sale_order_lines(self, sale_order):
        """
        Crea las líneas del sale.order a partir de los items del caso DTE.
        """
        self.ensure_one()
        
        for sequence, item in enumerate(self.dte_case_id.item_ids, 1):
            # Obtener o crear producto
            product = self._get_product_for_dte_item(item.name)
            
            # Preparar valores de la línea
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.id,
                'name': item.name,
                'product_uom_qty': item.quantity,
                'price_unit': item.price_unit,
                'discount': item.discount_percent or 0.0,
                'sequence': sequence * 10,
            }
            
            # Configurar impuestos según si es exento o no
            if item.is_exempt:
                line_vals['tax_id'] = [(6, 0, [])]  # Sin impuestos
            else:
                # Usar el impuesto configurado por defecto
                if self.certification_process_id.default_tax_id:
                    line_vals['tax_id'] = [(6, 0, [self.certification_process_id.default_tax_id.id])]
                else:
                    # Fallback: buscar IVA 19%
                    iva_tax = self.env['account.tax'].search([
                        ('company_id', '=', self.certification_process_id.company_id.id),
                        ('type_tax_use', '=', 'sale'),
                        ('amount_type', '=', 'percent'),
                        ('amount', '=', 19),
                        ('country_id.code', '=', 'CL')
                    ], limit=1)
                    
                    if iva_tax:
                        line_vals['tax_id'] = [(6, 0, [iva_tax.id])]
                    else:
                        _logger.warning("No se encontró impuesto IVA al 19%% para item '%s'", item.name)
            
            # Crear la línea
            self.env['sale.order.line'].create(line_vals)

    def _get_product_for_dte_item(self, item_name):
        """
        Obtiene o crea un producto para el item del DTE.
        Crea productos únicos sin SKU genérico para evitar duplicados.
        """
        # Buscar producto existente por nombre exacto
        product = self.env['product.product'].search([
            ('name', '=', item_name)
        ], limit=1)
        
        if product:
            _logger.info("Producto existente encontrado: %s (ID: %s)", product.name, product.id)
            return product
        
        # Crear producto único para este item (SIN default_code para evitar SKU en líneas)
        _logger.info("Creando nuevo producto: %s", item_name)
        product = self.env['product.product'].create({
            'name': item_name,  # Nombre exacto del item DTE
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 0,
            'standard_price': 0,
            'sale_ok': True,
            'purchase_ok': False,
            # NO agregar default_code para evitar que aparezca SKU en las líneas
        })
        
        _logger.info("✓ Producto creado: %s (ID: %s)", product.name, product.id)
        return product

    def _configure_dte_fields_on_invoice(self, invoice):
        """
        Configura campos específicos del DTE en la factura generada.
        Incluye forzar el diario de certificación y logging para debug.
        """
        self.ensure_one()
        
        # Buscar el tipo de documento SII
        doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', self.dte_case_id.document_type_code),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if not doc_type:
            raise UserError(_("Tipo de documento SII '%s' no encontrado") % self.dte_case_id.document_type_code)
        
        _logger.info("Tipo de documento encontrado: %s (%s)", doc_type.name, doc_type.code)
        
        # Configurar valores específicos del DTE
        invoice_vals = {
            'l10n_latam_document_type_id': doc_type.id,
            'invoice_date': fields.Date.context_today(self),
            'ref': f'Caso SII {self.dte_case_id.case_number_raw}',
        }
        
        # FORZAR el uso del diario de certificación
        journal = self.certification_process_id.certification_journal_id
        if journal:
            _logger.info("Configurando diario de certificación: %s (ID: %s)", journal.name, journal.id)
            _logger.info("Diario usa documentos: %s", journal.l10n_latam_use_documents)
            _logger.info("Diario tipo: %s", journal.type)
            invoice_vals['journal_id'] = journal.id
        else:
            _logger.warning("⚠️  No hay diario de certificación configurado - usando diario por defecto")
        
        # Configurar campos específicos según el tipo de documento
        if self.dte_case_id.document_type_code == '52':  # Guía de despacho
            invoice_vals.update({
                'l10n_cl_dte_gd_move_reason': self._map_dispatch_motive_to_code(self.dte_case_id.dispatch_motive_raw),
                'l10n_cl_dte_gd_transport_type': self._map_dispatch_transport_to_code(self.dte_case_id.dispatch_transport_type_raw),
            })
        
        # Verificar configuración de la empresa
        company = self.certification_process_id.company_id
        _logger.info("Empresa: %s, País: %s", company.name, company.country_id.code)
        
        # Aplicar los valores
        invoice.write(invoice_vals)
        
        # Verificar después de la configuración
        _logger.info("✓ Factura configurada:")
        _logger.info("  - Diario: %s (ID: %s)", invoice.journal_id.name, invoice.journal_id.id)
        _logger.info("  - Tipo documento: %s (%s)", invoice.l10n_latam_document_type_id.name, invoice.l10n_latam_document_type_id.code)
        _logger.info("  - Fecha: %s", invoice.invoice_date)
        _logger.info("  - Referencia: %s", invoice.ref)

    def _apply_global_discount_to_invoice(self, invoice, discount_percent):
        """
        Aplica un descuento global a la factura usando el producto de descuento.
        """
        if not discount_percent or discount_percent <= 0:
            return
        
        # Solo aplicar a líneas afectas (no exentas)
        affected_lines = invoice.invoice_line_ids.filtered(lambda l: l.tax_ids and not l.l10n_latam_vat_exempt)
        
        if not affected_lines:
            _logger.warning("No se pudo aplicar descuento global: no hay líneas afectas")
            return
        
        # Calcular el monto total de los ítems afectos
        total_affected = sum(line.price_subtotal for line in affected_lines)
        discount_amount = total_affected * (discount_percent / 100.0)
        
        if discount_amount <= 0:
            return
        
        # Usar el producto de descuento configurado
        discount_product = self.certification_process_id.default_discount_product_id
        if not discount_product:
            # Crear producto de descuento si no existe
            discount_product = self.env['product.product'].create({
                'name': 'Descuento Global',
                'default_code': 'DISCOUNT_GLOBAL',
                'type': 'service',
                'invoice_policy': 'order',
                'sale_ok': True,
                'purchase_ok': False,
            })
            self.certification_process_id.default_discount_product_id = discount_product.id
        
        # Obtener los impuestos de las líneas afectas
        tax_ids = affected_lines[0].tax_ids.ids if affected_lines and affected_lines[0].tax_ids else []
        
        # Crear la línea de descuento
        discount_line_vals = {
            'product_id': discount_product.id,
            'name': f'Descuento Global {discount_percent}%',
            'price_unit': -discount_amount,
            'quantity': 1.0,
            'tax_ids': [(6, 0, tax_ids)],
            'move_id': invoice.id,
        }
        
        self.env['account.move.line'].create(discount_line_vals)
        
        # Recalcular totales
        invoice._recompute_dynamic_lines()

    def _create_document_references_on_invoice(self, invoice):
        """
        Crea las referencias entre documentos en la factura.
        """
        self.ensure_one()
        
        references_to_create = []
        
        # Agregar la referencia obligatoria al SET
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if set_doc_type:
            references_to_create.append({
                'move_id': invoice.id,
                'l10n_cl_reference_doc_type_id': set_doc_type.id,
                'origin_doc_number': '',
                'reason': f'CASO {self.dte_case_id.case_number_raw}',
                'date': fields.Date.context_today(self),
            })
        
        # Agregar las demás referencias del caso DTE
        for ref in self.dte_case_id.reference_ids:
            # Buscar el documento referenciado si existe
            referenced_move = self._get_referenced_move(ref.referenced_sii_case_number)
            
            reference_values = {
                'move_id': invoice.id,
                'l10n_cl_reference_doc_type_id': (referenced_move.l10n_latam_document_type_id.id 
                                                if referenced_move else False),
                'origin_doc_number': (referenced_move.l10n_latam_document_number 
                                    if referenced_move else f"REF-{ref.referenced_sii_case_number}"),
                'reference_doc_code': ref.reference_code,
                'reason': ref.reason_raw,
                'date': fields.Date.context_today(self),
            }
            references_to_create.append(reference_values)
        
        # Crear todas las referencias
        if references_to_create:
            self.env['l10n_cl.account.invoice.reference'].create(references_to_create)

    def _get_referenced_move(self, referenced_sii_case_number):
        """Busca un documento generado basado en el número de caso SII de la referencia."""
        if not referenced_sii_case_number:
            return self.env['account.move']
        
        referenced_dte_case = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
            ('case_number_raw', '=', referenced_sii_case_number),
            ('generated_account_move_id', '!=', False)
        ], limit=1)
        
        return referenced_dte_case.generated_account_move_id

    def _map_dispatch_motive_to_code(self, motive_raw):
        """Mapea el motivo de traslado a código SII."""
        if not motive_raw:
            return False
        
        motive_upper = motive_raw.upper()
        if 'VENTA' in motive_upper:
            return '1'
        if 'COMPRA' in motive_upper:
            return '2'
        if 'CONSIGNACION' in motive_upper and 'A' in motive_upper:
            return '3'
        if 'CONSIGNACION' in motive_upper and 'DE' in motive_upper:
            return '4'
        if 'TRASLADO INTERNO' in motive_upper:
            return '5'
        if 'OTROS TRASLADOS NO VENTA' in motive_upper:
            return '6'
        if 'GUIA DE DEVOLUCION' in motive_upper:
            return '7'
        if 'TRASLADO PARA EXPORTACION' in motive_upper:
            return '8'
        if 'VENTA PARA EXPORTACION' in motive_upper:
            return '9'
        return False

    def _map_dispatch_transport_to_code(self, transport_raw):
        """Mapea el tipo de transporte a código SII."""
        if not transport_raw:
            return False
        
        transport_upper = transport_raw.upper()
        if 'EMISOR' in transport_upper:
            return '1'
        if 'CLIENTE' in transport_upper and 'CUENTA' in transport_upper:
            return '2'
        if 'TERCEROS' in transport_upper:
            return '3'
        return False