from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from lxml import etree
from datetime import datetime
import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)

class CertificationBatchFile(models.Model):
    _name = 'l10n_cl_edi.certification.batch_file'
    _description = 'Archivo de Envío Consolidado SII'
    _order = 'create_date desc'
    
    certification_id = fields.Many2one(
        'l10n_cl_edi.certification.process',
        string='Proceso de Certificación',
        required=True,
        ondelete='cascade'
    )
    
    name = fields.Char(
        string='Nombre',
        required=True,
        help='Nombre descriptivo del archivo consolidado'
    )
    
    set_type = fields.Selection([
        ('basico', 'SET BÁSICO'),
        ('guias', 'SET GUÍAS DE DESPACHO'),
        ('ventas', 'LIBRO DE VENTAS (IEV)'),
        ('compras', 'LIBRO DE COMPRAS (IEC)'),
        ('libro_guias', 'LIBRO DE GUÍAS'),
        ('exportacion1', 'SET EXPORTACIÓN 1'),
        ('exportacion2', 'SET EXPORTACIÓN 2'),
    ], string='Tipo de Set', required=True)
    
    xml_content = fields.Text(
        string='Contenido XML',
        help='Contenido XML del archivo consolidado'
    )
    
    file_data = fields.Binary(
        string='Archivo XML',
        attachment=True,
        help='Archivo XML codificado en base64'
    )
    
    filename = fields.Char(
        string='Nombre del Archivo',
        help='Nombre del archivo XML para descarga'
    )
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('downloaded', 'Descargado'),
        ('error', 'Error')
    ], string='Estado', default='draft')
    
    document_count = fields.Integer(
        string='Cantidad de Documentos',
        help='Número de DTEs incluidos en el envío consolidado'
    )
    
    error_message = fields.Text(
        string='Mensaje de Error',
        help='Detalle del error si la generación falló'
    )
    
    generation_date = fields.Datetime(
        string='Fecha de Generación',
        default=fields.Datetime.now
    )
    
    def action_download_file(self):
        """Acción para descargar el archivo XML consolidado"""
        self.ensure_one()
        
        if not self.file_data:
            raise UserError(_('No hay archivo disponible para descargar.'))
        
        # Marcar como descargado
        self.state = 'downloaded'
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&download=true&filename={self.filename}',
            'target': 'self',
        }
    
    def action_regenerate(self):
        """Regenerar el archivo consolidado"""
        self.ensure_one()
        
        # Llamar al método de generación correspondiente en el proceso de certificación
        generation_method = getattr(self.certification_id, f'action_generate_batch_{self.set_type}', None)
        if generation_method:
            return generation_method()
        else:
            raise UserError(_('Método de generación no encontrado para el tipo de set: %s') % self.set_type)
    
    @api.model
    def create(self, vals):
        """Override create para generar nombre del archivo automáticamente"""
        if not vals.get('filename') and vals.get('set_type'):
            company = self.env['l10n_cl_edi.certification.process'].browse(vals.get('certification_id')).company_id
            rut = company.vat.replace('-', '').replace('.', '') if company.vat else 'UNKNOWN'
            set_type_upper = vals['set_type'].upper()
            vals['filename'] = f"{set_type_upper}_{rut}.xml"
        
        return super().create(vals)

    # ==================== MÉTODOS DE GENERACIÓN BATCH ====================

    @api.model
    def generate_batch_basico(self, certification_process_id):
        """Generar SET BÁSICO - Facturas y notas de crédito"""
        return self._generate_batch_file(certification_process_id, 'basico', 'SET BÁSICO')

    @api.model
    def generate_batch_guias(self, certification_process_id):
        """Generar SET GUÍAS DE DESPACHO"""
        return self._generate_batch_file(certification_process_id, 'guias', 'SET GUÍAS DE DESPACHO')

    @api.model
    def generate_batch_ventas(self, certification_process_id):
        """Generar LIBRO DE VENTAS (IEV)"""
        return self._generate_batch_file(certification_process_id, 'ventas', 'LIBRO DE VENTAS (IEV)')

    @api.model
    def generate_batch_compras(self, certification_process_id):
        """Generar LIBRO DE COMPRAS (IEC)"""
        return self._generate_batch_file(certification_process_id, 'compras', 'LIBRO DE COMPRAS (IEC)')

    @api.model
    def generate_batch_libro_guias(self, certification_process_id):
        """Generar LIBRO DE GUÍAS"""
        return self._generate_batch_file(certification_process_id, 'libro_guias', 'LIBRO DE GUÍAS')

    @api.model
    def generate_batch_exportacion1(self, certification_process_id):
        """Generar SET EXPORTACIÓN 1"""
        return self._generate_batch_file(certification_process_id, 'exportacion1', 'SET EXPORTACIÓN 1')

    @api.model
    def generate_batch_exportacion2(self, certification_process_id):
        """Generar SET EXPORTACIÓN 2"""
        return self._generate_batch_file(certification_process_id, 'exportacion2', 'SET EXPORTACIÓN 2')

    def _generate_batch_file(self, certification_process_id, set_type, name):
        """Motor principal de generación de archivos consolidados"""
        _logger.info(f"=== INICIANDO GENERACIÓN BATCH {set_type.upper()} ===")
        
        # Obtener proceso de certificación
        process = self.env['l10n_cl_edi.certification.process'].browse(certification_process_id)
        if not process.exists():
            raise UserError(_('Proceso de certificación no encontrado'))

        try:
            # 1. Validar prerequisitos
            self._validate_ready_for_batch_generation(process, set_type)
            
            # 2. Regenerar documentos del set con nuevos folios
            regenerated_documents = self._regenerate_test_documents(process, set_type)
            
            # 3. Extraer nodos DTE de los XMLs individuales
            dte_nodes = self._extract_dte_nodes(regenerated_documents)
            
            # 4. Construir XML consolidado
            consolidated_xml = self._build_consolidated_setdte(process, dte_nodes, set_type)
            
            # 5. Crear archivo batch
            batch_file = self.create({
                'certification_id': certification_process_id,
                'name': name,
                'set_type': set_type,
                'xml_content': consolidated_xml,
                'file_data': base64.b64encode(consolidated_xml.encode('utf-8')),
                'document_count': len(dte_nodes),
                'state': 'generated'
            })
            
            _logger.info(f"Archivo batch {set_type} generado exitosamente con {len(dte_nodes)} documentos")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Archivo Consolidado Generado'),
                    'message': _('Se generó exitosamente %s con %d documentos') % (name, len(dte_nodes)),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error generando archivo batch {set_type}: {str(e)}")
            
            # Crear registro de error
            self.create({
                'certification_id': certification_process_id,
                'name': f"{name} (Error)",
                'set_type': set_type,
                'state': 'error',
                'error_message': str(e)
            })
            
            raise UserError(_('Error generando archivo consolidado: %s') % str(e))

    def _validate_ready_for_batch_generation(self, process, set_type):
        """Validar que todos los documentos estén listos para consolidación"""
        _logger.info(f"Validando prerequisitos para set {set_type}")
        
        # 1. Verificar que existan casos DTE para el tipo de set
        relevant_cases = self._get_relevant_cases_for_set_type(process, set_type)
        if not relevant_cases:
            raise UserError(_('No se encontraron casos DTE para el tipo de set: %s') % set_type)
        
        # 2. Verificar que todos los documentos fueron generados
        missing_cases = relevant_cases.filtered(lambda c: c.generation_status == 'pending')
        if missing_cases:
            case_numbers = ', '.join(missing_cases.mapped('case_number_raw'))
            raise UserError(_('Faltan por generar documentos del set: %s') % case_numbers)
        
        # 3. Verificar estado SII (opcional - con warning)
        rejected_docs = relevant_cases.filtered(lambda c: c.generated_account_move_id and 
                                               c.generated_account_move_id.l10n_cl_dte_status == 'rejected')
        if rejected_docs:
            case_numbers = ', '.join(rejected_docs.mapped('case_number_raw'))
            # Por ahora solo log warning, no bloquear
            _logger.warning(f"Documentos rechazados encontrados: {case_numbers}")

    def _get_relevant_cases_for_set_type(self, process, set_type):
        """Obtener casos DTE relevantes según el tipo de set"""
        all_cases = self.env['l10n_cl_edi.certification.case.dte'].search([
            ('parsed_set_id.certification_process_id', '=', process.id)
        ])
        
        # Mapeo de tipos de set a tipos de documento
        set_type_mappings = {
            'basico': ['33', '34', '56', '61'],  # Facturas, facturas exentas, notas débito, notas crédito
            'guias': ['52'],  # Guías de despacho
            'ventas': ['33', '34', '56', '61'],  # Para libro de ventas
            'compras': ['33', '34', '56', '61'],  # Para libro de compras (simulado)
            'libro_guias': ['52'],  # Para libro de guías
            'exportacion1': ['110'],  # Facturas de exportación
            'exportacion2': ['111', '112'],  # Notas de exportación
        }
        
        relevant_doc_types = set_type_mappings.get(set_type, [])
        if not relevant_doc_types:
            return all_cases  # Si no hay mapeo específico, incluir todos
        
        return all_cases.filtered(lambda c: c.document_type_code in relevant_doc_types)

    def _regenerate_test_documents(self, process, set_type):
        """Regenerar documentos del set con nuevos folios CAF"""
        _logger.info(f"Regenerando documentos para set {set_type}")
        
        relevant_cases = self._get_relevant_cases_for_set_type(process, set_type)
        regenerated_documents = []
        
        for case in relevant_cases:
            try:
                # Utilizar el generador de documentos existente
                generator = self.env['l10n_cl_edi.certification.document.generator'].create({
                    'dte_case_id': case.id,
                    'certification_process_id': process.id
                })
                
                # Regenerar documento
                result = generator.generate_document()
                
                # Obtener el documento generado/actualizado
                if case.generated_account_move_id:
                    document = case.generated_account_move_id
                    
                    # Asegurar que el documento esté confirmado
                    if document.state == 'draft':
                        document.action_post()
                    
                    # Verificar que tenga XML DTE
                    if document.l10n_cl_dte_file:
                        regenerated_documents.append(document)
                        _logger.info(f"Documento regenerado para caso {case.case_number_raw}")
                    else:
                        _logger.warning(f"Documento sin XML DTE para caso {case.case_number_raw}")
                
            except Exception as e:
                _logger.error(f"Error regenerando documento para caso {case.case_number_raw}: {str(e)}")
                continue
        
        if not regenerated_documents:
            raise UserError(_('No se pudieron regenerar documentos para el set %s') % set_type)
        
        return regenerated_documents

    def _extract_dte_nodes(self, documents):
        """Extraer nodos DTE de los XMLs individuales usando lxml"""
        _logger.info(f"Extrayendo nodos DTE de {len(documents)} documentos")
        
        dte_nodes = []
        
        for document in documents:
            try:
                if not document.l10n_cl_dte_file:
                    _logger.warning(f"Documento {document.name} sin archivo DTE")
                    continue
                
                # Decodificar XML
                xml_data = base64.b64decode(document.l10n_cl_dte_file).decode('ISO-8859-1')
                
                # Parsear con lxml
                root = etree.fromstring(xml_data.encode('ISO-8859-1'))
                
                # Buscar nodo DTE (con namespace)
                namespaces = {'sii': 'http://www.sii.cl/SiiDte'}
                dte_node = root.find('.//sii:DTE', namespaces)
                
                if dte_node is not None:
                    dte_nodes.append(dte_node)
                    _logger.info(f"DTE extraído de documento {document.name}")
                else:
                    _logger.warning(f"No se encontró nodo DTE en documento {document.name}")
                    
            except Exception as e:
                _logger.error(f"Error extrayendo DTE de documento {document.name}: {str(e)}")
                continue
        
        if not dte_nodes:
            raise UserError(_('No se pudieron extraer nodos DTE de los documentos'))
        
        return dte_nodes

    def _build_consolidated_setdte(self, process, dte_nodes, set_type):
        """Construir XML consolidado con carátula y múltiples DTEs"""
        _logger.info(f"Construyendo XML consolidado para {len(dte_nodes)} DTEs")
        
        # Crear estructura base del EnvioDTE
        envio_root = etree.Element('EnvioDTE')
        envio_root.set('xmlns', 'http://www.sii.cl/SiiDte')
        envio_root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        envio_root.set('xsi:schemaLocation', 'http://www.sii.cl/SiiDte EnvioDTE_v10.xsd')
        envio_root.set('version', '1.0')
        
        # Crear SetDTE
        set_dte = etree.SubElement(envio_root, 'SetDTE')
        set_dte.set('ID', 'SetDoc')
        
        # Crear carátula consolidada
        caratula = self._build_consolidated_caratula(process, dte_nodes, set_type)
        set_dte.append(caratula)
        
        # Agregar todos los nodos DTE
        for dte_node in dte_nodes:
            set_dte.append(dte_node)
        
        # Convertir a string con encoding correcto
        xml_string = etree.tostring(envio_root, encoding='ISO-8859-1', xml_declaration=True, pretty_print=True)
        
        return xml_string.decode('ISO-8859-1')

    def _build_consolidated_caratula(self, process, dte_nodes, set_type):
        """Generar carátula consolidada con SubTotDTE"""
        caratula = etree.Element('Caratula')
        caratula.set('version', '1.0')
        
        company = process.company_id
        
        # RutEmisor
        rut_emisor = etree.SubElement(caratula, 'RutEmisor')
        rut_emisor.text = company.vat or '11111111-1'
        
        # RutEnvia (mismo que emisor por ahora)
        rut_envia = etree.SubElement(caratula, 'RutEnvia')
        rut_envia.text = company.vat or '11111111-1'
        
        # RutReceptor (siempre SII)
        rut_receptor = etree.SubElement(caratula, 'RutReceptor')
        rut_receptor.text = '60803000-K'
        
        # FchResol y NroResol (datos de certificación)
        if company.l10n_cl_dte_resolution_date:
            fch_resol = etree.SubElement(caratula, 'FchResol')
            fch_resol.text = company.l10n_cl_dte_resolution_date.strftime('%Y-%m-%d')
        
        if company.l10n_cl_dte_resolution_number:
            nro_resol = etree.SubElement(caratula, 'NroResol')
            nro_resol.text = str(company.l10n_cl_dte_resolution_number)
        
        # TmstFirmaEnv
        tmst_firma = etree.SubElement(caratula, 'TmstFirmaEnv')
        tmst_firma.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        # Contar documentos por tipo para SubTotDTE
        doc_counts = {}
        for dte_node in dte_nodes:
            # Extraer tipo de documento del DTE
            doc_encabezado = dte_node.find('.//{http://www.sii.cl/SiiDte}Encabezado')
            if doc_encabezado is not None:
                id_doc = doc_encabezado.find('.//{http://www.sii.cl/SiiDte}IdDoc')
                if id_doc is not None:
                    tipo_dte = id_doc.find('.//{http://www.sii.cl/SiiDte}TipoDTE')
                    if tipo_dte is not None:
                        doc_type = tipo_dte.text
                        doc_counts[doc_type] = doc_counts.get(doc_type, 0) + 1
        
        # Agregar SubTotDTE para cada tipo
        for doc_type, count in doc_counts.items():
            subtot_dte = etree.SubElement(caratula, 'SubTotDTE')
            
            tipo_dte_elem = etree.SubElement(subtot_dte, 'TipoDTE')
            tipo_dte_elem.text = doc_type
            
            nro_doc_elem = etree.SubElement(subtot_dte, 'NroDTE')
            nro_doc_elem.text = str(count)
        
        return caratula