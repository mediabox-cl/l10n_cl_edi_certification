# -*- coding: utf-8 -*-

import re
from typing import Dict, List, Optional, Any, Tuple

class SiiTestSetParser:
    """
    Parser para archivos de Set de Pruebas del SII.
    
    Este parser extrae la información de los sets de prueba del SII
    desde los archivos de texto proporcionados por el organismo.
    """
    
    # Patrones de expresiones regulares para identificar secciones y datos
    SET_HEADER_PATTERN = r'SET\s+([A-ZÁ-Úa-zá-ú\s]+)\s*-\s*NUMERO\s+DE\s+(?:ATENCION|ATENCIÓN):\s*(\d+)'
    CASE_HEADER_PATTERN = r'^CASO\s+(\d+-\d+)'
    DOCUMENT_TYPE_PATTERN = r'DOCUMENTO\s+(.+)'
    REFERENCE_PATTERN = r'REFERENCIA\s+(.+)'
    REFERENCE_REASON_PATTERN = r'RAZON REFERENCIA\s+(.+)'
    ITEM_HEADER_PATTERN = r'ITEM\s+(?:CANTIDAD|VALOR\s+UNITARIO|PRECIO\s+UNITARIO|TOTAL\s+LINEA)?'
    MOTIVO_PATTERN = r'MOTIVO:\s+(.+)'
    TRASLADO_PATTERN = r'TRASLADO POR:\s+(.+)'
    
    def __init__(self, file_content: str):
        """
        Inicializa el parser con el contenido del archivo.
        
        Args:
            file_content: Contenido completo del archivo de texto del set de pruebas.
        """
        self.content = file_content
        
    def parse(self) -> Dict[str, Any]:
        """
        Procesa el contenido completo del archivo.
        
        Returns:
            Dict con los datos extraídos, incluyendo sets y casos.
        """
        # Extraer cada conjunto de pruebas
        result = {
            'sets': [],
            'cases': []
        }
        
        # Encontrar todos los sets de prueba
        set_matches = re.finditer(self.SET_HEADER_PATTERN, self.content)
        for set_match in set_matches:
            set_type = set_match.group(1).strip()
            attention_number = set_match.group(2).strip()
            
            # Obtener el texto desde el encabezado hasta el próximo separador o el final
            start_pos = set_match.start()
            next_separator = self.content.find('-'*10, start_pos + 1)
            if next_separator == -1:
                next_separator = len(self.content)
            
            set_content = self.content[start_pos:next_separator]
            
            # Extraer los casos del set
            set_cases = self._extract_cases(set_content, set_type, attention_number)
            
            # Crear el set
            set_data = {
                'set_type': self._normalize_set_type(set_type),
                'attention_number': attention_number,
                'cases': set_cases
            }
            
            result['sets'].append(set_data)
            result['cases'].extend(set_cases)
            
        # Establecer referencias entre documentos
        self._resolve_references(result['cases'])
        
        return result
    
    def _extract_cases(self, set_content: str, set_type: str, attention_number: str) -> List[Dict[str, Any]]:
        """
        Extrae los casos de prueba de un set.
        Utiliza los encabezados de CASO para delimitar el contenido de cada caso.
        """
        cases = []
        
        # Encontrar todos los inicios y números de caso
        matches = list(re.finditer(self.CASE_HEADER_PATTERN, set_content, re.MULTILINE))
        
        for i, current_match in enumerate(matches):
            case_number = current_match.group(1).strip()
            start_pos = current_match.start()
            
            # Determinar el final del contenido de este caso
            # Es el inicio del siguiente caso, o el final del set_content si este es el último caso
            if i + 1 < len(matches):
                end_pos = matches[i+1].start()
            else:
                end_pos = len(set_content)
            
            case_content_block = set_content[start_pos:end_pos]
            
            # Procesar el caso con su bloque de contenido completo
            case_data = self._process_case(case_content_block, case_number, set_type, attention_number)
            if case_data:
                cases.append(case_data)
        
        return cases
    
    def _process_case(self, case_content: str, case_number: str, set_type: str, attention_number: str) -> Dict[str, Any]:
        """
        Procesa un caso de prueba individual a partir de su bloque de contenido.
        """
        lines = case_content.split('\n')
        
        case_data = {
            'case_number': case_number,
            'set_type': self._normalize_set_type(set_type),
            'set_attention_number': attention_number,
            'document_type': None,
            'reference_document': None,
            'referenced_case_number': None,
            'reference_reason': None,
            'motivo': None,
            'traslado_por': None,
            'items': [],
            'additional_info': {}
        }
        
        in_items_section = False
        item_header_text = ""
        has_uom_column = False

        # Primera pasada para encontrar la cabecera de items y determinar si hay UoM
        temp_item_header_found = False
        for line_idx, line_content in enumerate(lines):
            if not temp_item_header_found and 'ITEM' in line_content and \
               ('CANTIDAD' in line_content or 'PRECIO UNITARIO' in line_content or \
                'VALOR UNITARIO' in line_content or 'UNIDAD MEDIDA' in line_content):
                item_header_text = line_content
                if 'UNIDAD MEDIDA' in item_header_text:
                    has_uom_column = True
                temp_item_header_found = True

        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue

            if re.match(self.CASE_HEADER_PATTERN, line_strip):
                continue

            doc_match = re.search(self.DOCUMENT_TYPE_PATTERN, line)
            if doc_match:
                document_type_text = doc_match.group(1).strip()
                if not case_data.get('document_type'):
                    case_data['document_type'] = self._normalize_document_type(document_type_text)
                continue
            
            # Check for RAZON REFERENCIA FIRST to avoid conflict with REFERENCE_PATTERN
            reason_match = re.search(self.REFERENCE_REASON_PATTERN, line)
            if reason_match:
                case_data['reference_reason'] = reason_match.group(1).strip()
                continue
            
            # Then check for REFERENCIA
            ref_match = re.search(self.REFERENCE_PATTERN, line)
            if ref_match:
                reference_text = ref_match.group(1).strip()
                case_data['reference_document'] = reference_text
                referenced_case_num_match = re.search(r'CASO\s+(\d+-\d+)', reference_text)
                if referenced_case_num_match:
                    case_data['referenced_case_number'] = referenced_case_num_match.group(1).strip()
                continue
            
            motivo_match = re.search(self.MOTIVO_PATTERN, line)
            if motivo_match:
                case_data['motivo'] = motivo_match.group(1).strip()
                continue
            
            traslado_match = re.search(self.TRASLADO_PATTERN, line)
            if traslado_match:
                case_data['traslado_por'] = traslado_match.group(1).strip()
                continue
            
            if not in_items_section and item_header_text and line.strip() == item_header_text.strip():
                in_items_section = True
                continue
            
            if in_items_section and line_strip and not line_strip.startswith('=') and not 'DESCUENTO GLOBAL' in line_strip:
                item = self._parse_item_line(line_strip, has_uom_column, item_header_text)
                if item:
                    case_data['items'].append(item)
            
            if 'DESCUENTO GLOBAL' in line:
                discount_match = re.search(r'(\d+)%\s*$', line)
                if discount_match:
                    case_data['global_discount'] = float(discount_match.group(1))

        return case_data
    
    def _parse_item_line(self, line: str, has_uom_column: bool, item_header_text: str) -> Optional[Dict[str, Any]]:
        """
        Parsea una línea de ítem.
        
        Args:
            line: Línea con datos del ítem.
            has_uom_column: Flag para indicar si la línea contiene una columna de UoM.
            item_header_text: Texto de la cabecera de la sección de ítems.
            
        Returns:
            Diccionario con los datos del ítem o None si no se pudo parsear.
        """
        if not line.strip() or line.startswith('=') or line.startswith('-'):
            return None
        
        line_copy = line.strip()
        
        discount_percent = None
        discount_match = re.search(r'(\d+)%\s*$', line_copy)
        if discount_match:
            discount_percent = float(discount_match.group(1))
            line_copy = line_copy[:discount_match.start()].strip()
        
        numbers = re.findall(r'\b(\d+(?:.\d+)?)\b', line_copy)
        
        item = {
            'is_exempt': 'EXENTO' in line_copy.upper() or 'EXENTA' in line_copy.upper()
        }
        if has_uom_column:
            item['uom'] = None

        if discount_percent is not None:
            item['discount_percent'] = discount_percent
        
        parts = re.split(r'\s{2,}', line_copy)
        
        if parts:
            item['name'] = parts[0].strip()
            
            if 'VALOR UNITARIO' in item_header_text and not 'CANTIDAD' in item_header_text:
                if numbers:
                    price_str = numbers[-1]
                    item['price_unit'] = float(price_str)
                    idx_price_val = line_copy.rfind(price_str)
                    text_before_price = line_copy[:idx_price_val].strip() if idx_price_val != -1 else ""
                    
                    if has_uom_column and text_before_price:
                        name_uom_parts = text_before_price.split()
                        if len(name_uom_parts) > 1:
                            uom_candidate = name_uom_parts[-1]
                            # Check if uom_candidate is non-numeric and plausible (e.g., not overly long)
                            if not uom_candidate.replace('.', '', 1).isdigit() and len(uom_candidate) < 15: # Heuristic
                                item['uom'] = uom_candidate
                                item['name'] = " ".join(name_uom_parts[:-1])
                            else:
                                item['name'] = text_before_price # UoM candidate not plausible
                        else:
                            item['name'] = text_before_price # Only one word, assume name
                    else:
                        item['name'] = text_before_price

            elif 'CANTIDAD' in item_header_text and not ('PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text):
                if numbers:
                    qty_str = numbers[-1]
                    item['quantity'] = float(qty_str)
                    idx_qty_val = line_copy.rfind(qty_str)

                    if has_uom_column and idx_qty_val != -1:
                        uom_candidate = line_copy[idx_qty_val + len(qty_str):].strip()
                        if uom_candidate and not uom_candidate.replace('.', '', 1).isdigit():
                            item['uom'] = uom_candidate
                    
                    if idx_qty_val != -1:
                        item['name'] = line_copy[:idx_qty_val].strip()
                    elif numbers: # Fallback name logic if idx_qty_val failed (e.g. name is just numbers[0])
                         item['name'] = line_copy[:line_copy.rfind(numbers[0])].strip()
                    else: # Should not happen if numbers were found
                         item['name'] = line_copy 
            
            elif len(numbers) >= 2 and ('PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text) and 'CANTIDAD' in item_header_text:
                qty_str = numbers[-2]
                price_str = numbers[-1]
                item['quantity'] = float(qty_str)
                item['price_unit'] = float(price_str)
                
                idx_price_val = line_copy.rfind(price_str)
                search_area_for_qty = line_copy[:idx_price_val] if idx_price_val != -1 else line_copy
                idx_qty_val = search_area_for_qty.rfind(qty_str)

                if has_uom_column and idx_qty_val != -1 and idx_price_val != -1 and (idx_qty_val + len(qty_str) < idx_price_val):
                    uom_candidate = line_copy[idx_qty_val + len(qty_str):idx_price_val].strip()
                    if uom_candidate and not uom_candidate.replace('.', '', 1).isdigit():
                        item['uom'] = uom_candidate
                
                if idx_qty_val != -1:
                    item['name'] = line_copy[:idx_qty_val].strip()
                else: 
                    # Fallback: if precise indices not found, try original simpler name extraction
                    _temp_line = line_copy
                    _idx_price = _temp_line.rfind(price_str)
                    if _idx_price != -1: _temp_line = _temp_line[:_idx_price].strip()
                    # If UoM was parsed, it might be at the end of _temp_line now
                    if item.get('uom') and _temp_line.endswith(str(item['uom'])):
                         _temp_line = _temp_line[:-len(str(item['uom']))].strip()
                    _idx_qty = _temp_line.rfind(qty_str)
                    if _idx_qty != -1: _temp_line = _temp_line[:_idx_qty].strip()
                    item['name'] = _temp_line.strip()


            elif len(numbers) == 1 and ('PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text or 'CANTIDAD' in item_header_text):
                val = float(numbers[0])
                if 'CANTIDAD' in item_header_text and not ('PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text):
                    item['quantity'] = val
                elif ('PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text) and not 'CANTIDAD' in item_header_text:
                    item['price_unit'] = val
                else:
                    if 'PRECIO UNITARIO' in item_header_text or 'VALOR UNITARIO' in item_header_text:
                         item['price_unit'] = val
                    elif 'CANTIDAD' in item_header_text:
                         item['quantity'] = val

                numeric_part_start_index = line_copy.rfind(numbers[0])
                item['name'] = line_copy[:numeric_part_start_index].strip()

        if not item.get('name') and line.strip():
            if numbers:
                first_num_idx = line_copy.find(numbers[0])
                if first_num_idx > 0:
                    item['name'] = line_copy[:first_num_idx].strip()
                else:
                    item['name'] = line_copy
            else:
                item['name'] = line_copy
        
        if not item.get('name') and len(item.keys()) <= (2 if has_uom_column else 1):
            return None
            
        return item
    
    def _normalize_set_type(self, set_type: str) -> str:
        """
        Normaliza el tipo de set a un valor estándar.
        
        Args:
            set_type: Tipo de set como aparece en el archivo.
            
        Returns:
            Tipo de set normalizado.
        """
        set_type = set_type.upper()
        
        mapping = {
            'BASICO': 'basic',
            'FACTURA EXENTA': 'exempt_invoice',
            'LIBRO DE COMPRAS': 'purchase_book',
            'LIBRO DE VENTAS': 'sales_book',
            'GUIA DE DESPACHO': 'dispatch_guide',
            'LIBRO DE GUIAS': 'guides_book',
            'EXPORTACION': 'export_document',
            'LIQUIDACIONES': 'liquidation',
            'FACTURA DE COMPRA': 'purchase_invoice_issuer',
        }
        
        for key, value in mapping.items():
            if key in set_type:
                return value
        
        return 'unknown'
    
    def _normalize_document_type(self, document_type: str) -> str:
        """
        Normaliza el tipo de documento a un valor estándar.
        
        Args:
            document_type: Tipo de documento como aparece en el archivo.
            
        Returns:
            Tipo de documento normalizado.
        """
        document_type = document_type.upper()
        
        mapping = {
            'FACTURA ELECTRONICA': 'electronic_invoice',
            'FACTURA NO AFECTA O EXENTA ELECTRONICA': 'exempt_invoice',
            'NOTA DE CREDITO ELECTRONICA': 'credit_note',
            'NOTA DE DEBITO ELECTRONICA': 'debit_note',
            'GUIA DE DESPACHO': 'dispatch_guide',
            'FACTURA DE EXPORTACION ELECTRONICA': 'export_invoice',
            'NOTA DE CREDITO DE EXPORTACION ELECTRONICA': 'export_credit_note',
            'NOTA DE DEBITO DE EXPORTACION ELECTRONICA': 'export_debit_note',
            'LIQUIDACION FACTURA ELECTRONICA': 'liquidation_invoice',
            'FACTURA DE COMPRA ELECTRONICA': 'purchase_invoice',
            'FACTURA': 'invoice',
        }
        
        for key, value in mapping.items():
            if key in document_type:
                return value
        
        return 'unknown'
    
    def _resolve_references(self, cases: List[Dict[str, Any]]) -> None:
        """
        Busca y establece referencias entre casos basados en sus descripciones.
        
        Args:
            cases: Lista de casos donde buscar referencias.
        """
        cases_by_number = {case['case_number']: case for case in cases}
        
        cases_by_doc_type = {}
        for case in cases:
            doc_type = case.get('document_type')
            if doc_type:
                if doc_type not in cases_by_doc_type:
                    cases_by_doc_type[doc_type] = []
                cases_by_doc_type[doc_type].append(case)
        
        for case in cases:
            if not case.get('reference_document'):
                continue
            
            ref_doc = case['reference_document']
            ref_reason = case.get('reference_reason', '')
            
            case_ref_match = re.search(r'CASO\s+(\d+-\d+)', ref_doc)
            if case_ref_match:
                ref_case_number = case_ref_match.group(1)
                if ref_case_number in cases_by_number:
                    case['reference_id'] = ref_case_number
                    continue
            
            for doc_type, doc_cases in cases_by_doc_type.items():
                if doc_type and doc_type in ref_doc:
                    if doc_cases:
                        if 'ANULA' in ref_reason:
                            case['reference_id'] = doc_cases[0]['case_number']
                        else:
                            case['reference_id'] = doc_cases[-1]['case_number']
                        break


# Función auxiliar para probar el parser
def test_parser(file_path):
    """
    Función para probar el parser con un archivo específico.
    
    Args:
        file_path: Ruta al archivo de texto con el set de pruebas.
        
    Returns:
        Diccionario con la información extraída.
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
        content = file.read()
    
    parser = SiiTestSetParser(content)
    return parser.parse()


if __name__ == '__main__':
    # Código para ejecutar pruebas cuando se ejecuta este archivo directamente
    import sys
    import json
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            result = test_parser(file_path)
            # Imprimir resultado en formato JSON para mejor visualización
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error al procesar el archivo: {e}")
    else:
        print("Por favor especifica la ruta al archivo de set de pruebas.")
        print("Uso: python sii_test_set_parser.py ruta/al/archivo.txt")