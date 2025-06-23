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
        """Generate invoice, credit note or debit note from DTE case"""
        _logger.info(f"=== INICIANDO GENERACIÓN DE DOCUMENTO PARA CASO {self.dte_case_id.id} ===")
        
        # **NUEVA VERIFICACIÓN: Comprobar si ya existe una factura vinculada**
        if self.dte_case_id.generated_account_move_id:
            _logger.info(f"Caso {self.dte_case_id.id} ya tiene documento vinculado: {self.dte_case_id.generated_account_move_id.name}")
            if self.dte_case_id.generated_account_move_id.state == 'draft':
                _logger.info("El documento existente está en borrador, se puede continuar editando")
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Documento Existente',
                    'res_model': 'account.move',
                    'res_id': self.dte_case_id.generated_account_move_id.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            else:
                _logger.info(f"El documento existente está en estado: {self.dte_case_id.generated_account_move_id.state}")
                raise UserError(f"Este caso DTE ya tiene un documento generado: {self.dte_case_id.generated_account_move_id.name} (Estado: {self.dte_case_id.generated_account_move_id.state})")
        
        # **NUEVA VERIFICACIÓN: Buscar documentos duplicados por referencia**
        existing_moves = self.env['account.move'].search([
            ('ref', '=', f'Certificación DTE - Caso {self.dte_case_id.id}'),
            ('state', '!=', 'cancel')
        ])
        if existing_moves:
            _logger.warning(f"Encontrados documentos existentes con referencia del caso {self.dte_case_id.id}: {existing_moves.mapped('name')}")
            # Vincular el primer documento encontrado si no hay vinculación
            if not self.dte_case_id.generated_account_move_id and existing_moves:
                self.dte_case_id.generated_account_move_id = existing_moves[0]
                _logger.info(f"Vinculado documento existente {existing_moves[0].name} al caso {self.dte_case_id.id}")
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Documento Recuperado',
                    'res_model': 'account.move',
                    'res_id': existing_moves[0].id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        try:
            # Validar datos requeridos
            self._validate_required_data()
            
            # **NUEVO: Detectar tipo de documento y usar flujo correspondiente**
            document_type = self.dte_case_id.document_type_code
            
            _logger.info(f"🔍 DETECCIÓN DE FLUJO:")
            _logger.info(f"   - Caso: {self.dte_case_id.case_number_raw}")
            _logger.info(f"   - Tipo documento: '{document_type}' (tipo: {type(document_type)})")
            _logger.info(f"   - Referencias: {len(self.dte_case_id.reference_ids)}")
            
            if document_type == '52':  # Guía de Despacho
                _logger.info(f"✅ ENTRANDO A FLUJO DE GUÍAS DE DESPACHO")
                return self._generate_delivery_guide()
            elif document_type in ['61', '56']:  # Nota de crédito o débito
                _logger.info(f"✅ ENTRANDO A FLUJO DE NOTAS DE CRÉDITO/DÉBITO")
                return self._generate_credit_or_debit_note()
            elif document_type in ['110', '111', '112']:  # Documentos de Exportación
                _logger.info(f"✅ ENTRANDO A FLUJO DE DOCUMENTOS DE EXPORTACIÓN")
                return self._generate_export_document()
            else:  # Factura u otro documento original
                _logger.info(f"✅ ENTRANDO A FLUJO DE DOCUMENTOS ORIGINALES")
                return self._generate_original_document()
                
        except Exception as e:
            _logger.error(f"Error generando documento para caso {self.dte_case_id.id}: {str(e)}")
            # Actualizar estado de error
            self.dte_case_id.generation_status = 'error'
            self.dte_case_id.error_message = str(e)
            raise UserError(f"Error al generar documento: {str(e)}")

    def _generate_original_document(self):
        """Genera facturas u otros documentos originales usando el flujo sale.order"""
        _logger.info(f"Generando documento original (tipo {self.dte_case_id.document_type_code})")
        
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

    def _generate_export_document(self):
        """Genera documentos de exportación (110, 111, 112) con campos específicos"""
        _logger.info(f"Generando documento de exportación (tipo {self.dte_case_id.document_type_code})")
        
        # Crear sale.order
        sale_order = self._create_sale_order()
        _logger.info(f"Sale Order creada: {sale_order.name}")
        
        # Confirmar sale.order
        sale_order.action_confirm()
        _logger.info(f"Sale Order confirmada: {sale_order.name}")
        
        # Crear factura (en borrador)
        invoice = self._create_invoice_from_sale_order(sale_order)
        _logger.info(f"Factura de exportación creada en borrador: {invoice.name}")
        
        # Configurar campos específicos de DTE y exportación
        self._configure_dte_fields_on_invoice(invoice)
        _logger.info(f"Campos DTE configurados en factura: {invoice.name}")
        
        # NUEVO: Configurar campos específicos de exportación
        self._configure_export_fields_on_invoice(invoice)
        _logger.info(f"Campos de exportación configurados en factura: {invoice.name}")
        
        # NUEVO: Configurar moneda de exportación
        self._configure_export_currency_on_invoice(invoice)
        _logger.info(f"Moneda de exportación configurada en factura: {invoice.name}")

        # Aplicar descuento global si existe
        if self.dte_case_id.global_discount_percent and self.dte_case_id.global_discount_percent > 0:
            _logger.info(f"Aplicando descuento global: {self.dte_case_id.global_discount_percent}%")
            self._apply_global_discount_to_invoice(invoice, self.dte_case_id.global_discount_percent)
            _logger.info(f"Descuento global aplicado en factura: {invoice.name}")

        # Crear referencias de documentos
        self._create_document_references_on_invoice(invoice)
        _logger.info(f"Referencias de documentos creadas en factura: {invoice.name}")
        
        # Vincular caso con factura generada
        self.dte_case_id.generated_account_move_id = invoice.id
        self.dte_case_id.generation_status = 'generated'
        _logger.info(f"=== CASO {self.dte_case_id.id} VINCULADO A FACTURA DE EXPORTACIÓN {invoice.name} ===")
        
        # Log de éxito
        _logger.info(f"Factura de exportación generada exitosamente: {invoice.name} para caso DTE {self.dte_case_id.id}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Factura de Exportación Generada',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _generate_credit_or_debit_note(self):
        """Genera nota de crédito o débito desde documento referenciado"""
        _logger.info(f"=== ENTRANDO A _generate_credit_or_debit_note() ===")
        _logger.info(f"Generando nota de crédito/débito (tipo {self.dte_case_id.document_type_code})")
        _logger.info(f"Caso: {self.dte_case_id.case_number_raw}")
        _logger.info(f"Referencias disponibles: {len(self.dte_case_id.reference_ids)}")
        
        # Buscar el documento original referenciado
        if not self.dte_case_id.reference_ids:
            _logger.error(f"❌ El caso {self.dte_case_id.case_number_raw} no tiene referencias")
            raise UserError(f"La nota de crédito/débito {self.dte_case_id.case_number_raw} debe tener referencias al documento original")
        
        # Obtener la primera referencia (documento original)
        ref = self.dte_case_id.reference_ids[0]
        _logger.info(f"✓ Primera referencia: '{ref.reference_document_text_raw}' -> caso {ref.referenced_sii_case_number}")
        
        # **NUEVA LÓGICA: Detectar si es ND que anula NC**
        _logger.info(f"🔍 VERIFICANDO SI ES ND QUE ANULA NC:")
        _logger.info(f"   - Tipo caso actual: '{self.dte_case_id.document_type_code}'")
        _logger.info(f"   - Código referencia: '{ref.reference_code}'")
        _logger.info(f"   - Caso referenciado existe: {bool(ref.referenced_case_dte_id)}")
        if ref.referenced_case_dte_id:
            _logger.info(f"   - Tipo caso referenciado: '{ref.referenced_case_dte_id.document_type_code}'")
        
        if (self.dte_case_id.document_type_code == '56' and  # Es nota de débito
            ref.reference_code == '1' and  # Código anulación
            ref.referenced_case_dte_id and 
            ref.referenced_case_dte_id.document_type_code == '61'):  # Referencia a NC
            
            _logger.info(f"🎯 DETECTADO: ND que anula NC (caso {self.dte_case_id.case_number_raw})")
            return self._generate_debit_note_from_credit_note()
        else:
            _logger.info(f"📌 NO ES ND QUE ANULA NC - usando flujo estándar de NC/ND")
        
        # Buscar el documento original generado
        _logger.info(f"🔍 Buscando documento original con caso: {ref.referenced_sii_case_number}")
        original_invoice = self._get_referenced_move(ref.referenced_sii_case_number)
        _logger.info(f"Documento original encontrado: {bool(original_invoice)}")
        
        if not original_invoice:
            # Si no existe, sugerir generarlo primero
            referenced_case = self.env['l10n_cl_edi.certification.case.dte'].search([
                ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
                ('case_number_raw', '=', ref.referenced_sii_case_number)
            ], limit=1)
            
            if referenced_case:
                error_msg = f"El documento original (caso {ref.referenced_sii_case_number}) aún no ha sido generado. "
                error_msg += f"Debe generar primero el caso '{referenced_case.case_number_raw} - {referenced_case.document_type_raw}' "
                error_msg += f"antes de crear esta nota de crédito/débito."
                raise UserError(error_msg)
            else:
                raise UserError(f"No se encontró el caso DTE referenciado: {ref.referenced_sii_case_number}")
        
        # Validar que el documento original esté confirmado
        if original_invoice.state not in ['posted']:
            raise UserError(f"El documento original {original_invoice.name} debe estar confirmado antes de crear la nota de crédito/débito (estado actual: {original_invoice.state})")
        
        _logger.info(f"Documento original encontrado: {original_invoice.name} (estado: {original_invoice.state})")
        
        # Generar la nota de crédito/débito
        _logger.info(f"🚀 Generando NC/ND usando flujo estándar")
        credit_note = self._generate_credit_note_from_case(original_invoice, self.dte_case_id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Nota de {"Crédito" if self.dte_case_id.document_type_code == "61" else "Débito"} Generada',
            'res_model': 'account.move',
            'res_id': credit_note.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _validate_required_data(self):
        """Validate that all required data is present"""
        if not self.dte_case_id:
            raise UserError("No hay caso DTE asociado")
        
        if not self.dte_case_id.document_type_code:
            raise UserError("El caso DTE debe tener un tipo de documento")
        
        # Validaciones específicas por tipo de documento
        if self.dte_case_id.document_type_code in ['61', '56']:  # NC/ND
            self._validate_credit_debit_note_requirements()
        else:  # Documentos originales
            # Asignar automáticamente un partner si no lo tiene
            if not self.dte_case_id.partner_id:
                # Para documentos de exportación, usar partners extranjeros específicos
                if self.dte_case_id.document_type_code in ['110', '111', '112']:
                    partner = self._get_export_partner_for_case()
                else:
                    partner = self._get_available_certification_partner()
                self.dte_case_id.partner_id = partner
                _logger.info(f"Partner asignado automáticamente al caso {self.dte_case_id.case_number_raw}: {partner.name}")
    
    def _validate_credit_debit_note_requirements(self):
        """Valida requisitos específicos para notas de crédito/débito"""
        # Verificar que tenga referencias
        if not self.dte_case_id.reference_ids:
            raise UserError(f"La nota de crédito/débito {self.dte_case_id.case_number_raw} debe tener referencias al documento original")
        
        # Obtener la primera referencia (documento original)
        ref = self.dte_case_id.reference_ids[0]
        
        # Validar que el caso referenciado exista
        if not ref.referenced_case_dte_id:
            raise UserError(f"No se encontró el caso DTE original referenciado: {ref.referenced_sii_case_number}")
        
        # Validar que el caso referenciado tenga factura generada
        original_case = ref.referenced_case_dte_id
        if not original_case.generated_account_move_id:
            raise UserError(f"El caso original {original_case.case_number_raw} debe tener un documento generado antes de crear la nota de crédito/débito")
        
        # Validar que la factura original esté confirmada
        if original_case.generated_account_move_id.state == 'draft':
            raise UserError(f"El documento original {original_case.generated_account_move_id.name} debe estar confirmado antes de crear la nota de crédito/débito")

    def _create_sale_order(self):
        """Create sale.order from DTE case"""
        # El partner ya debe estar asignado por la validación
        partner = self.dte_case_id.partner_id
        _logger.info(f"Usando partner del caso: {partner.name}")
        
        # Determinar moneda para documentos de exportación
        currency_id = self._get_export_currency_id() or self.env.company.currency_id.id
        
        sale_order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'company_id': self.env.company.id,
            'currency_id': currency_id,
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
            
            # Usar valores directos - los datos del SII ya están correctos
            quantity = item.quantity or 1.0
            price_unit = item.price_unit
            discount = item.discount_percent or 0.0
            
            # Preparar valores de la línea
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.id,
                'name': item.name,
                'product_uom_qty': quantity,
                'price_unit': price_unit,
                'discount': discount,
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
        Para documentos de exportación, usa productos específicos SIN IVA.
        """
        # PARA DOCUMENTOS DE EXPORTACIÓN: usar productos específicos sin IVA
        if self.dte_case_id.document_type_code in ['110', '111', '112']:
            return self._get_export_product_for_item(item_name)
        
        # Para documentos normales, usar la lógica existente
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
    
    def _get_export_product_for_item(self, item_name):
        """
        Obtiene producto específico de exportación SIN IVA según el nombre del item.
        """
        item_upper = item_name.upper()
        
        # Mapear según el tipo de producto/servicio
        if 'CHATARRA' in item_upper or 'ALUMINIO' in item_upper:
            product = self.env.ref('l10n_cl_edi_certification.export_product_aluminum_scrap', False)
        elif 'SERVICIO' in item_upper and ('PROFESIONAL' in item_upper or 'CONSULTOR' in item_upper):
            product = self.env.ref('l10n_cl_edi_certification.export_product_professional_services', False)
        elif 'SERVICIO' in item_upper and ('HOTEL' in item_upper or 'TURISM' in item_upper):
            product = self.env.ref('l10n_cl_edi_certification.export_product_hotel_services', False)
        elif 'AGRICOLA' in item_upper or 'FRUTA' in item_upper or 'VERDURA' in item_upper:
            product = self.env.ref('l10n_cl_edi_certification.export_product_agricultural', False)
        else:
            # Producto genérico para otros casos
            product = self.env.ref('l10n_cl_edi_certification.export_product_generic', False)
        
        if not product:
            # Fallback al producto genérico
            product = self.env.ref('l10n_cl_edi_certification.export_product_generic')
        
        _logger.info(f"✓ Producto de exportación seleccionado: '{item_name}' → {product.name} (SIN IVA)")
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
        """
        Mapea el tipo de transporte a código SII TipoDespacho según especificación:
        1 = Despacho por Cuenta del Comprador
        2 = Despacho por Cuenta del Emisor a Instalaciones del Comprador
        3 = Despacho por Cuenta del Emisor a Otras Instalaciones
        """
        if not transport_raw:
            # Para traslados internos sin especificar transporte, usar "emisor a otras instalaciones"
            return '3'
        
        transport_upper = transport_raw.upper()
        
        # Cliente maneja el transporte (caso: "CLIENTE")
        if 'CLIENTE' in transport_upper:
            return '1'  # Despacho por Cuenta del Comprador
        
        # Emisor del documento al cliente (caso: "EMISOR DEL DOCUMENTO AL LOCAL DEL CLIENTE")
        if 'EMISOR' in transport_upper and 'CLIENTE' in transport_upper:
            return '2'  # Despacho por Cuenta del Emisor a Instalaciones del Comprador
        
        # Emisor a otras ubicaciones o terceros
        if 'EMISOR' in transport_upper or 'TERCEROS' in transport_upper:
            return '3'  # Despacho por Cuenta del Emisor a Otras Instalaciones
            
        # Default para casos no reconocidos - emisor a otras instalaciones
        return '3'

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

    def _configure_export_fields_on_invoice(self, invoice):
        """
        Configura campos específicos de exportación en la factura usando campos de l10n_cl_edi_exports.
        Mapea los campos export_*_raw del caso DTE a los campos estándar de Odoo para exportación.
        """
        self.ensure_one()
        
        _logger.info(f"Configurando campos de exportación para caso {self.dte_case_id.case_number_raw}")
        
        export_values = {}
        
        # 1. Puertos de embarque y desembarque
        if self.dte_case_id.export_loading_port_raw:
            loading_port = self._map_port_name_to_record(self.dte_case_id.export_loading_port_raw)
            if loading_port:
                export_values['l10n_cl_port_origin_id'] = loading_port.id
                _logger.info(f"Puerto embarque mapeado: {self.dte_case_id.export_loading_port_raw} → {loading_port.name}")
        
        if self.dte_case_id.export_unloading_port_raw:
            unloading_port = self._map_port_name_to_record(self.dte_case_id.export_unloading_port_raw)
            if unloading_port:
                export_values['l10n_cl_port_destination_id'] = unloading_port.id
                _logger.info(f"Puerto desembarque mapeado: {self.dte_case_id.export_unloading_port_raw} → {unloading_port.name}")
        
        # 2. País de destino (si es diferente al del partner)
        if self.dte_case_id.export_destination_country_raw:
            destination_country = self._map_country_name_to_record(self.dte_case_id.export_destination_country_raw)
            if destination_country:
                export_values['l10n_cl_destination_country_id'] = destination_country.id
                _logger.info(f"País destino mapeado: {self.dte_case_id.export_destination_country_raw} → {destination_country.name}")
        
        # 3. Cantidad de bultos
        if self.dte_case_id.export_total_packages:
            export_values['l10n_cl_customs_quantity_of_packages'] = self.dte_case_id.export_total_packages
            _logger.info(f"Total bultos: {self.dte_case_id.export_total_packages}")
        
        # 4. Vía de transporte
        if self.dte_case_id.export_transport_way_raw:
            transport_code = self._map_transport_way_to_code(self.dte_case_id.export_transport_way_raw)
            if transport_code:
                export_values['l10n_cl_customs_transport_type'] = transport_code
                _logger.info(f"Vía transporte mapeada: {self.dte_case_id.export_transport_way_raw} → {transport_code}")
        
        # 5. Modalidad de venta
        if self.dte_case_id.export_sale_modality_raw:
            sale_mode_code = self._map_sale_modality_to_code(self.dte_case_id.export_sale_modality_raw)
            if sale_mode_code:
                export_values['l10n_cl_customs_sale_mode'] = sale_mode_code
                _logger.info(f"Modalidad venta mapeada: {self.dte_case_id.export_sale_modality_raw} → {sale_mode_code}")
        
        # 6. Incoterm (cláusula de venta)
        if self.dte_case_id.export_sale_clause_raw:
            incoterm = self._map_incoterm_to_record(self.dte_case_id.export_sale_clause_raw)
            if incoterm:
                export_values['invoice_incoterm_id'] = incoterm.id
                _logger.info(f"Incoterm mapeado: {self.dte_case_id.export_sale_clause_raw} → {incoterm.code}")
        
        # 7. Configurar partner como extranjero si es necesario
        if self.dte_case_id.export_client_nationality_raw:
            self._configure_partner_as_foreign(invoice.partner_id)
        
        # 8. Campos específicos adicionales (nuevos en account.move)
        if self.dte_case_id.export_payment_terms_raw:
            payment_code = self._map_payment_terms_to_code(self.dte_case_id.export_payment_terms_raw)
            if payment_code:
                export_values['l10n_cl_export_payment_terms'] = payment_code
                _logger.info(f"Forma pago exportación: {self.dte_case_id.export_payment_terms_raw} → {payment_code}")
        
        if self.dte_case_id.export_reference_text:
            export_values['l10n_cl_export_reference_text'] = self.dte_case_id.export_reference_text
            _logger.info(f"Referencia documental: {self.dte_case_id.export_reference_text[:50]}...")
        
        if self.dte_case_id.export_package_type_raw:
            export_values['l10n_cl_export_package_type'] = self.dte_case_id.export_package_type_raw
            _logger.info(f"Tipo bulto: {self.dte_case_id.export_package_type_raw}")
        
        if self.dte_case_id.export_freight_amount:
            export_values['l10n_cl_export_freight_amount'] = self.dte_case_id.export_freight_amount
            _logger.info(f"Monto flete: {self.dte_case_id.export_freight_amount}")
        
        if self.dte_case_id.export_insurance_amount:
            export_values['l10n_cl_export_insurance_amount'] = self.dte_case_id.export_insurance_amount
            _logger.info(f"Monto seguro: {self.dte_case_id.export_insurance_amount}")
        
        if self.dte_case_id.export_foreign_commission_percent:
            export_values['l10n_cl_export_foreign_commission_percent'] = self.dte_case_id.export_foreign_commission_percent
            _logger.info(f"% Comisiones extranjero: {self.dte_case_id.export_foreign_commission_percent}")
        
        # Aplicar todos los valores
        if export_values:
            invoice.write(export_values)
            _logger.info(f"✓ Campos de exportación configurados: {list(export_values.keys())}")
        else:
            _logger.warning("No se configuraron campos de exportación")
        
        # Log resumen de configuración
        _logger.info("=== RESUMEN CONFIGURACIÓN EXPORTACIÓN ===")
        _logger.info(f"Puerto origen: {invoice.l10n_cl_port_origin_id.name if invoice.l10n_cl_port_origin_id else 'No configurado'}")
        _logger.info(f"Puerto destino: {invoice.l10n_cl_port_destination_id.name if invoice.l10n_cl_port_destination_id else 'No configurado'}")
        _logger.info(f"País destino: {invoice.l10n_cl_destination_country_id.name if invoice.l10n_cl_destination_country_id else 'No configurado'}")
        _logger.info(f"Total bultos: {invoice.l10n_cl_customs_quantity_of_packages}")
        _logger.info(f"Vía transporte: {invoice.l10n_cl_customs_transport_type}")
        _logger.info(f"Modalidad venta: {invoice.l10n_cl_customs_sale_mode}")
        _logger.info(f"Incoterm: {invoice.invoice_incoterm_id.code if invoice.invoice_incoterm_id else 'No configurado'}")

    def _generate_credit_note_from_case(self, invoice, case_dte):
        """
        Genera nota de crédito desde caso de certificación siguiendo procesos nativos de Odoo.
        CORREGIDO: Configura correctamente el tipo de documento y contexto antes de crear la NC.
        
        Args:
            invoice (account.move): Factura original desde la cual crear la NC
            case_dte (l10n_cl_edi.certification.case.dte): Caso DTE de la nota de crédito
            
        Returns:
            account.move: Nota de crédito generada
        """
        self.ensure_one()
        
        _logger.info(f"=== GENERANDO NOTA DE CRÉDITO ===")
        _logger.info(f"Factura original: {invoice.name} (ID: {invoice.id})")
        _logger.info(f"Caso DTE: {case_dte.case_number_raw} - {case_dte.document_type_raw}")
        
        # Validar que es una nota de crédito o débito
        if case_dte.document_type_code not in ['61', '56']:
            raise UserError(f"El caso {case_dte.case_number_raw} no es una nota de crédito/débito (tipo: {case_dte.document_type_code})")
        
        # **CLAVE 1: Obtener el tipo correcto de documento según el partner**
        # Esto usa la lógica nativa del módulo chileno
        reverse_doc_type = invoice._l10n_cl_get_reverse_doc_type()
        _logger.info(f"Tipo de documento NC determinado: {reverse_doc_type.name} (código: {reverse_doc_type.code})")
        
        # **CLAVE 2: Determinar el código de referencia según el caso**
        reference_code = '3'  # Por defecto: corrección de monto
        if case_dte.reference_ids:
            reference_code = case_dte.reference_ids[0].reference_code
            _logger.info(f"Código de referencia del caso: {reference_code}")
        
        # **CLAVE 3: Configurar el contexto como lo hace el wizard nativo**
        reference_reason = case_dte.reference_ids[0].reason_raw if case_dte.reference_ids else 'Nota de crédito'
        
        reversal_context = {
            'default_l10n_cl_edi_reference_doc_code': reference_code,
        }
        
        # Para correcciones de texto (código 2), configurar textos
        if reference_code == '2':
            reversal_context.update({
                'default_l10n_cl_original_text': 'Texto original a corregir',
                'default_l10n_cl_corrected_text': reference_reason,
            })
            _logger.info("Configurando corrección de texto")
        
        _logger.info(f"Contexto de reversión: {reversal_context}")
        
        # **CLAVE 4: Preparar los valores por defecto usando el método nativo**
        # Esto simula lo que hace el wizard de reversión chileno
        # IMPORTANTE: Crear las referencias en el ORDEN CORRECTO para el XML (SET primero)
        
        # Buscar tipo de documento SET para la primera referencia
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        # Crear referencias en orden correcto: SET primero, luego documento original
        reference_lines = []
        
        # PRIMERA REFERENCIA: SET (obligatoria para certificación SII)
        if set_doc_type:
            reference_lines.append([0, 0, {
                'l10n_cl_reference_doc_type_id': set_doc_type.id,
                'origin_doc_number': case_dte.case_number_raw,
                'reason': f'CASO {case_dte.case_number_raw}',
                'date': fields.Date.context_today(self),
                # NO incluir reference_doc_code para referencia SET
            }])
            _logger.info(f"✓ Referencia SET preparada (primera): {case_dte.case_number_raw}")
        else:
            _logger.error("❌ No se encontró tipo de documento SET")
            raise UserError("No se encontró tipo de documento SET para referencias")
        
        # SEGUNDA REFERENCIA: Documento original 
        reference_lines.append([0, 0, {
            'origin_doc_number': invoice.l10n_latam_document_number,
            'l10n_cl_reference_doc_type_id': invoice.l10n_latam_document_type_id.id,
            'reference_doc_code': reference_code,
            'reason': reference_reason,
            'date': invoice.invoice_date,
        }])
        _logger.info(f"✓ Referencia documento original preparada (segunda): {invoice.l10n_latam_document_number}")
        
        default_values = [{
            'move_type': 'out_refund' if invoice.move_type == 'out_invoice' else 'in_refund',
            'invoice_origin': f'{invoice.l10n_latam_document_type_id.doc_code_prefix} {invoice.l10n_latam_document_number}',
            'l10n_latam_document_type_id': reverse_doc_type.id,  # ← ESTO ERA LO QUE FALTABA
            'l10n_cl_reference_ids': reference_lines  # Referencias en orden correcto
        }]
        
        _logger.info("Valores por defecto configurados para NC")
        
        # **PASO 5: Crear la NC usando el método nativo con contexto correcto**
        try:
            _logger.info("Llamando a _reverse_moves() con configuración correcta")
            
            # Usar el contexto correcto y los valores por defecto
            reversed_moves = invoice.with_context(**reversal_context)._reverse_moves(
                default_values_list=default_values,
                cancel=False
            )
            
            if not reversed_moves:
                raise UserError("No se pudo crear la nota de crédito/débito")
            
            credit_note = reversed_moves[0]
            _logger.info(f"✓ NC/ND creada: {credit_note.name} (ID: {credit_note.id})")
            _logger.info(f"  - Tipo documento: {credit_note.l10n_latam_document_type_id.name}")
            _logger.info(f"  - Código: {credit_note.l10n_latam_document_type_id.code}")
            
        except Exception as e:
            _logger.error(f"❌ Error creando NC/ND: {str(e)}")
            raise UserError(f"Error al crear nota de crédito/débito: {str(e)}")
        
        # **PASO 6: Verificar que las referencias se crearon correctamente**
        _logger.info("Verificando referencias creadas en la NC")
        
        # Las referencias ya fueron configuradas en default_values en el orden correcto:
        # 1. SET (primera - aparece primera en XML)
        # 2. Documento original (segunda - aparece segunda en XML)
        
        created_references = credit_note.l10n_cl_reference_ids
        _logger.info(f"✓ Total referencias creadas: {len(created_references)}")
        
        for i, ref in enumerate(created_references.sorted('id'), 1):
            _logger.info(f"  Ref {i}: {ref.l10n_cl_reference_doc_type_id.code} - {ref.origin_doc_number} - {ref.reason}")
        
        # Verificar que SET es la primera referencia
        if created_references:
            first_ref = created_references.sorted('id')[0]
            if first_ref.l10n_cl_reference_doc_type_id.code == 'SET':
                _logger.info("✓ Orden de referencias correcto: SET aparece primera")
            else:
                _logger.warning(f"⚠️  Orden de referencias incorrecto: {first_ref.l10n_cl_reference_doc_type_id.code} aparece primera en lugar de SET")
        else:
            _logger.error("❌ No se crearon referencias")
        
        # **PASO 7: Ajustar líneas según el tipo de nota de crédito**
        _logger.info("Ajustando líneas del documento según tipo de NC")
        self._adjust_credit_note_lines(credit_note, case_dte)
        
        # **PASO 8: Marcar el caso como generado**
        case_dte.write({
            'generation_status': 'generated',
            'generated_account_move_id': credit_note.id,
        })
        
        _logger.info(f"✅ NOTA DE CRÉDITO GENERADA EXITOSAMENTE")
        _logger.info(f"   Documento: {credit_note.name}")
        _logger.info(f"   Tipo: {credit_note.l10n_latam_document_type_id.name} ({credit_note.l10n_latam_document_type_id.code})")
        _logger.info(f"   Referencias: {len(credit_note.l10n_cl_reference_ids)}")
        _logger.info(f"   Caso marcado como generado")
        
        return credit_note
    
    def _adjust_credit_note_lines(self, credit_note, case_dte):
        """
        Ajusta las líneas de la nota de crédito según el tipo de operación.
        Delega a métodos específicos para cada tipo de corrección.
        """
        self.ensure_one()
        
        if not case_dte.reference_ids:
            _logger.info("No hay referencias en el caso, manteniendo líneas originales")
            return
        
        ref_code = case_dte.reference_ids[0].reference_code
        _logger.info(f"Procesando nota de crédito con código de referencia: {ref_code}")
        
        if ref_code == '2':  # Corrección de texto/giro
            self._apply_text_correction_nc(credit_note, case_dte)
        elif ref_code == '3':  # Devolución de mercaderías
            self._apply_partial_return_nc(credit_note, case_dte)
        elif ref_code == '1':  # Anulación completa
            self._apply_full_cancellation_nc(credit_note, case_dte)
        else:
            _logger.warning(f"Código de referencia no reconocido: {ref_code}. Manteniendo líneas originales.")

    def _apply_text_correction_nc(self, credit_note, case_dte):
        """
        Aplica corrección de texto/giro (código 2).
        Crea una línea con monto $0 para informar la corrección.
        """
        _logger.info("=== APLICANDO CORRECCIÓN DE TEXTO/GIRO (Código 2) ===")
        
        # Eliminar líneas existentes (excepto líneas de impuestos)
        product_lines = credit_note.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note') and not l.tax_line_id
        )
        
        if product_lines:
            _logger.info(f"Eliminando {len(product_lines)} líneas originales")
            product_lines.unlink()
        
        # Crear línea de corrección con monto 0
        correction_text = case_dte.reference_ids[0].reason_raw or "Corrección de texto"
        
        correction_line_vals = {
            'move_id': credit_note.id,
            'name': f'CORRECCIÓN: {correction_text}',
            'quantity': 1.0,
            'price_unit': 0.0,  # ← MONTO CERO según regulación SII
            'account_id': credit_note.journal_id.default_account_id.id,
        }
        
        correction_line = self.env['account.move.line'].create(correction_line_vals)
        _logger.info("✓ Línea de corrección creada con monto $0")
        _logger.info(f"  Descripción: {correction_line.name}")
        _logger.info("  → Esta NC solo informa la corrección, no afecta montos")

    def _apply_partial_return_nc(self, credit_note, case_dte):
        """
        Aplica devolución parcial de mercaderías (código 3).
        Ajusta cantidades según los ítems específicos del caso DTE.
        """
        _logger.info("=== APLICANDO DEVOLUCIÓN PARCIAL (Código 3) ===")
        
        if not case_dte.item_ids:
            _logger.warning("No hay ítems específicos en el caso DTE. Manteniendo líneas originales.")
            return
        
        _logger.info(f"Ajustando cantidades según {len(case_dte.item_ids)} ítems del caso")
        
        # Mapear ítems del caso por nombre para facilitar búsqueda
        case_items_by_name = {item.name: item for item in case_dte.item_ids}
        
        # Obtener líneas de productos (sin líneas de impuestos ni descriptivas)
        product_lines = credit_note.invoice_line_ids.filtered(
            lambda l: l.product_id and l.display_type not in ('line_section', 'line_note') and not l.tax_line_id
        )
        
        lines_matched = 0
        lines_to_remove = []
        
        for line in product_lines:
            # Buscar ítem correspondiente en el caso por nombre
            matching_item = None
            for item_name, item in case_items_by_name.items():
                # Búsqueda flexible: comparar nombres normalizados
                if (item_name.upper().strip() in line.name.upper().strip() or 
                    line.name.upper().strip() in item_name.upper().strip()):
                    matching_item = item
                    break
            
            if matching_item:
                # Actualizar cantidad según el caso DTE (mantener precio unitario original)
                old_qty = line.quantity
                line.write({
                    'quantity': matching_item.quantity,
                    # Mantener price_unit original para consistencia
                })
                _logger.info(f"✓ Línea actualizada: '{line.name}'")
                _logger.info(f"  Cantidad: {old_qty} → {matching_item.quantity}")
                _logger.info(f"  Precio unitario: ${line.price_unit:,.0f} (mantenido)")
                lines_matched += 1
            else:
                # Si no hay ítem correspondiente, marcar para eliminar
                # (solo devolver productos específicamente mencionados en el caso)
                lines_to_remove.append(line)
                _logger.info(f"⚠️  Línea sin ítem correspondiente (se eliminará): '{line.name}'")
        
        # Eliminar líneas que no tienen ítems correspondientes en la devolución
        if lines_to_remove:
            lines_to_remove_names = [l.name for l in lines_to_remove]
            for line in lines_to_remove:
                line.unlink()
            _logger.info(f"✓ Eliminadas {len(lines_to_remove)} líneas no incluidas en devolución")
            for name in lines_to_remove_names:
                _logger.info(f"  - {name}")
        
        _logger.info(f"✅ DEVOLUCIÓN PARCIAL COMPLETADA:")
        _logger.info(f"  - Líneas ajustadas: {lines_matched}")
        _logger.info(f"  - Líneas eliminadas: {len(lines_to_remove)}")
        _logger.info("  → Solo se reversan los productos específicamente devueltos")

    def _apply_full_cancellation_nc(self, credit_note, case_dte):
        """
        Aplica anulación completa (código 1).
        Mantiene las líneas originales con montos completos para anular toda la factura.
        """
        _logger.info("=== APLICANDO ANULACIÓN COMPLETA (Código 1) ===")
        
        # Para anulación completa, las líneas ya están correctas (montos completos negativos)
        # Solo verificar que tenemos las líneas correctas
        
        product_lines = credit_note.invoice_line_ids.filtered(
            lambda l: l.product_id and l.display_type not in ('line_section', 'line_note') and not l.tax_line_id
        )
        
        if case_dte.item_ids:
            # Si el caso tiene ítems específicos, verificar que coincidan
            _logger.info(f"Verificando {len(product_lines)} líneas contra {len(case_dte.item_ids)} ítems del caso")
            
            # Mapear ítems del caso por nombre
            case_items_by_name = {item.name: item for item in case_dte.item_ids}
            
            for line in product_lines:
                # Buscar ítem correspondiente
                matching_item = None
                for item_name, item in case_items_by_name.items():
                    if (item_name.upper().strip() in line.name.upper().strip() or 
                        line.name.upper().strip() in item_name.upper().strip()):
                        matching_item = item
                        break
                
                if matching_item:
                    # Para anulación, verificar que las cantidades sean correctas
                    # (deberían ser las mismas que la factura original)
                    if line.quantity != matching_item.quantity:
                        _logger.info(f"Ajustando cantidad para anulación completa: '{line.name}'")
                        _logger.info(f"  Cantidad: {line.quantity} → {matching_item.quantity}")
                        line.write({'quantity': matching_item.quantity})
                    
                    _logger.info(f"✓ Línea verificada: '{line.name}' - Cant: {line.quantity}")
                else:
                    _logger.warning(f"⚠️  Línea sin ítem correspondiente: '{line.name}'")
        
        total_lines = len(product_lines)
        total_amount = sum(line.price_subtotal for line in product_lines)
        
        _logger.info(f"✅ ANULACIÓN COMPLETA CONFIGURADA:")
        _logger.info(f"  - Total líneas: {total_lines}")
        _logger.info(f"  - Monto total NC: ${total_amount:,.0f}")
        _logger.info("  → Esta NC anula completamente la factura original")

    def _generate_debit_note_from_credit_note(self):
        """
        Genera nota de débito que anula una nota de crédito usando el wizard nativo.
        Simplificado para sets de pruebas específicos del SII.
        """
        _logger.info(f"=== GENERANDO ND QUE ANULA NC (CASO {self.dte_case_id.case_number_raw}) ===")
        
        # Obtener referencia a la nota de crédito
        ref = self.dte_case_id.reference_ids[0]
        credit_note_case = ref.referenced_case_dte_id
        
        if not credit_note_case or not credit_note_case.generated_account_move_id:
            raise UserError(
                f"La nota de crédito referenciada (caso {ref.referenced_sii_case_number}) "
                f"debe ser generada antes de crear la nota de débito."
            )
        
        credit_note = credit_note_case.generated_account_move_id
        
        # Validar que la NC esté confirmada
        if credit_note.state != 'posted':
            raise UserError(
                f"La nota de crédito {credit_note.name} debe estar confirmada "
                f"antes de crear la nota de débito (estado actual: {credit_note.state})"
            )
        
        _logger.info(f"✓ NC a anular: {credit_note.name} (ID: {credit_note.id})")
        
        # Preparar contexto para el wizard nativo
        wizard_context = {
            'active_model': 'account.move',
            'active_ids': [credit_note.id],
            'default_l10n_cl_edi_reference_doc_code': '1',  # Anulación
        }
        
        # Crear wizard nativo de nota de débito
        try:
            wizard = self.env['account.debit.note'].with_context(**wizard_context).create({
                'move_ids': [(6, 0, [credit_note.id])],
                'l10n_cl_edi_reference_doc_code': '1',  # Código anulación
                'reason': ref.reason_raw or f'Anula NC {credit_note.l10n_latam_document_number}',
            })
            
            _logger.info(f"✓ Wizard nativo creado con código de referencia '1' (anulación)")
            
        except Exception as e:
            _logger.error(f"❌ Error creando wizard de ND: {str(e)}")
            raise UserError(f"Error al crear wizard de nota de débito: {str(e)}")
        
        # Ejecutar creación usando lógica nativa
        try:
            result = wizard.create_debit()
            
            if result and 'res_id' in result:
                debit_note_id = result['res_id']
                debit_note = self.env['account.move'].browse(debit_note_id)
                
                _logger.info(f"✓ ND creada por wizard nativo: {debit_note.name} (ID: {debit_note_id})")
                
            elif isinstance(result, dict) and 'domain' in result:
                # El wizard devolvió múltiples documentos, tomar el último creado
                domain = result['domain']
                debit_notes = self.env['account.move'].search(domain, order='id desc', limit=1)
                
                if debit_notes:
                    debit_note = debit_notes[0]
                    _logger.info(f"✓ ND encontrada por dominio: {debit_note.name} (ID: {debit_note.id})")
                else:
                    raise UserError("No se pudo encontrar la nota de débito creada")
            else:
                raise UserError("El wizard no devolvió una nota de débito válida")
                
        except Exception as e:
            _logger.error(f"❌ Error ejecutando wizard de ND: {str(e)}")
            raise UserError(f"Error al ejecutar wizard de nota de débito: {str(e)}")
        
        # **CORRECCIÓN CRÍTICA: Forzar el tipo de documento correcto**
        self._fix_debit_note_document_type(debit_note)
        
        # Configurar referencia obligatoria al SET
        self._add_set_reference_to_debit_note(debit_note)
        
        # Vincular el caso al documento generado
        self.dte_case_id.write({
            'generation_status': 'generated',
            'generated_account_move_id': debit_note.id,
        })
        
        _logger.info(f"✅ NOTA DE DÉBITO GENERADA EXITOSAMENTE")
        _logger.info(f"   Documento: {debit_note.name}")
        _logger.info(f"   Tipo: {debit_note.l10n_latam_document_type_id.name}")
        _logger.info(f"   Referencias: {len(debit_note.l10n_cl_reference_ids)}")
        _logger.info(f"   Anula NC: {credit_note.name}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nota de Débito Generada',
            'res_model': 'account.move',
            'res_id': debit_note.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _fix_debit_note_document_type(self, debit_note):
        """
        Corrige el tipo de documento de la nota de débito.
        El wizard nativo a veces asigna tipo incorrecto.
        """
        # Buscar el tipo correcto de nota de débito
        debit_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', '56'),  # Nota de Débito Electrónica
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if not debit_doc_type:
            _logger.error("❌ No se encontró tipo de documento '56' para Nota de Débito")
            raise UserError("No se encontró el tipo de documento Nota de Débito Electrónica (56)")
        
        # Verificar el tipo actual
        current_type = debit_note.l10n_latam_document_type_id
        _logger.info(f"🔍 Tipo actual ND: {current_type.name} ({current_type.code})")
        
        if current_type.code != '56':
            # Corregir el tipo de documento
            _logger.info(f"🔧 Corrigiendo tipo de documento: {current_type.code} → 56")
            
            debit_note.write({
                'l10n_latam_document_type_id': debit_doc_type.id,
            })
            
            _logger.info(f"✅ Tipo de documento corregido: {debit_note.l10n_latam_document_type_id.name} ({debit_note.l10n_latam_document_type_id.code})")
        else:
            _logger.info(f"✅ Tipo de documento ya es correcto: {current_type.name} ({current_type.code})")
    
    def _add_set_reference_to_debit_note(self, debit_note):
        """
        Configura las referencias de la nota de débito en el orden correcto para cumplir 
        con los requisitos del SII.
        
        ORDEN REQUERIDO EN XML:
        1. SET (primera referencia - requisito SII)
        2. Documento anulado (segunda referencia - generada por wizard nativo)
        
        PATRÓN: Mismo que funciona en notas de crédito
        """
        _logger.info(f"=== CONFIGURANDO REFERENCIAS EN ORDEN CORRECTO PARA ND ===")
        
        # PASO 1: Capturar la referencia generada automáticamente por el wizard nativo
        existing_references = debit_note.l10n_cl_reference_ids
        _logger.info(f"Referencias existentes encontradas: {len(existing_references)}")
        
        if not existing_references:
            _logger.error("❌ No se encontraron referencias generadas por el wizard nativo")
            raise UserError("El wizard nativo no generó referencias al documento anulado")
        
        # Guardar la referencia al documento anulado (generada automáticamente)
        original_reference = existing_references[0]  # Debería ser la única referencia
        
        # Capturar datos de la referencia original antes de eliminarla
        original_ref_data = {
            'l10n_cl_reference_doc_type_id': original_reference.l10n_cl_reference_doc_type_id.id,
            'origin_doc_number': original_reference.origin_doc_number,
            'reference_doc_code': original_reference.reference_doc_code,
            'reason': original_reference.reason,
            'date': original_reference.date,
        }
        
        _logger.info(f"✓ Referencia original capturada: {original_ref_data['origin_doc_number']} (código: {original_ref_data['reference_doc_code']})")
        
        # PASO 2: Eliminar todas las referencias existentes
        _logger.info("🗑️  Eliminando referencias existentes para recrear en orden correcto")
        existing_references.unlink()
        
        # PASO 3: Buscar tipo de documento SET
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if not set_doc_type:
            _logger.error("❌ No se encontró tipo de documento SET")
            raise UserError("No se encontró el tipo de documento SET para referencias")
        
        # PASO 4: Recrear referencias en el ORDEN CORRECTO
        
        # PRIMERA REFERENCIA: SET (aparece primera en XML)
        set_reference_vals = {
            'move_id': debit_note.id,
            'l10n_cl_reference_doc_type_id': set_doc_type.id,
            'origin_doc_number': self.dte_case_id.case_number_raw,
            'reason': f'CASO {self.dte_case_id.case_number_raw}',
            'date': fields.Date.context_today(self),
            # NO incluir reference_doc_code para referencia SET
        }
        
        set_ref = self.env['l10n_cl.account.invoice.reference'].create(set_reference_vals)
        _logger.info(f"✓ PRIMERA referencia creada (SET): {set_ref.origin_doc_number}")
        
        # SEGUNDA REFERENCIA: Documento anulado (aparece segunda en XML)
        original_ref_data['move_id'] = debit_note.id
        original_ref = self.env['l10n_cl.account.invoice.reference'].create(original_ref_data)
        _logger.info(f"✓ SEGUNDA referencia creada (doc anulado): {original_ref.origin_doc_number} (código: {original_ref.reference_doc_code})")
        
        # PASO 5: Verificar el orden final
        final_references = debit_note.l10n_cl_reference_ids.sorted('id')
        _logger.info(f"✅ REFERENCIAS CONFIGURADAS EN ORDEN CORRECTO:")
        _logger.info(f"   Total referencias: {len(final_references)}")
        
        for i, ref in enumerate(final_references, 1):
            _logger.info(f"   {i}. {ref.l10n_cl_reference_doc_type_id.code} - {ref.origin_doc_number} - {ref.reason}")
        
        # Verificar que SET es la primera referencia
        if final_references and final_references[0].l10n_cl_reference_doc_type_id.code == 'SET':
            _logger.info("✅ ORDEN CORRECTO: SET aparece como primera referencia en XML")
        else:
            _logger.error("❌ ORDEN INCORRECTO: SET no es la primera referencia")
            
        return True

    # ========================================================================
    # MÉTODOS PARA GENERACIÓN DE GUÍAS DE DESPACHO
    # ========================================================================

    # Mapping de tipos de movimiento para guías de despacho
    DISPATCH_MOVEMENT_MAPPING = {
        # Traslado Interno - Partner = Empresa misma
        'internal_transfer': {
            'keywords': ['TRASLADO INTERNO', 'ENTRE BODEGAS', 'MATERIALES ENTRE BODEGAS'],
            'partner_type': 'company_self',
            'sii_movement_type': '2',  # Traslado interno según SII
            'requires_price': False,
            'is_sale': False
        },
        
        # Venta con Transporte por Emisor - Partner = Cliente certificación
        'sale_issuer_transport': {
            'keywords': ['VENTA', 'EMISOR DEL DOCUMENTO AL LOCAL'],
            'partner_type': 'certification_pool',
            'sii_movement_type': '1',  # Venta según SII
            'requires_price': True,
            'is_sale': True
        },
        
        # Venta con Retiro por Cliente - Partner = Cliente certificación  
        'sale_client_pickup': {
            'keywords': ['VENTA', 'CLIENTE', 'TRASLADO POR: CLIENTE'],
            'partner_type': 'certification_pool',
            'sii_movement_type': '1',  # Venta según SII
            'requires_price': True,
            'is_sale': True
        }
    }

    def _generate_delivery_guide(self):
        """
        Método principal para generar guías de despacho.
        """
        self.ensure_one()
        _logger.info(f"=== INICIANDO GENERACIÓN DE GUÍA DE DESPACHO ===")
        _logger.info(f"Caso: {self.dte_case_id.case_number_raw}")
        
        # **VERIFICACIÓN: Comprobar si ya existe una guía vinculada**
        if self.dte_case_id.generated_stock_picking_id:
            _logger.info(f"Caso {self.dte_case_id.id} ya tiene guía vinculada: {self.dte_case_id.generated_stock_picking_id.name}")
            return {
                'type': 'ir.actions.act_window',
                'name': 'Guía de Despacho Existente',
                'res_model': 'stock.picking',
                'res_id': self.dte_case_id.generated_stock_picking_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        
        # 1. Clasificar tipo de movimiento
        movement_type, movement_config = self._classify_dispatch_movement(self.dte_case_id)
        _logger.info(f"Tipo de movimiento detectado: {movement_type}")
        _logger.info(f"Configuración: {movement_config}")
        
        # 2. Validaciones específicas
        self._validate_delivery_guide_requirements(movement_config)
        _logger.info("Validaciones completadas")
        
        # 3. Obtener partner apropiado
        partner = self._get_dispatch_partner(self.dte_case_id, movement_config)
        _logger.info(f"Partner seleccionado: {partner.name} (ID: {partner.id})")
        
        # 4. Crear picking con configuración específica
        picking = self._create_stock_picking(partner, movement_config)
        _logger.info(f"Stock picking creado: {picking.name}")
        
        # 5. Agregar líneas de productos
        self._create_picking_lines(picking, movement_config)
        _logger.info(f"Líneas de picking creadas")
        
        # 6. Finalizar y procesar
        self._finalize_delivery_guide(picking, movement_config)
        _logger.info(f"Guía de despacho finalizada")
        
        _logger.info(f"✅ GUÍA DE DESPACHO GENERADA EXITOSAMENTE: {picking.name}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Guía de Despacho Generada',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _classify_dispatch_movement(self, dte_case):
        """
        Clasifica el tipo de movimiento de la guía de despacho
        basado en motivo y tipo de traslado.
        """
        motivo = (dte_case.dispatch_motive_raw or '').upper()
        transporte = (dte_case.dispatch_transport_type_raw or '').upper()
        
        combined_text = f"{motivo} {transporte}"
        _logger.info(f"Analizando texto combinado: '{combined_text}'")
        
        for movement_type, config in self.DISPATCH_MOVEMENT_MAPPING.items():
            if any(keyword in combined_text for keyword in config['keywords']):
                _logger.info(f"Tipo de movimiento detectado: {movement_type}")
                return movement_type, config
                
        # Default fallback
        _logger.warning(f"No se detectó tipo específico, usando fallback: sale_issuer_transport")
        return 'sale_issuer_transport', self.DISPATCH_MOVEMENT_MAPPING['sale_issuer_transport']

    def _get_dispatch_partner(self, dte_case, movement_config):
        """
        Obtiene el partner apropiado según el tipo de movimiento.
        """
        if movement_config['partner_type'] == 'company_self':
            # Para traslados internos, usar la empresa misma
            company_partner = self.certification_process_id.company_id.partner_id
            _logger.info(f"Usando empresa misma como partner: {company_partner.name}")
            return company_partner
            
        elif movement_config['partner_type'] == 'certification_pool':
            # Para ventas, usar pool de partners de certificación
            partner = self._get_available_certification_partner()
            _logger.info(f"Usando partner de certificación: {partner.name}")
            return partner
            
        else:
            raise UserError(_('Tipo de partner no reconocido: %s') % movement_config['partner_type'])

    def _get_available_certification_partner(self):
        """
        Obtiene un partner disponible del pool de certificación.
        Considera tanto facturas como guías de despacho ya generadas en este proceso.
        """
        # Buscar partners ya utilizados en casos DTE (facturas) del proceso actual
        used_partners_in_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
            ('partner_id', '!=', False)
        ]).mapped('partner_id')
        
        # Buscar partners ya utilizados en guías de despacho generadas del proceso actual
        used_partners_in_pickings = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
            ('generated_stock_picking_id', '!=', False)
        ]).mapped('generated_stock_picking_id.partner_id')
        
        # Combinar ambos conjuntos de partners usados
        all_used_partners = used_partners_in_cases | used_partners_in_pickings
        
        _logger.info(f"Partners usados en casos DTE: {used_partners_in_cases.mapped('name')}")
        _logger.info(f"Partners usados en guías: {used_partners_in_pickings.mapped('name')}")
        _logger.info(f"Total partners usados: {all_used_partners.mapped('name')}")
        
        # Buscar un partner no usado en este proceso
        available_partners = self.env['res.partner'].search([
            ('l10n_cl_edi_certification_partner', '=', True),
            ('id', 'not in', all_used_partners.ids)
        ])
        
        _logger.info(f"Partners disponibles: {available_partners.mapped('name')}")
        
        if not available_partners:
            # Si no hay partners únicos disponibles, usar cualquiera del pool
            _logger.warning("No hay partners únicos disponibles, reutilizando del pool")
            available_partners = self.env['res.partner'].search([
                ('l10n_cl_edi_certification_partner', '=', True)
            ])
        
        if not available_partners:
            raise UserError(_('No hay partners de certificación disponibles'))
        
        return available_partners[0]

    def _validate_delivery_guide_requirements(self, movement_config):
        """
        Valida requisitos específicos según tipo de movimiento.
        """
        validations = []
        
        # Validaciones comunes
        validations.extend([
            self._validate_caf_available_for_guide(),
            self._validate_company_address_configured(),
            self._validate_picking_type_available(),
        ])
        
        # Validaciones específicas por tipo
        if movement_config['is_sale']:
            validations.extend([
                self._validate_prices_present_in_items(),
            ])
        else:
            validations.extend([
                self._validate_internal_locations_available(),
            ])
            
        if not all(validations):
            raise UserError(_('No se cumplen todos los requisitos para generar la guía de despacho'))
        
        return True

    def _validate_caf_available_for_guide(self):
        """Valida que exista CAF disponible para documento tipo 52."""
        caf_count = self.env['l10n_cl.dte.caf'].search_count([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('l10n_latam_document_type_id.code', '=', '52'),
            ('status', '=', 'in_use')
        ])
        
        if caf_count == 0:
            raise UserError(_('No hay CAF disponible para Guía de Despacho Electrónica (tipo 52)'))
        
        return True

    def _validate_company_address_configured(self):
        """Valida que la empresa tenga dirección configurada."""
        company = self.certification_process_id.company_id
        if not company.street:
            raise UserError(_('La empresa debe tener dirección configurada para emitir guías de despacho'))
        return True

    def _validate_picking_type_available(self):
        """Valida que exista un tipo de picking disponible."""
        picking_types = self.env['stock.picking.type'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('code', '=', 'outgoing')
        ])
        
        if not picking_types:
            raise UserError(_('No hay tipos de picking de salida configurados'))
        
        return True

    def _validate_prices_present_in_items(self):
        """Valida que los items tengan precios para ventas."""
        items_without_price = self.dte_case_id.item_ids.filtered(lambda item: item.price_unit <= 0)
        if items_without_price:
            raise UserError(_('Todos los items deben tener precio unitario para ventas'))
        return True

    def _validate_internal_locations_available(self):
        """Valida que existan ubicaciones internas para traslados."""
        internal_locations = self.env['stock.location'].search([
            ('company_id', '=', self.certification_process_id.company_id.id),
            ('usage', '=', 'internal')
        ])
        
        if len(internal_locations) < 2:
            raise UserError(_('Se requieren al menos 2 ubicaciones internas para traslados'))
        
        return True

    def _create_stock_picking(self, partner, movement_config):
        """
        Crea el stock.picking con configuración específica del movimiento.
        """
        company = self.certification_process_id.company_id
        
        # Determinar ubicaciones según tipo de movimiento
        if movement_config['partner_type'] == 'company_self':
            # Traslado interno: misma empresa, diferentes ubicaciones
            location_src = self._get_internal_source_location(company)
            location_dest = self._get_internal_dest_location(company)
        else:
            # Venta: de stock interno a ubicación del cliente
            location_src = self._get_stock_location(company)
            location_dest = partner.property_stock_customer or self._get_customer_location()
            
        # Determinar motivo de traslado según dispatch_motive_raw del caso
        delivery_guide_reason = self._get_delivery_guide_reason_from_case()
        
        # Determinar tipo de transporte según dispatch_transport_type_raw del caso
        transport_type = self._map_dispatch_transport_to_code(self.dte_case_id.dispatch_transport_type_raw)
        
        # Asegurar que el partner tenga configuración para guías de despacho
        if not partner.l10n_cl_delivery_guide_price:
            partner.l10n_cl_delivery_guide_price = 'none'  # Para certificación, no mostrar precios
            
        picking_vals = {
            'partner_id': partner.id,
            'picking_type_id': self._get_picking_type(movement_config).id,
            'location_id': location_src.id,  # Campo correcto para ubicación origen
            'location_dest_id': location_dest.id,
            'origin': f'Certificación SII - Caso {self.dte_case_id.case_number_raw}',
            'l10n_cl_edi_certification_id': self.certification_process_id.id,  # Proceso de certificación
            'l10n_cl_edi_certification_case_id': self.dte_case_id.id,  # Caso DTE específico
            'l10n_cl_delivery_guide_reason': delivery_guide_reason,  # Motivo según caso DTE
            'l10n_cl_dte_gd_transport_type': transport_type,  # Tipo de transporte
        }
        
        _logger.info(f"Creando picking con valores: {picking_vals}")
        return self.env['stock.picking'].create(picking_vals)

    def _get_internal_source_location(self, company):
        """Obtiene ubicación origen para traslados internos."""
        location = self.env['stock.location'].search([
            ('company_id', '=', company.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        
        if not location:
            # Fallback a ubicación stock principal
            location = self.env['stock.warehouse'].search([
                ('company_id', '=', company.id)
            ], limit=1).lot_stock_id
            
        if not location:
            raise UserError(_('No se encontró ubicación origen para traslado interno'))
            
        return location
        
    def _get_internal_dest_location(self, company):
        """Obtiene ubicación destino para traslados internos."""
        # Buscar una ubicación diferente a la origen
        source_location = self._get_internal_source_location(company)
        
        location = self.env['stock.location'].search([
            ('company_id', '=', company.id),
            ('usage', '=', 'internal'),
            ('id', '!=', source_location.id)
        ], limit=1)
        
        if not location:
            # Si no hay otra ubicación interna, crear una temporal para certificación
            location = self.env['stock.location'].create({
                'name': 'Bodega Destino Certificación',
                'usage': 'internal',
                'location_id': source_location.location_id.id,
                'company_id': company.id,
            })
            
        return location

    def _get_stock_location(self, company):
        """Obtiene ubicación de stock principal."""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', company.id)
        ], limit=1)
        
        if not warehouse:
            raise UserError(_('No se encontró almacén configurado para la empresa'))
            
        return warehouse.lot_stock_id

    def _get_customer_location(self):
        """Obtiene ubicación genérica de clientes."""
        location = self.env['stock.location'].search([
            ('usage', '=', 'customer')
        ], limit=1)
        
        if not location:
            raise UserError(_('No se encontró ubicación de clientes'))
            
        return location

    def _get_picking_type(self, movement_config):
        """Obtiene el tipo de picking apropiado."""
        company = self.certification_process_id.company_id
        
        if movement_config['partner_type'] == 'company_self':
            # Para traslados internos, buscar tipo internal
            picking_type = self.env['stock.picking.type'].search([
                ('company_id', '=', company.id),
                ('code', '=', 'internal')
            ], limit=1)
        else:
            # Para ventas, buscar tipo outgoing
            picking_type = self.env['stock.picking.type'].search([
                ('company_id', '=', company.id),
                ('code', '=', 'outgoing')
            ], limit=1)
        
        if not picking_type:
            # Fallback: cualquier tipo de la empresa
            picking_type = self.env['stock.picking.type'].search([
                ('company_id', '=', company.id)
            ], limit=1)
            
        if not picking_type:
            raise UserError(_('No se encontró tipo de picking configurado'))
            
        return picking_type

    def _create_picking_lines(self, picking, movement_config):
        """
        Crea las líneas del picking basadas en los items del caso DTE.
        """
        for item in self.dte_case_id.item_ids:
            # Buscar o crear producto para guía de despacho (tipo consumible)
            product = self._get_product_for_delivery_guide(item.name)
            
            # Crear línea de movimiento
            move_vals = {
                'name': item.name,
                'product_id': product.id,
                'product_uom_qty': item.quantity,
                'product_uom': product.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,  # Campo correcto para ubicación origen
                'location_dest_id': picking.location_dest_id.id,
            }
            
            # Para ventas, agregar información de precio
            if movement_config['requires_price'] and item.price_unit > 0:
                # El precio se maneja en la factura posterior, no en el picking
                pass
            
            _logger.info(f"Creando línea de movimiento: {move_vals}")
            self.env['stock.move'].create(move_vals)

    def _get_product_for_delivery_guide(self, item_name):
        """
        Obtiene o crea un producto para guías de despacho.
        Usa tipo 'consu' (consumible) para permitir movimientos de stock.
        """
        # Buscar producto existente tipo consumible
        product = self.env['product.product'].search([
            ('name', '=', item_name),
            ('type', '=', 'consu')
        ], limit=1)
        
        if product:
            _logger.info("Producto consumible existente encontrado: %s (ID: %s)", product.name, product.id)
            return product
        
        # Crear producto consumible para guía de despacho
        _logger.info("Creando nuevo producto consumible para guía: %s", item_name)
        product = self.env['product.product'].create({
            'name': item_name,
            'type': 'consu',  # Consumible - permite movimientos de stock
            'invoice_policy': 'delivery',  # Facturar al entregar
            'list_price': 0,
            'standard_price': 0,
            'sale_ok': True,
            'purchase_ok': True,
            'categ_id': self._get_certification_product_category().id,
        })
        
        _logger.info("✓ Producto consumible creado: %s (ID: %s)", product.name, product.id)
        return product

    def _get_certification_product_category(self):
        """Obtiene o crea categoría para productos de certificación."""
        category = self.env['product.category'].search([
            ('name', '=', 'Certificación SII')
        ], limit=1)
        
        if not category:
            category = self.env['product.category'].create({
                'name': 'Certificación SII',
            })
            
        return category
    
    def _get_delivery_guide_reason_from_case(self):
        """
        Determina el motivo de traslado (l10n_cl_delivery_guide_reason) basado en 
        el campo dispatch_motive_raw del caso DTE.
        
        Mapeo según SII:
        1 = Operación constituye venta
        2 = Ventas por efectuar  
        3 = Consignaciones
        4 = Entregas gratuitas
        5 = Traslados internos
        6 = Otros traslados no venta
        7 = Guía de devolución
        8 = Traslado para exportación (no constituye venta)
        """
        self.ensure_one()
        
        dispatch_motive = (self.dte_case_id.dispatch_motive_raw or '').upper().strip()
        
        # Mapeo de texto a código SII según l10n_cl_edi_stock
        # 1 = Operation is sale
        # 2 = Sales to be made  
        # 3 = Consignments
        # 4 = Free delivery
        # 5 = Internal Transfer
        # 6 = Other not-sale transfers
        # 7 = Return guide
        # 8 = Exportation Transfers
        # 9 = Export Sales
        motive_mapping = {
            'VENTA': '1',  # Operation is sale
            'VENTAS POR EFECTUAR': '2',  # Sales to be made
            'CONSIGNACIONES': '3',  # Consignments
            'ENTREGAS GRATUITAS': '4',  # Free delivery
            'TRASLADO DE MATERIALES ENTRE BODEGAS DE LA EMPRESA': '5',  # Internal Transfer
            'TRASLADO INTERNO': '5',  # Internal Transfer
            'TRASLADOS INTERNOS': '5',  # Internal Transfer
            'TRASLADO ENTRE BODEGAS': '5',  # Internal Transfer
            'OTROS TRASLADOS': '6',  # Other not-sale transfers
            'DEVOLUCION': '7',  # Return guide
            'DEVOLUCIÓN': '7',  # Return guide
            'EXPORTACION': '8',  # Exportation Transfers
            'EXPORTACIÓN': '8',  # Exportation Transfers
            'VENTAS EXPORTACION': '9',  # Export Sales
            'VENTAS DE EXPORTACIÓN': '9',  # Export Sales
        }
        
        # Buscar coincidencia exacta
        if dispatch_motive in motive_mapping:
            reason_code = motive_mapping[dispatch_motive]
            _logger.info(f"Motivo traslado: '{dispatch_motive}' → Código SII: {reason_code}")
            return reason_code
        
        # Buscar coincidencias parciales para casos complejos
        for key, code in motive_mapping.items():
            if key in dispatch_motive:
                reason_code = code
                _logger.info(f"Motivo traslado (coincidencia parcial): '{dispatch_motive}' contiene '{key}' → Código SII: {reason_code}")
                return reason_code
        
        # Fallback: si no encuentra coincidencia, intentar determinar por tipo de picking
        _logger.warning(f"No se pudo mapear motivo de traslado: '{dispatch_motive}'. Usando fallback.")
        return '1'  # Venta por defecto

    def _finalize_delivery_guide(self, picking, movement_config):
        """
        Finaliza la guía y actualiza estados del caso.
        """
        # Confirmar picking
        picking.action_confirm()
        _logger.info(f"Picking confirmado: {picking.name}")
        
        # Asignar disponibilidad (asigna stock automáticamente para certificación)
        picking.action_assign()
        _logger.info(f"Stock asignado: {picking.name}")
        
        # Para certificación, NO marcar como done automáticamente
        # El usuario necesita validar manualmente que todo esté correcto
        _logger.info(f"Picking creado en estado '{picking.state}' - Usuario debe validar manualmente")
        
        # Actualizar caso DTE
        self.dte_case_id.write({
            'generated_stock_picking_id': picking.id,
            'generation_status': 'generated',
            # NO sobrescribir partner_id aquí - mantener la lógica de herencia automática
        })
        
        _logger.info(f"Caso DTE actualizado - Picking: {picking.name}, Partner: {picking.partner_id.name}")
        
        return True

    # === MÉTODOS HELPER PARA MAPEO DE EXPORTACIÓN ===
    
    def _map_port_name_to_record(self, port_name_raw):
        """Mapea nombre de puerto a registro l10n_cl.customs_port"""
        if not port_name_raw:
            return self.env['l10n_cl.customs_port']
        
        # Buscar por nombre exacto primero
        port = self.env['l10n_cl.customs_port'].search([
            ('name', '=ilike', port_name_raw.strip())
        ], limit=1)
        
        if not port:
            # Buscar por coincidencia parcial
            port = self.env['l10n_cl.customs_port'].search([
                ('name', 'ilike', port_name_raw.strip())
            ], limit=1)
            
        if port:
            _logger.info(f"Puerto encontrado: {port_name_raw} → {port.name} (código: {port.code})")
        else:
            _logger.warning(f"Puerto no encontrado: {port_name_raw}")
            
        return port
    
    def _map_country_name_to_record(self, country_name_raw):
        """Mapea nombre de país a registro res.country"""
        if not country_name_raw:
            return self.env['res.country']
        
        # Buscar por nombre exacto primero
        country = self.env['res.country'].search([
            ('name', '=ilike', country_name_raw.strip())
        ], limit=1)
        
        if not country:
            # Buscar por nombre de aduana
            country = self.env['res.country'].search([
                ('l10n_cl_customs_name', '=ilike', country_name_raw.strip())
            ], limit=1)
            
        if country:
            _logger.info(f"País encontrado: {country_name_raw} → {country.name} (código SII: {country.l10n_cl_customs_code})")
        else:
            _logger.warning(f"País no encontrado: {country_name_raw}")
            
        return country
    
    def _map_transport_way_to_code(self, transport_way_raw):
        """Mapea vía de transporte a código l10n_cl_customs_transport_type válido"""
        if not transport_way_raw:
            return False
        
        transport_upper = transport_way_raw.upper()
        
        # Mapeo usando códigos válidos de Odoo l10n_cl_edi_exports
        if 'MARITIM' in transport_upper or 'FLUVIAL' in transport_upper or 'LACUSTRE' in transport_upper:
            return '01'  # Maritime, river and lake
        elif 'AERE' in transport_upper or 'AEREO' in transport_upper:
            return '04'  # Aerial
        elif 'POSTAL' in transport_upper:
            return '05'  # Post
        elif 'FERROVIARIO' in transport_upper or 'FERROCARRIL' in transport_upper:
            return '06'  # Railway
        elif 'TERRESTRE' in transport_upper or 'CARRETERO' in transport_upper:
            return '07'  # Wagoner / Land
        elif 'DUCTOS' in transport_upper or 'OLEODUCTO' in transport_upper or 'GASODUCTO' in transport_upper:
            return '08'  # Pipelines, Gas Pipelines
        elif 'ELECTRICA' in transport_upper or 'ENERGIA' in transport_upper:
            return '09'  # Power Line (aerial or underground)
        elif 'COURIER' in transport_upper or 'MENSAJERIA' in transport_upper:
            return '11'  # Courier/Air Courier
        else:
            return '10'  # Other (para casos no reconocidos)
        
        _logger.warning(f"Vía de transporte no reconocida: {transport_way_raw}, usando 'Other'")
        return '10'
    
    def _map_sale_modality_to_code(self, sale_modality_raw):
        """Mapea modalidad de venta a código l10n_cl_customs_sale_mode válido"""
        if not sale_modality_raw:
            return False
        
        modality_upper = sale_modality_raw.upper()
        
        # Mapeo usando códigos válidos de Odoo l10n_cl_edi_exports
        if 'FIRME' in modality_upper or 'A FIRME' in modality_upper:
            return '1'  # Firmly
        elif 'CONDICIONAL' in modality_upper or 'CONDICION' in modality_upper:
            return '2'  # Under condition
        elif 'CONSIGNACION LIBRE' in modality_upper:
            return '3'  # Under free consignment
        elif 'CONSIGNACION' in modality_upper and 'MINIMO' in modality_upper:
            return '4'  # Under consignment with a minimum firmly
        elif 'SIN PAGO' in modality_upper or 'GRATUITO' in modality_upper:
            return '9'  # Without payment
        else:
            # Para casos no reconocidos, usar consignación libre como default
            return '3'  # Under free consignment
        
        _logger.warning(f"Modalidad de venta no reconocida: {sale_modality_raw}, usando 'Under free consignment'")
        return '3'
    
    def _map_incoterm_to_record(self, incoterm_raw):
        """Mapea cláusula de venta (Incoterm) a registro account.incoterms"""
        if not incoterm_raw:
            return self.env['account.incoterms']
        
        # Buscar por código exacto
        incoterm = self.env['account.incoterms'].search([
            ('code', '=ilike', incoterm_raw.strip())
        ], limit=1)
        
        if not incoterm:
            # Buscar por nombre
            incoterm = self.env['account.incoterms'].search([
                ('name', 'ilike', incoterm_raw.strip())
            ], limit=1)
            
        if incoterm:
            _logger.info(f"Incoterm encontrado: {incoterm_raw} → {incoterm.code} ({incoterm.name})")
        else:
            _logger.warning(f"Incoterm no encontrado: {incoterm_raw}")
            
        return incoterm
    
    def _configure_partner_as_foreign(self, partner):
        """Configura partner como extranjero si es necesario"""
        if partner.l10n_cl_sii_taxpayer_type != '4':  # 4 = Extranjero
            partner.write({'l10n_cl_sii_taxpayer_type': '4'})
            _logger.info(f"Partner {partner.name} configurado como extranjero")
    
    def _map_payment_terms_to_code(self, payment_terms_raw):
        """Mapea forma de pago exportación a código válido"""
        if not payment_terms_raw:
            return False
        
        payment_upper = payment_terms_raw.upper()
        
        if 'ANTICIPO' in payment_upper:
            return 'ANTICIPO'
        elif 'ACRED' in payment_upper or 'CREDITO' in payment_upper:
            return 'ACRED'
        elif 'COBRANZA' in payment_upper:
            return 'COBRANZA'
        elif 'CONTADO' in payment_upper:
            return 'CONTADO'
        else:
            return 'OTROS'
    
    def _get_export_partner_for_case(self):
        """Obtiene partner extranjero específico según el caso de exportación"""
        self.ensure_one()
        
        # Determinar país/nacionalidad basado en los datos del caso
        country_raw = None
        nationality_raw = None
        
        if hasattr(self.dte_case_id, 'export_client_nationality_raw') and self.dte_case_id.export_client_nationality_raw:
            nationality_raw = self.dte_case_id.export_client_nationality_raw.upper()
        elif hasattr(self.dte_case_id, 'export_recipient_country_raw') and self.dte_case_id.export_recipient_country_raw:
            country_raw = self.dte_case_id.export_recipient_country_raw.upper()
        elif hasattr(self.dte_case_id, 'export_destination_country_raw') and self.dte_case_id.export_destination_country_raw:
            country_raw = self.dte_case_id.export_destination_country_raw.upper()
        
        # Seleccionar partner específico según nacionalidad/país
        if nationality_raw and 'ALEMANIA' in nationality_raw:
            # Servicios hoteleros alemanes
            partner_id = self.env.ref('l10n_cl_edi_certification.export_partner_germany_hospitality', False)
        elif country_raw and 'ALEMANIA' in country_raw:
            # Servicios profesionales alemanes
            partner_id = self.env.ref('l10n_cl_edi_certification.export_partner_germany_services', False)
        elif country_raw and 'ECUADOR' in country_raw:
            # Productos ecuatorianos
            partner_id = self.env.ref('l10n_cl_edi_certification.export_partner_ecuador_products', False)
        else:
            # Partner genérico para otros casos
            partner_id = self.env.ref('l10n_cl_edi_certification.export_partner_generic_foreign', False)
        
        if not partner_id:
            # Fallback al partner genérico si no se encuentra el específico
            partner_id = self.env.ref('l10n_cl_edi_certification.export_partner_generic_foreign')
        
        _logger.info(f"Partner de exportación seleccionado para caso {self.dte_case_id.case_number_raw}: {partner_id.name} (País/Nacionalidad: {country_raw or nationality_raw or 'GENÉRICO'})")
        return partner_id
    
    def _configure_export_currency_on_invoice(self, invoice):
        """Configura la moneda correcta para documentos de exportación"""
        self.ensure_one()
        
        if not hasattr(self.dte_case_id, 'export_currency_raw') or not self.dte_case_id.export_currency_raw:
            _logger.warning(f"No hay moneda de exportación especificada para caso {self.dte_case_id.case_number_raw}")
            return
        
        currency_raw = self.dte_case_id.export_currency_raw.upper()
        currency = None
        
        # Mapear monedas del SII a códigos ISO de Odoo
        if 'DOLAR USA' in currency_raw or 'DOLLAR' in currency_raw:
            currency = self.env.ref('base.USD', False)
        elif 'FRANCO SZ' in currency_raw or 'FRANC' in currency_raw or 'CHF' in currency_raw:
            currency = self.env.ref('base.CHF', False)
        elif 'EURO' in currency_raw or 'EUR' in currency_raw:
            currency = self.env.ref('base.EUR', False)
        
        if currency and currency.active:
            # Cambiar moneda de la factura
            invoice.write({'currency_id': currency.id})
            _logger.info(f"Moneda configurada: {currency_raw} → {currency.name} ({currency.symbol})")
            
            # Actualizar también el sale.order asociado si existe
            if hasattr(invoice, 'invoice_origin') and invoice.invoice_origin:
                sale_order = self.env['sale.order'].search([('name', '=', invoice.invoice_origin)], limit=1)
                if sale_order:
                    sale_order.write({'currency_id': currency.id})
                    _logger.info(f"Moneda también actualizada en sale.order: {sale_order.name}")
        else:
            if currency and not currency.active:
                _logger.warning(f"Moneda {currency.name} no está activa. Activando automáticamente...")
                currency.write({'active': True})
                invoice.write({'currency_id': currency.id})
                _logger.info(f"Moneda activada y configurada: {currency_raw} → {currency.name}")
            else:
                _logger.error(f"Moneda no reconocida: {currency_raw}. Manteniendo CLP por defecto.")
                # Aquí podríamos crear la moneda automáticamente si fuera necesario
    
    def _get_export_currency_id(self):
        """Obtiene el ID de la moneda de exportación para el sale.order"""
        self.ensure_one()
        
        if not hasattr(self.dte_case_id, 'export_currency_raw') or not self.dte_case_id.export_currency_raw:
            return None
        
        currency_raw = self.dte_case_id.export_currency_raw.upper()
        
        # Mapear monedas del SII a códigos ISO de Odoo
        if 'DOLAR USA' in currency_raw or 'DOLLAR' in currency_raw:
            currency = self.env.ref('base.USD', False)
        elif 'FRANCO SZ' in currency_raw or 'FRANC' in currency_raw or 'CHF' in currency_raw:
            currency = self.env.ref('base.CHF', False)
        elif 'EURO' in currency_raw or 'EUR' in currency_raw:
            currency = self.env.ref('base.EUR', False)
        else:
            return None
        
        if currency:
            # Activar moneda si no está activa
            if not currency.active:
                currency.write({'active': True})
                _logger.info(f"Moneda {currency.name} activada automáticamente")
            
            return currency.id
        
        return None
    
