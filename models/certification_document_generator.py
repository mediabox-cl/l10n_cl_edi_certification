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
        Método principal que coordina la generación del documento.
        Delega a métodos específicos según el tipo de documento.
        """
        self.ensure_one()
        
        # Verificar que el caso esté en estado correcto
        if self.dte_case_id.generation_status != 'pending':
            raise UserError(_("El caso DTE ya ha sido procesado"))
        
        # Determinar método basado en el tipo de documento
        doc_type = self.dte_case_id.document_type_code
        method_name = f'_generate_document_type_{doc_type}'
        
        # Verificar que el método existe
        if not hasattr(self, method_name):
            raise UserError(_("Tipo de documento %s no está soportado") % doc_type)
        
        # Llamar al método específico usando dispatch dinámico
        try:
            generator_method = getattr(self, method_name)
            move = generator_method()
            
            # Actualizar el estado del caso DTE
            self.dte_case_id.write({
                'generated_account_move_id': move.id,
                'generation_status': 'generated',
                'error_message': False
            })
            
            _logger.info("Documento generado exitosamente para caso %s", self.dte_case_id.case_number_raw)
            return move
            
        except Exception as e:
            # Marcar el caso como error
            self.dte_case_id.write({
                'generation_status': 'error',
                'error_message': str(e)
            })
            _logger.error("Error generando documento para caso %s: %s", self.dte_case_id.case_number_raw, str(e))
            raise

    # === MÉTODOS DE GENERACIÓN POR TIPO DE DOCUMENTO ===
    # Nota: Estos métodos están expresados pero no desarrollados inicialmente
    
    def _generate_document_type_33(self):
        """
        Genera Factura Electrónica (33) a partir de un caso DTE.
        """
        self.ensure_one()
        _logger.info("Generando Factura Electrónica (33) para caso %s", self.dte_case_id.case_number_raw)
        
        # 1. Preparar valores base para la factura
        move_vals = self._prepare_base_move_vals()
        
        # 2. Preparar líneas de detalle
        invoice_lines_vals = []
        for item in self.dte_case_id.item_ids:
            line_vals = self._prepare_invoice_line_vals_from_dte_item(
                item, move_vals.get('move_type', 'out_invoice')
            )
            invoice_lines_vals.append((0, 0, line_vals))
        
        # 3. Añadir líneas a los valores del documento
        move_vals['invoice_line_ids'] = invoice_lines_vals
        
        # 4. Crear el documento (sin descuentos ni referencias aún)
        new_move = self.env['account.move'].create(move_vals)
        _logger.info("Documento base creado: %s (ID: %s)", new_move.name, new_move.id)
        
        # 5. Añadir referencias SET y otras si existen
        self._create_document_references(new_move)
        
        # 6. Aplicar descuento global si corresponde
        if self.dte_case_id.global_discount_percent and self.dte_case_id.global_discount_percent > 0:
            self._apply_global_discount(new_move, self.dte_case_id.global_discount_percent)
            
        # 7. Validar según configuración (opcional)
        # Si está configurado para validar automáticamente facturas electrónicas
        # if self.certification_process_id.auto_validate_documents:
        #    new_move.action_post()
        
        _logger.info("Factura Electrónica (33) generada exitosamente: %s", new_move.name)
        return new_move
    
    def _generate_document_type_34(self):
        """Genera Factura No Afecta o Exenta Electrónica (34)"""
        _logger.info("Generando Factura Exenta (34) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para facturas exentas
        raise NotImplementedError("Generación de Factura Exenta (34) pendiente de implementación")
    
    def _generate_document_type_61(self):
        """
        Genera Nota de Crédito Electrónica (61) a partir de un caso DTE.
        
        Tipos de NC en sets de prueba:
        1. Corrección de datos (giro, texto)
        2. Devolución de mercadería
        3. Anulación de factura
        """
        self.ensure_one()
        _logger.info("Generando Nota de Crédito (61) para caso %s", self.dte_case_id.case_number_raw)
        
        # 1. Preparar valores base para la nota de crédito
        move_vals = self._prepare_base_move_vals()
        
        # 2. Buscar el documento original referenciado si existe
        referenced_move = None
        referenced_case = None
        
        if self.dte_case_id.reference_ids:
            for ref in self.dte_case_id.reference_ids:
                if ref.referenced_sii_case_number:
                    referenced_case = self.env['l10n_cl_edi.certification.case.dte'].search([
                        ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
                        ('case_number_raw', '=', ref.referenced_sii_case_number),
                        ('generated_account_move_id', '!=', False)
                    ], limit=1)
                    
                    if referenced_case:
                        referenced_move = referenced_case.generated_account_move_id
                        _logger.info("Documento referenciado encontrado: %s (ID: %s)", 
                                    referenced_move.name, referenced_move.id)
                        break
        
        # 3. Determinar el tipo de nota de crédito basado en la razón
        nc_type = 'text_correction'  # por defecto
        reason_raw = ""
        
        if self.dte_case_id.reference_ids:
            reason_raw = self.dte_case_id.reference_ids[0].reason_raw or ""
            
            if reason_raw:
                reason_raw = reason_raw.upper()
                if 'DEVOLU' in reason_raw and 'MERCAD' in reason_raw:
                    nc_type = 'return'
                elif 'ANULA' in reason_raw:
                    nc_type = 'cancel'
                elif 'CORRIGE' in reason_raw and 'GIRO' in reason_raw:
                    nc_type = 'text_correction'
                elif 'CORRIGE' in reason_raw and 'MONTO' in reason_raw:
                    nc_type = 'amount_correction'
        
        _logger.info("Tipo de Nota de Crédito: %s - Razón: %s", nc_type, reason_raw)
        
        # 4. Preparar líneas según el tipo de NC
        invoice_lines_vals = []
        
        if nc_type == 'cancel':
            # Para anulación de factura, copiar todas las líneas del documento original
            if referenced_move:
                for line in referenced_move.invoice_line_ids.filtered(lambda l: not ('Descuento Global' in (l.name or ''))):
                    # Copiar la línea pero sin duplicar relaciones
                    line_vals = {
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'quantity': line.quantity,
                        'price_unit': line.price_unit,
                        'product_uom_id': line.product_uom_id.id,
                        'discount': line.discount or 0.0,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                        'l10n_latam_vat_exempt': line.l10n_latam_vat_exempt,
                    }
                    invoice_lines_vals.append((0, 0, line_vals))
            else:
                # Si no hay documento original, usar los ítems del caso
                for item in self.dte_case_id.item_ids:
                    line_vals = self._prepare_invoice_line_vals_from_dte_item(
                        item, move_vals.get('move_type', 'out_refund')
                    )
                    invoice_lines_vals.append((0, 0, line_vals))
                
        elif nc_type == 'return':
            # Para devolución, usar las líneas del caso (cantidades devueltas)
            if self.dte_case_id.item_ids:
                # Caso con ítems específicos a devolver
                for item in self.dte_case_id.item_ids:
                    # Buscar precio original en documento referenciado
                    price_unit = item.price_unit
                    if not price_unit and referenced_move:
                        # Buscar el mismo producto en el documento original
                        ref_line = referenced_move.invoice_line_ids.filtered(
                            lambda l: l.name and item.name in l.name
                        )
                        if ref_line:
                            price_unit = ref_line[0].price_unit
                    
                    # Crear la línea con datos adecuados
                    line_vals = self._prepare_invoice_line_vals_from_dte_item(
                        item, move_vals.get('move_type', 'out_refund')
                    )
                    # Sobrescribir precio unitario si se encontró
                    if price_unit:
                        line_vals['price_unit'] = price_unit
                        
                    invoice_lines_vals.append((0, 0, line_vals))
            elif referenced_move:
                # No hay ítems específicos, devolver todo
                for line in referenced_move.invoice_line_ids.filtered(lambda l: not ('Descuento Global' in (l.name or ''))):
                    line_vals = {
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'quantity': line.quantity,
                        'price_unit': line.price_unit,
                        'product_uom_id': line.product_uom_id.id,
                        'discount': line.discount or 0.0,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                        'l10n_latam_vat_exempt': line.l10n_latam_vat_exempt,
                    }
                    invoice_lines_vals.append((0, 0, line_vals))
                    
        elif nc_type in ['text_correction', 'amount_correction']:
            # Para correcciones de texto o montos, crear una línea genérica
            # que simplemente indique la corrección
            product = self.env['product.product'].search([
                ('name', '=like', 'Corrección%')
            ], limit=1)
            
            if not product:
                product = self.env['product.product'].create({
                    'name': 'Corrección',
                    'type': 'service',
                    'default_code': 'CORRECCION',
                    'sale_ok': True,
                    'purchase_ok': True,
                })
            
            # Si hay documento original, usar el mismo esquema de impuestos
            tax_ids = []
            if referenced_move:
                tax_line = referenced_move.invoice_line_ids.filtered(lambda l: l.tax_ids)
                if tax_line:
                    tax_ids = [(6, 0, tax_line[0].tax_ids.ids)]
            
            # Crear línea genérica de corrección
            line_vals = {
                'product_id': product.id,
                'name': f"Corrección: {reason_raw or 'Documento'}",
                'quantity': 1,
                'price_unit': 0.0,  # No afecta montos
                'tax_ids': tax_ids,
            }
            invoice_lines_vals.append((0, 0, line_vals))
        
        # Si no se crearon líneas por ninguna regla, crear al menos una línea
        # para que la nota de crédito no quede vacía
        if not invoice_lines_vals:
            # Usar producto genérico
            product = self._get_product_for_document_item('Corrección Documento')
            line_vals = {
                'product_id': product.id,
                'name': f"Corrección: {reason_raw or 'Documento'}",
                'quantity': 1,
                'price_unit': 0.0,
                'tax_ids': [],
            }
            invoice_lines_vals.append((0, 0, line_vals))
        
        # 5. Añadir líneas a los valores del documento
        move_vals['invoice_line_ids'] = invoice_lines_vals
        
        # 6. Crear el documento
        new_move = self.env['account.move'].create(move_vals)
        _logger.info("Documento base creado: %s (ID: %s)", new_move.name, new_move.id)
        
        # 7. Añadir referencias
        self._create_document_references(new_move)
        
        # 8. Copiar datos adicionales del documento original si existe
        if referenced_move and nc_type in ['cancel', 'return']:
            # Copiar campos específicos que puedan ser relevantes
            for field in ['currency_id']:
                if hasattr(referenced_move, field) and hasattr(new_move, field):
                    value = getattr(referenced_move, field)
                    if value:
                        setattr(new_move, field, value)
        
        _logger.info("Nota de Crédito (61) generada exitosamente: %s", new_move.name)
        return new_move
    
    def _generate_document_type_56(self):
        """Genera Nota de Débito Electrónica (56)"""
        _logger.info("Generando Nota de Débito (56) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para notas de débito
        raise NotImplementedError("Generación de Nota de Débito (56) pendiente de implementación")
    
    def _generate_document_type_52(self):
        """Genera Guía de Despacho Electrónica (52)"""
        _logger.info("Generando Guía de Despacho (52) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para guías de despacho
        raise NotImplementedError("Generación de Guía de Despacho (52) pendiente de implementación")
    
    def _generate_document_type_110(self):
        """Genera Factura de Exportación Electrónica (110)"""
        _logger.info("Generando Factura de Exportación (110) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para facturas de exportación
        raise NotImplementedError("Generación de Factura de Exportación (110) pendiente de implementación")
    
    def _generate_document_type_111(self):
        """Genera Nota de Débito de Exportación Electrónica (111)"""
        _logger.info("Generando Nota de Débito de Exportación (111) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para notas de débito de exportación
        raise NotImplementedError("Generación de Nota de Débito de Exportación (111) pendiente de implementación")
    
    def _generate_document_type_112(self):
        """Genera Nota de Crédito de Exportación Electrónica (112)"""
        _logger.info("Generando Nota de Crédito de Exportación (112) para caso %s", self.dte_case_id.case_number_raw)
        # TODO: Implementar lógica específica para notas de crédito de exportación
        raise NotImplementedError("Generación de Nota de Crédito de Exportación (112) pendiente de implementación")

    # === MÉTODOS AUXILIARES COMUNES ===
    # Estos métodos serán utilizados por los generadores específicos
    
    def _prepare_base_move_vals(self):
        """
        Prepara los valores base que son comunes a todos los tipos de documento.
        """
        self.ensure_one()
        dte_case = self.dte_case_id
        partner = self._get_partner_for_document()
        
        # Buscar tipo de documento
        doc_type_model = self.env['l10n_latam.document.type']
        sii_doc_type = doc_type_model.search([
            ('code', '=', dte_case.document_type_code),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if not sii_doc_type:
            raise UserError(_("Tipo de documento SII '%s' no encontrado en Odoo para el caso %s.") % 
                            (dte_case.document_type_code, dte_case.case_number_raw))
        
        # Mapeo de tipos de documento a tipos de movimiento
        move_type_map = {
            '33': 'out_invoice',
            '34': 'out_invoice',
            '56': 'out_refund',
            '61': 'out_refund',
            '52': 'out_invoice',
            '110': 'out_invoice',
            '111': 'out_refund',
            '112': 'out_refund',
        }
        
        # Determinar el tipo de movimiento
        move_type = move_type_map.get(dte_case.document_type_code, 'out_invoice')
        if sii_doc_type.internal_type == 'debit_note':
            move_type = 'out_invoice'  # Las notas de débito son tipo invoice
        elif sii_doc_type.internal_type == 'credit_note':
            move_type = 'out_refund'
            
        # Buscar journal adecuado para ventas con documentos LATAM
        journal = self._get_appropriate_journal()
        
        # Valores básicos para el documento
        move_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'journal_id': journal.id,
            'company_id': self.certification_process_id.company_id.id,
            'l10n_latam_document_type_id': sii_doc_type.id,
            'invoice_date': fields.Date.context_today(self),
            'l10n_cl_edi_certification_id': self.certification_process_id.id,
        }
        
        return move_vals
    
    def _get_appropriate_journal(self):
        """
        Busca el diario más apropiado para el proceso de certificación.
        Prioriza el diario específico de certificación, si existe.
        """
        company = self.certification_process_id.company_id
        
        # 1. Buscar primero un diario específico de certificación
        certification_journal = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('name', '=like', '%Certificación SII%'),
            ('type', '=', 'sale'),
            ('l10n_latam_use_documents', '=', True),
        ], limit=1)
        
        if certification_journal:
            return certification_journal
            
        # 2. Si no hay diario de certificación, buscar cualquier diario de ventas con documentos
        journal = self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'sale'),
            ('l10n_latam_use_documents', '=', True),
        ], limit=1)
        
        # 3. Si aún no hay diario con documentos, buscar cualquier diario de ventas
        # y activar documentos LATAM temporalmente
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', company.id),
                ('type', '=', 'sale'),
            ], limit=1)
            
            if journal:
                _logger.info(
                    "Configurando temporalmente el diario '%s' para usar documentos LATAM durante certificación",
                    journal.name
                )
                # Activar documentos LATAM
                journal.write({
                    'l10n_latam_use_documents': True,
                    'l10n_cl_point_of_sale_type': 'online',
                })
        
        # 4. Si aún no hay diario, error informativo
        if not journal:
            # Sugerir crear un diario desde preparación de certificación
            raise UserError(_(
                "No se encontró ningún diario de ventas en la compañía %s.\n"
                "Vuelva a la pantalla principal de certificación y ejecute la acción 'Preparar Certificación' "
                "para configurar automáticamente un diario."
            ) % company.name)
        
        return journal
    
    def _get_product_for_document_item(self, item_name):
        """
        Obtiene o crea un producto para la línea del documento.
        Para certificación, usamos productos específicos o genéricos según sea necesario.
        """
        self.ensure_one()
        product_model = self.env['product.product']
        company = self.certification_process_id.company_id
        
        # Crear código único para productos de certificación basado en el nombre
        # Esto permite búsquedas posteriores más efectivas
        safe_name = item_name.replace(' ', '_').replace('&', 'and').upper()
        default_code = f"CERT_{safe_name[:30]}_{company.id}"
        
        # Buscar producto existente primero por código
        product = product_model.search([
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
            '|', ('default_code', '=', default_code),
            ('name', '=ilike', item_name)
        ], limit=1)
        
        if not product:
            # Si no existe, crear un producto específico para este ítem
            vals = {
                'name': item_name,
                'default_code': default_code,
                'type': 'consu',  # producto consumible para simplificar
                'categ_id': self.env.ref('product.product_category_all').id,
                'company_id': company.id,
                'standard_price': 0.0,
                'list_price': 0.0,
                'sale_ok': True,
                'purchase_ok': True,
            }
            product = product_model.create(vals)
            _logger.info("Creado producto para certificación: %s [%s]", product.name, product.default_code)
        
        return product
        
    def _prepare_invoice_line_vals_from_dte_item(self, dte_item, move_type):
        """
        Prepara los valores para una línea de factura a partir de un ítem del caso DTE.
        """
        self.ensure_one()
        company = self.certification_process_id.company_id
        
        # Obtener el producto adecuado
        product = self._get_product_for_document_item(dte_item.name)
        
        # Determinar precio unitario (puede ser negativo en notas de crédito)
        price_unit = dte_item.price_unit
        
        # Crear valores base para la línea
        line_vals = {
            'product_id': product.id,
            'name': dte_item.name,
            'quantity': dte_item.quantity,
            'price_unit': price_unit,
            'product_uom_id': product.uom_id.id,
            'discount': dte_item.discount_percent or 0.0,
        }
        
        # Determinar impuestos según si es exento o no
        if dte_item.is_exempt:
            line_vals['tax_ids'] = [(6, 0, [])]
            line_vals['l10n_latam_vat_exempt'] = True
        else:
            # Buscar impuesto IVA chileno al 19%
            iva_tax = self.env['account.tax'].search([
                ('company_id', '=', company.id),
                ('type_tax_use', '=', 'sale'),
                ('l10n_cl_sii_code', '=', 14),  # 14 es el código SII para IVA
                ('amount', '=', 19),
            ], limit=1)
            
            if not iva_tax:
                # Búsqueda alternativa si no se encuentra por código SII
                iva_tax = self.env['account.tax'].search([
                    ('company_id', '=', company.id),
                    ('type_tax_use', '=', 'sale'),
                    ('amount_type', '=', 'percent'),
                    ('amount', '=', 19),
                ], limit=1)
                
            if iva_tax:
                line_vals['tax_ids'] = [(6, 0, [iva_tax.id])]
            else:
                _logger.warning(
                    "No se encontró impuesto IVA al 19%% para ventas en Chile. "
                    "Línea '%s' sin impuesto.", dte_item.name
                )
        
        return line_vals
    
    def _get_partner_for_document(self):
        """
        Obtiene el partner que se utilizará para el documento.
        Para certificación SII, se debe usar un partner con RUT del SII.
        """
        self.ensure_one()
        
        # Buscar si ya existe un partner con el RUT del SII (60.803.000-K)
        partner = self.env['res.partner'].search([
            ('vat', '=', '60803000-K'),
            '|', ('company_id', '=', self.certification_process_id.company_id.id),
            ('company_id', '=', False)
        ], limit=1)
        
        # Si no existe, crear un partner específico para certificación
        if not partner:
            # Buscar el tipo de identificación RUT
            rut_identification_type = self.env['l10n_latam.identification.type'].search([
                ('name', '=', 'RUT'),
                ('country_id.code', '=', 'CL')
            ], limit=1)
            
            if not rut_identification_type:
                # Fallback: buscar por cualquier criterio que contenga RUT
                rut_identification_type = self.env['l10n_latam.identification.type'].search([
                    ('name', 'ilike', 'RUT'),
                    ('country_id.code', '=', 'CL')
                ], limit=1)
            
            partner_vals = {
                'name': 'SII - Servicio de Impuestos Internos (Certificación)',
                'vat': '60803000-K',
                'country_id': self.env.ref('base.cl').id,
                'company_type': 'company',
                'industry_id': self.env.ref('l10n_cl.res_partner_activity_SII_844101_companies').id,
                'l10n_cl_activity_description': 'Servicio de Impuestos Internos',
                'company_id': self.certification_process_id.company_id.id,
            }
            
            # Agregar tipo de identificación si se encontró
            if rut_identification_type:
                partner_vals['l10n_latam_identification_type_id'] = rut_identification_type.id
            else:
                _logger.warning("No se encontró el tipo de identificación RUT para Chile. El partner se creará sin este campo.")
            
            partner = self.env['res.partner'].create(partner_vals)
            _logger.info("Creado partner SII para certificación: %s", partner.name)
        
        return partner
    
    def _apply_global_discount(self, move, discount_percent):
        """
        Aplica un descuento global al documento usando el producto de descuento específico.
        En Chile, los descuentos globales se implementan como líneas negativas.
        
        Args:
            move: Documento account.move al que aplicar el descuento
            discount_percent: Porcentaje de descuento a aplicar
        
        Returns:
            El documento modificado
        """
        self.ensure_one()
        
        # Solo aplicar si hay un descuento definido
        if not move or not discount_percent or discount_percent <= 0:
            return move
        
        # Solo aplicar a líneas afectas (no exentas)
        affected_lines = move.invoice_line_ids.filtered(
            lambda l: l.tax_ids and not l.l10n_latam_vat_exempt
        )
        
        if not affected_lines:
            _logger.warning("No se pudo aplicar descuento global de %s%% al documento %s: no hay líneas afectas", 
                          discount_percent, move.name)
            return move
        
        # Calcular el monto total de los ítems afectos
        total_affected = sum(line.price_subtotal for line in affected_lines)
        
        # Calcular el monto del descuento
        discount_amount = total_affected * (discount_percent / 100.0)
        
        if discount_amount <= 0:
            return move
        
        # Buscar producto de descuento (ID 136 según información proporcionada)
        discount_product = self.env['product.product'].browse(136)
        if not discount_product.exists():
            # Búsqueda alternativa si no existe el ID específico
            discount_product = self.env['product.product'].search([
                ('name', '=like', 'Descuento%')
            ], limit=1)
            
            if not discount_product:
                # Si no existe, crear un producto de descuento
                discount_product = self.env['product.product'].create({
                    'name': 'Descuento Global',
                    'type': 'service',
                    'default_code': 'DESCUENTO',
                    'invoice_policy': 'order',
                    'sale_ok': True,
                    'purchase_ok': True,
                })
        
        # Obtener la cuenta contable para descuentos (usar la misma que los productos afectos)
        account_id = affected_lines[0].account_id.id if affected_lines else False
        
        # Obtener los impuestos de las líneas afectas
        # El descuento debe llevar los mismos impuestos que los productos afectos
        taxes = affected_lines[0].tax_ids if affected_lines and affected_lines[0].tax_ids else []
        
        # Crear línea de factura para el descuento
        discount_line_vals = {
            'move_id': move.id,
            'product_id': discount_product.id,
            'name': f'Descuento Global {discount_percent}%',
            'price_unit': -discount_amount,  # Monto negativo para descuento
            'quantity': 1.0,
            'account_id': account_id,
            'tax_ids': [(6, 0, taxes.ids)],
        }
        
        # Crear la línea directamente
        discount_line = self.env['account.move.line'].create(discount_line_vals)
        
        # Actualizar totales del documento
        move._recompute_dynamic_lines()
        
        return move
    
    def _create_document_references(self, move):
        """
        Crea las referencias para el documento.
        Para certificación SII, siempre debe existir la referencia al SET y CASO.
        """
        self.ensure_one()
        dte_case = self.dte_case_id
        references_to_create = []
        
        # 1. Agregar la referencia obligatoria al SET primero
        set_doc_type = self.env['l10n_latam.document.type'].search([
            ('code', '=', 'SET'),
            ('country_id.code', '=', 'CL')
        ], limit=1)
        
        if set_doc_type:
            references_to_create.append({
                'move_id': move.id,
                'l10n_cl_reference_doc_type_id': set_doc_type.id,
                'origin_doc_number': '',
                'reason': f'CASO {dte_case.case_number_raw}'
            })
        else:
            raise UserError(_("No se encontró el tipo de documento SET para referencias. "
                             "Ejecute primero la acción 'Preparar Certificación'."))
        
        # 2. Agregar referencias adicionales si existen
        if dte_case.reference_ids:
            for ref in dte_case.reference_ids:
                # Buscar documento referenciado si existe
                referenced_move = False
                if ref.referenced_sii_case_number:
                    referenced_dte_case = self.env['l10n_cl_edi.certification.case.dte'].search([
                        ('parsed_set_id.certification_process_id', '=', self.certification_process_id.id),
                        ('case_number_raw', '=', ref.referenced_sii_case_number),
                        ('generated_account_move_id', '!=', False)
                    ], limit=1)
                    
                    if referenced_dte_case:
                        referenced_move = referenced_dte_case.generated_account_move_id
                
                # Si hay tipo de documento referenciado, añadir la referencia
                if referenced_move:
                    reference_values = {
                        'move_id': move.id,
                        'l10n_cl_reference_doc_type_id': referenced_move.l10n_latam_document_type_id.id,
                        'origin_doc_number': referenced_move.l10n_latam_document_number,
                        'reference_doc_code': ref.reference_code,
                        'reason': ref.reason_raw or 'Referencia SII'
                    }
                    references_to_create.append(reference_values)
                else:
                    # Referencia sin documento generado aún
                    _logger.warning(
                        "No se encontró documento generado para caso referenciado %s. "
                        "La referencia se agregará sin número de documento.", 
                        ref.referenced_sii_case_number
                    )
                    # Buscar el tipo de documento basado en la descripción textual
                    ref_text = ref.reference_document_text_raw or ''
                    ref_doc_type = False
                    
                    if 'FACTURA' in ref_text.upper():
                        ref_doc_type = self.env['l10n_latam.document.type'].search([
                            ('code', '=', '33'),
                            ('country_id.code', '=', 'CL')
                        ], limit=1)
                    elif 'NOTA DE CREDITO' in ref_text.upper():
                        ref_doc_type = self.env['l10n_latam.document.type'].search([
                            ('code', '=', '61'),
                            ('country_id.code', '=', 'CL')
                        ], limit=1)
                    
                    if ref_doc_type:
                        reference_values = {
                            'move_id': move.id,
                            'l10n_cl_reference_doc_type_id': ref_doc_type.id,
                            'origin_doc_number': f"REF-{ref.referenced_sii_case_number or ''}",
                            'reference_doc_code': ref.reference_code,
                            'reason': ref.reason_raw or 'Referencia SII'
                        }
                        references_to_create.append(reference_values)
        
        # Crear todas las referencias
        if references_to_create:
            references = self.env['l10n_cl.account.invoice.reference'].create(references_to_create)
            return references
        return False