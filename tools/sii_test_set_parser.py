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
    CASE_HEADER_PATTERN = r'CASO\s+(\d+-\d+)'
    DOCUMENT_TYPE_PATTERN = r'DOCUMENTO\s+([\w\sÁ-Úá-ú]+)'
    REFERENCE_PATTERN = r'REFERENCIA\s+([\w\sÁ-Úá-ú]+)'
    REFERENCE_REASON_PATTERN = r'RAZON\s+REFERENCIA\s+([\w\sÁ-Úá-ú]+)'
    ITEM_HEADER_PATTERN = r'ITEM\s+(?:CANTIDAD|VALOR\s+UNITARIO|PRECIO\s+UNITARIO|TOTAL\s+LINEA)?'
    MOTIVO_PATTERN = r'MOTIVO:\s+([\w\sÁ-Úá-ú]+)'
    TRASLADO_PATTERN = r'TRASLADO POR:\s+([\w\sÁ-Úá-ú]+)'
    
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
        
        Args:
            set_content: Texto del set de pruebas.
            set_type: Tipo de set.
            attention_number: Número de atención del set.
            
        Returns:
            Lista de casos extraídos.
        """
        cases = []
        
        # Buscar todos los casos en el set
        case_matches = re.finditer(self.CASE_HEADER_PATTERN, set_content)
        for i, case_match in enumerate(case_matches):
            case_number = case_match.group(1).strip()
            
            # Obtener el texto del caso hasta el próximo caso o el final
            start_pos = case_match.start()
            next_case = set_content.find('CASO', start_pos + 1)
            if next_case == -1:
                next_case = len(set_content)
            
            case_content = set_content[start_pos:next_case]
            
            # Procesar el caso
            case_data = self._process_case(case_content, case_number, set_type, attention_number)
            if case_data:
                cases.append(case_data)
        
        return cases
    
    def _process_case(self, case_content: str, case_number: str, set_type: str, attention_number: str) -> Dict[str, Any]:
        """
        Procesa un caso de prueba individual.
        
        Args:
            case_content: Texto del caso.
            case_number: Número del caso.
            set_type: Tipo de set al que pertenece.
            attention_number: Número de atención del set.
            
        Returns:
            Diccionario con los datos del caso.
        """
        lines = case_content.split('\n')
        
        case_data = {
            'case_number': case_number,
            'set_type': self._normalize_set_type(set_type),
            'set_attention_number': attention_number,
            'document_type': None,
            'reference_document': None,
            'reference_reason': None,
            'motivo': None,
            'traslado_por': None,
            'items': [],
            'additional_info': {}
        }
        
        # Para mantener el seguimiento del contexto actual
        in_items_section = False
        
        for line in lines:
            # Detectar tipo de documento
            doc_match = re.search(self.DOCUMENT_TYPE_PATTERN, line)
            if doc_match:
                document_type = doc_match.group(1).strip()
                case_data['document_type'] = self._normalize_document_type(document_type)
                continue
            
            # Detectar referencias
            ref_match = re.search(self.REFERENCE_PATTERN, line)
            if ref_match:
                reference = ref_match.group(1).strip()
                case_data['reference_document'] = reference
                continue
            
            # Detectar razón de referencia
            reason_match = re.search(self.REFERENCE_REASON_PATTERN, line)
            if reason_match:
                reason = reason_match.group(1).strip()
                case_data['reference_reason'] = reason
                continue
            
            # Detectar motivo (para guías de despacho)
            motivo_match = re.search(self.MOTIVO_PATTERN, line)
            if motivo_match:
                motivo = motivo_match.group(1).strip()
                case_data['motivo'] = motivo
                continue
            
            # Detectar traslado por (para guías de despacho)
            traslado_match = re.search(self.TRASLADO_PATTERN, line)
            if traslado_match:
                traslado_por = traslado_match.group(1).strip()
                case_data['traslado_por'] = traslado_por
                continue
            
            # Detectar inicio de sección de ítems
            if 'ITEM' in line and ('CANTIDAD' in line or 'PRECIO UNITARIO' in line or 'VALOR UNITARIO' in line):
                in_items_section = True
                continue
            
            # Procesar ítems si estamos en la sección de ítems
            if in_items_section and line.strip() and not line.startswith('=') and not 'DESCUENTO GLOBAL' in line:
                item = self._parse_item_line(line)
                if item:
                    case_data['items'].append(item)
                continue
            
            # Capturar información adicional con formato clave: valor
            if ":" in line and not in_items_section:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if key and value:
                        case_data['additional_info'][key] = value
            
            # Capturar descuento global
            if 'DESCUENTO GLOBAL' in line:
                discount_match = re.search(r'(\d+)%', line)
                if discount_match:
                    case_data['global_discount'] = float(discount_match.group(1))
        
        return case_data
    
    def _parse_item_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parsea una línea de ítem.
        
        Args:
            line: Línea con datos del ítem.
            
        Returns:
            Diccionario con los datos del ítem o None si no se pudo parsear.
        """
        if not line.strip() or line.startswith('=') or line.startswith('-'):
            return None
        
        # Trabajar con una copia de la línea para no modificar la original
        line_copy = line.strip()
        
        # Detectar porcentaje de descuento si aparece al final
        discount_percent = None
        discount_match = re.search(r'(\d+)%$', line_copy)
        if discount_match:
            discount_percent = float(discount_match.group(1))
            # Quitar el descuento de la línea para no afectar el parsing del resto
            line_copy = line_copy[:discount_match.start()].strip()
        
        # Intentar extraer cantidad y precio unitario
        # Buscamos números al final de la línea
        numbers = re.findall(r'\b\d+\b', line_copy)
        
        item = {
            'name': line_copy,  # Valor predeterminado si no podemos parsear correctamente
            'is_exempt': 'EXENTO' in line_copy.upper() or 'EXENTA' in line_copy.upper()
        }
        
        if discount_percent is not None:
            item['discount_percent'] = discount_percent
        
        if len(numbers) >= 2:
            # Al menos dos números, asumimos que el último es precio y el penúltimo es cantidad
            item['price_unit'] = float(numbers[-1])
            item['quantity'] = float(numbers[-2])
            
            # El nombre es todo lo que está antes de los números
            # Para esto, necesitamos encontrar la posición del penúltimo número
            pos_quantity = line_copy.rfind(numbers[-2])
            if pos_quantity > 0:
                item['name'] = line_copy[:pos_quantity].strip()
        elif len(numbers) == 1:
            # Solo un número, podría ser cantidad o precio
            if 'CANTIDAD' in line_copy:
                item['quantity'] = float(numbers[0])
            else:
                item['price_unit'] = float(numbers[0])
            
            # El nombre es todo lo que está antes del número
            pos_number = line_copy.find(numbers[0])
            if pos_number > 0:
                item['name'] = line_copy[:pos_number].strip()
        
        # Si no se pudo extraer el nombre, usar toda la línea
        if 'name' not in item or not item['name']:
            item['name'] = line_copy
        
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
        # Crear diccionario para búsqueda rápida por caso_number
        cases_by_number = {case['case_number']: case for case in cases}
        
        # Crear diccionario por tipo de documento
        cases_by_doc_type = {}
        for case in cases:
            doc_type = case.get('document_type')
            if doc_type:  # Solo agregar si doc_type no es None
                if doc_type not in cases_by_doc_type:
                    cases_by_doc_type[doc_type] = []
                cases_by_doc_type[doc_type].append(case)
        
        # Para cada caso que tenga referencia, intentar encontrar el caso referenciado
        for case in cases:
            if not case.get('reference_document'):
                continue
            
            ref_doc = case['reference_document']
            ref_reason = case.get('reference_reason', '')
            
            # Extraer caso referenciado si se menciona el número
            case_ref_match = re.search(r'CASO\s+(\d+-\d+)', ref_doc)
            if case_ref_match:
                ref_case_number = case_ref_match.group(1)
                if ref_case_number in cases_by_number:
                    case['reference_id'] = ref_case_number
                    continue
            
            # Si no encontramos por número, buscar por tipo de documento
            for doc_type, doc_cases in cases_by_doc_type.items():
                if doc_type and doc_type in ref_doc:  # Asegurarse de que doc_type no sea None
                    # Si hay varios del mismo tipo, tomamos el más reciente (número más alto)
                    # a menos que sea una anulación, en cuyo caso buscamos el primero
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