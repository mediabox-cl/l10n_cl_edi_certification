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
        """Generate invoice from DTE case using sale.order flow"""
        _logger.info(f"=== INICIANDO GENERACIÓN DE DOCUMENTO PARA CASO {self.dte_case_id.id} ===")
        
        # **NUEVA VERIFICACIÓN: Comprobar si ya existe una factura vinculada**
        if self.dte_case_id.generated_account_move_id:
            _logger.info(f"Caso {self.dte_case_id.id} ya tiene factura vinculada: {self.dte_case_id.generated_account_move_id.name}")
            if self.dte_case_id.generated_account_move_id.state == 'draft':
                _logger.info("La factura existente está en borrador, se puede continuar editando")
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Factura Existente',
                    'res_model': 'account.move',
                    'res_id': self.dte_case_id.generated_account_move_id.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            else:
                _logger.info(f"La factura existente está en estado: {self.dte_case_id.generated_account_move_id.state}")
                raise UserError(f"Este caso DTE ya tiene una factura generada: {self.dte_case_id.generated_account_move_id.name} (Estado: {self.dte_case_id.generated_account_move_id.state})")
        
        # **NUEVA VERIFICACIÓN: Buscar facturas duplicadas por referencia**
        existing_moves = self.env['account.move'].search([
            ('ref', '=', f'Certificación DTE - Caso {self.dte_case_id.id}'),
            ('state', '!=', 'cancel')
        ])
        if existing_moves:
            _logger.warning(f"Encontradas facturas existentes con referencia del caso {self.dte_case_id.id}: {existing_moves.mapped('name')}")
            # Vincular la primera factura encontrada si no hay vinculación
            if not self.dte_case_id.generated_account_move_id and existing_moves:
                self.dte_case_id.generated_account_move_id = existing_moves[0]
                _logger.info(f"Vinculada factura existente {existing_moves[0].name} al caso {self.dte_case_id.id}")
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Factura Recuperada',
                    'res_model': 'account.move',
                    'res_id': existing_moves[0].id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        try:
            # Validar datos requeridos
            self._validate_required_data()
            
            # Crear sale.order
            sale_order = self._create_sale_order()
            _logger.info(f"Sale Order creada: {sale_order.name}")
            
            # Confirmar sale.order
            sale_order.action_confirm()
            _logger.info(f"Sale Order confirmada: {sale_order.name}")
            
            # Crear factura (en borrador)
            invoice = self._create_invoice_from_sale_order(sale_order)
            _logger.info(f"Factura creada en borrador: {invoice.name}")
            
            # Configurar campos específicos de DTE
            self._configure_dte_fields_on_invoice(invoice)
            _logger.info(f"Campos DTE configurados en factura: {invoice.name}")

            # Aplicar descuento global si existe
            if self.dte_case_id.global_discount_percent and self.dte_case_id.global_discount_percent > 0:
                _logger.info(f"Aplicando descuento global: {self.dte_case_id.global_discount_percent}%")
                self._apply_global_discount_to_invoice(invoice, self.dte_case_id.global_discount_percent)
                _logger.info(f"Descuento global aplicado en factura: {invoice.name}")

            # Crear referencias de documentos
            self._create_document_references_on_invoice(invoice)
            _logger.info(f"Referencias de documentos creadas en factura: {invoice.name}")
            
            # **MEJORAR VINCULACIÓN: Guardar relación y agregar logging**
            self.dte_case_id.generated_account_move_id = invoice.id
            self.dte_case_id.generation_status = 'generated'
            _logger.info(f"=== CASO {self.dte_case_id.id} VINCULADO A FACTURA {invoice.name} ===")
            
            # Log de éxito
            _logger.info(f"Factura generada exitosamente: {invoice.name} para caso DTE {self.dte_case_id.id}")
            
            # Verificar después de la configuración
            _logger.info("✓ Factura configurada:")
            _logger.info("  - Diario: %s (ID: %s)", invoice.journal_id.name, invoice.journal_id.id)
            _logger.info("  - Tipo documento: %s (%s)", invoice.l10n_latam_document_type_id.name, invoice.l10n_latam_document_type_id.code)
            _logger.info("  - Fecha: %s", invoice.invoice_date)
            _logger.info("  - Referencia: %s", invoice.ref)
            _logger.info("  - Número documento: %s", invoice.l10n_latam_document_number)

            # APLICAR GIRO ALTERNATIVO SI ES NECESARIO
            self._apply_alternative_giro_if_needed(invoice)
            
            return {
                'type': 'ir.actions.act_window',
                'name': 'Factura Generada',
                'res_model': 'account.move',
                'res_id': invoice.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"Error generando documento para caso {self.dte_case_id.id}: {str(e)}")
            # Actualizar estado de error
            self.dte_case_id.generation_status = 'error'
            self.dte_case_id.error_message = str(e)
            raise UserError(f"Error al generar documento: {str(e)}")

    def _validate_required_data(self):
        """Validate that all required data is present"""
        if not self.dte_case_id:
            raise UserError("No hay caso DTE asociado")
        
        if not self.dte_case_id.partner_id:
            raise UserError("El caso DTE debe tener un partner asociado")
        
        if not self.dte_case_id.document_type_code:
            raise UserError("El caso DTE debe tener un tipo de documento")

    def _create_sale_order(self):
        """Create sale.order from DTE case"""
        partner = self.dte_case_id.partner_id
        
        sale_order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'company_id': self.env.company.id,
            'currency_id': self.env.company.currency_id.id,
            'pricelist_id': partner.property_product_pricelist.id or self.env.company.currency_id.id,
            'l10n_cl_edi_certification_id': self.certification_process_id.id,  # Referencia al proceso de certificación
            'note': f'Orden generada desde caso de certificación DTE {self.dte_case_id.id}',
            # NO crear líneas genéricas aquí - se crearán desde los items del DTE
        }
        
        sale_order = self.env['sale.order'].create(sale_order_vals)
        
        # Crear las líneas reales basadas en los items del DTE
        self._create_sale_order_lines(sale_order)
        
        return sale_order

    def _create_invoice_from_sale_order(self, sale_order):
        """Create invoice from sale.order"""
        invoices = sale_order._create_invoices(final=False)  # Crear en borrador
        if not invoices:
            raise UserError("No se pudo crear la factura desde el pedido de venta")
        
        invoice = invoices[0]
        
        # Agregar referencia al caso DTE
        invoice.ref = f'Certificación DTE - Caso {self.dte_case_id.id}'
        
        # Establecer contexto de certificación para corrección de encoding
        invoice = invoice.with_context(l10n_cl_edi_certification=True)
        
        return invoice

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
        
        # CORREGIR NÚMERO DE DOCUMENTO SI ES NECESARIO
        self._fix_document_number_if_needed(invoice)
        
        # Verificar después de la configuración
        _logger.info("✓ Factura configurada:")
        _logger.info("  - Diario: %s (ID: %s)", invoice.journal_id.name, invoice.journal_id.id)
        _logger.info("  - Tipo documento: %s (%s)", invoice.l10n_latam_document_type_id.name, invoice.l10n_latam_document_type_id.code)
        _logger.info("  - Fecha: %s", invoice.invoice_date)
        _logger.info("  - Referencia: %s", invoice.ref)
        _logger.info("  - Número documento: %s", invoice.l10n_latam_document_number)

        # APLICAR GIRO ALTERNATIVO SI ES NECESARIO
        self._apply_alternative_giro_if_needed(invoice)

    def _fix_document_number_if_needed(self, invoice):
        """
        Corrige el número de documento si tiene formato incorrecto (ej: INV/2025/00001).
        Busca el CAF disponible y asigna el siguiente folio válido.
        """
        self.ensure_one()
        
        current_number = invoice.l10n_latam_document_number
        _logger.info("Verificando número de documento actual: %s", current_number)
        
        # Verificar si el número tiene formato incorrecto (contiene letras o barras)
        if current_number and ('/' in current_number or any(c.isalpha() for c in current_number)):
            _logger.warning("⚠️  Número de documento con formato incorrecto: %s", current_number)
            
            # Buscar el siguiente folio disponible del CAF
            next_folio = self._get_next_available_folio(invoice.l10n_latam_document_type_id)
            
            if next_folio:
                # Asignar el folio correcto
                invoice.write({'l10n_latam_document_number': str(next_folio).zfill(6)})
                _logger.info("✓ Número de documento corregido: %s → %s", current_number, invoice.l10n_latam_document_number)
            else:
                _logger.error("❌ No se pudo obtener un folio válido del CAF")
                raise UserError(_("No se pudo obtener un folio válido del CAF para el tipo de documento %s") % 
                              invoice.l10n_latam_document_type_id.name)
        else:
            _logger.info("✓ Número de documento correcto: %s", current_number)

    def _get_next_available_folio(self, document_type):
        """
        Obtiene el siguiente folio disponible del CAF para el tipo de documento.
        """
        self.ensure_one()
        
        company_id = self.certification_process_id.company_id.id
        
        # Buscar CAF disponible para este tipo de documento
        caf = self.env['l10n_cl.dte.caf'].search([
            ('l10n_latam_document_type_id', '=', document_type.id),
            ('company_id', '=', company_id),
            ('status', '=', 'in_use')
        ], limit=1)
        
        if not caf:
            _logger.error("No se encontró CAF disponible para tipo %s en empresa %s", 
                         document_type.code, company_id)
            return None
        
        _logger.info("CAF encontrado: %s (rango: %s-%s)", caf.filename, caf.start_nb, caf.final_nb)
        
        # Buscar el último folio usado para este tipo de documento
        last_move = self.env['account.move'].search([
            ('l10n_latam_document_type_id', '=', document_type.id),
            ('company_id', '=', company_id),
            ('state', '=', 'posted'),
            ('l10n_latam_document_number', '!=', False)
        ], order='l10n_latam_document_number desc', limit=1)
        
        if last_move and last_move.l10n_latam_document_number.isdigit():
            # Siguiente folio después del último usado
            next_folio = int(last_move.l10n_latam_document_number) + 1
            _logger.info("Último folio usado: %s, siguiente: %s", last_move.l10n_latam_document_number, next_folio)
        else:
            # Primer folio del CAF
            next_folio = caf.start_nb
            _logger.info("No hay folios previos, usando primer folio del CAF: %s", next_folio)
        
        # Verificar que el folio esté dentro del rango del CAF
        if next_folio > caf.final_nb:
            _logger.error("Folio %s excede el rango del CAF (%s-%s)", next_folio, caf.start_nb, caf.final_nb)
            return None
        
        _logger.info("✓ Siguiente folio disponible: %s", next_folio)
        return next_folio

    def _apply_global_discount_to_invoice(self, invoice, discount_percent):
        """
        Aplica un descuento global a la factura usando el producto de descuento.
        
        Por defecto, el descuento se aplica solo a ITEMS AFECTOS (líneas con impuestos),
        que es lo que aparece en los sets de pruebas del SII.
        
        TODO: Agregar campo al modelo para especificar el tipo de descuento si se necesita
        """
        if not discount_percent or discount_percent <= 0:
            return
        
        # Obtener líneas de producto (excluyendo secciones y notas)
        product_lines = invoice.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        
        if not product_lines:
            _logger.warning("No se pudo aplicar descuento global: no hay líneas de producto")
            return
        
        # APLICAR SOLO A ITEMS AFECTOS (líneas con impuestos)
        # Esto coincide con los sets de pruebas del SII que dicen "DESCUENTO GLOBAL ITEMES AFECTOS"
        lines_with_taxes = product_lines.filtered(lambda l: l.tax_ids)
        
        if not lines_with_taxes:
            _logger.warning("No se pudo aplicar descuento global: no hay líneas afectas (con impuestos)")
            return
        
        _logger.info(f"Aplicando descuento global solo a {len(lines_with_taxes)} líneas afectas (de {len(product_lines)} total)")
        
        # Calcular el monto total solo de las líneas afectas
        total_amount = sum(line.price_subtotal for line in lines_with_taxes)
        discount_amount = total_amount * (discount_percent / 100.0)
        
        if discount_amount <= 0:
            _logger.warning(f"Monto de descuento calculado es 0 o negativo: {discount_amount}")
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
        
        # La línea de descuento debe llevar los mismos impuestos que las líneas afectas
        # Usar los impuestos de la primera línea afecta como referencia
        tax_ids = lines_with_taxes[0].tax_ids.ids
        
        # Crear la línea de descuento
        discount_line_vals = {
            'product_id': discount_product.id,
            'name': f'Descuento Global {discount_percent}% - ITEMS AFECTOS',
            'price_unit': -discount_amount,
            'quantity': 1.0,
            'tax_ids': [(6, 0, tax_ids)],
            'move_id': invoice.id,
        }
        
        discount_line = self.env['account.move.line'].create(discount_line_vals)
        
        _logger.info(f"✓ Descuento global aplicado:")
        _logger.info(f"  - Tipo: ITEMS AFECTOS únicamente")
        _logger.info(f"  - Porcentaje: {discount_percent}%")
        _logger.info(f"  - Base (solo afectas): ${total_amount:,.0f}")
        _logger.info(f"  - Descuento: ${discount_amount:,.0f}")
        _logger.info(f"  - Líneas incluidas: {len(lines_with_taxes)} de {len(product_lines)}")
        _logger.info(f"  - Impuestos en descuento: {len(tax_ids)} impuestos")
        _logger.info(f"  - IndExeDR esperado en XML: 2 (descuento sobre items afectos)")

    def _create_document_references_on_invoice(self, invoice):
        """
        Crea las referencias entre documentos en la factura.
        """
        self.ensure_one()
        
        _logger.info(f"=== CREANDO REFERENCIAS PARA FACTURA {invoice.name} ===")
        
        references_to_create = []
        
        # Agregar la referencia obligatoria al SET
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if set_doc_type:
            _logger.info(f"Creando referencia obligatoria al SET: {set_doc_type.name}")
            references_to_create.append({
                'move_id': invoice.id,
                'l10n_cl_reference_doc_type_id': set_doc_type.id,
                'origin_doc_number': self.dte_case_id.case_number_raw,
                'reason': f'CASO {self.dte_case_id.case_number_raw}',
                'date': fields.Date.context_today(self),
            })
        else:
            _logger.warning("No se encontró tipo de documento SET")
        
        # Verificar si hay referencias en el caso DTE
        _logger.info(f"Caso DTE {self.dte_case_id.id} tiene {len(self.dte_case_id.reference_ids)} referencias")
        
        # Agregar las demás referencias del caso DTE
        for ref in self.dte_case_id.reference_ids:
            _logger.info(f"Procesando referencia: {ref.reference_document_text_raw} -> {ref.referenced_sii_case_number}")
            
            # Buscar el documento referenciado si existe
            referenced_move = self._get_referenced_move(ref.referenced_sii_case_number)
            
            if referenced_move:
                _logger.info(f"Documento referenciado encontrado: {referenced_move.name}")
            else:
                _logger.info(f"Documento referenciado NO encontrado para caso: {ref.referenced_sii_case_number}")
            
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
            _logger.info(f"Referencia agregada: {reference_values}")
        
        # Crear todas las referencias
        if references_to_create:
            _logger.info(f"Creando {len(references_to_create)} referencias")
            try:
                created_refs = self.env['l10n_cl.account.invoice.reference'].create(references_to_create)
                _logger.info(f"✓ Referencias creadas exitosamente: {len(created_refs)} registros")
            except Exception as e:
                _logger.error(f"❌ Error creando referencias: {str(e)}")
                raise
        else:
            _logger.warning("No hay referencias para crear")

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

    def _apply_alternative_giro_if_needed(self, invoice):
        """
        Aplica giro alternativo para casos específicos como corrección de giro.
        
        Caso 4267228-5: CORRIGE GIRO DEL RECEPTOR
        """
        self.ensure_one()
        
        case_number = self.dte_case_id.case_number_raw
        
        # Caso especial: Corrección de giro
        if case_number == '4267228-5':
            partner = invoice.partner_id
            original_giro = partner.l10n_cl_activity_description
            alternative_giro = 'Servicios de Consultoría Empresarial'  # 37 chars
            
            # Aplicar giro alternativo temporalmente
            partner.write({'l10n_cl_activity_description': alternative_giro})
            
            _logger.info(f"🔄 Giro alternativo aplicado para caso {case_number}:")
            _logger.info(f"   Original: '{original_giro}'")
            _logger.info(f"   Corregido: '{alternative_giro}'")
            _logger.info(f"   Motivo: CORRIGE GIRO DEL RECEPTOR")
        else:
            _logger.info(f"✓ Giro normal mantenido para caso {case_number}")