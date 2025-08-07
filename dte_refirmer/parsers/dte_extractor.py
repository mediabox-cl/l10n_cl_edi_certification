
from lxml import etree
from typing import List, Dict, Any

class DTEExtractor:
    """
    Extrae datos específicos y reutilizables de un elemento DTE.
    """
    def __init__(self, dte_element: etree._Element, namespaces: Dict[str, str]):
        self.dte_element = dte_element
        self.namespaces = namespaces
        
        # Determine if the element is a Documento or Exportaciones
        if dte_element.tag == etree.QName(namespaces['ns'], 'Documento'):
            self.documento = dte_element
        elif dte_element.tag == etree.QName(namespaces['ns'], 'Exportaciones'):
            self.documento = dte_element
        else:
            raise ValueError("Elemento DTE no es Documento ni Exportaciones.")

        self.document_id = self.documento.get('ID')
        if not self.document_id:
            raise ValueError("El elemento Documento/Exportaciones no tiene un atributo ID.")

    def extract_document_structure(self) -> Dict[str, Any]:
        """Extrae la estructura completa del Documento para reconstrucción."""
        return {
            'id': self.document_id,
            'encabezado': self.extract_encabezado(),
            'detalles': self.extract_detalles(),
            'referencias': self.extract_referencias(),
            'timestamp': self.extract_timestamp(),
        }

    def extract_encabezado(self) -> etree._Element:
        """Extrae el elemento Encabezado completo para reutilizarlo."""
        encabezado = self.documento.find('ns:Encabezado', self.namespaces)
        if encabezado is None:
            raise ValueError(f"Documento {self.document_id} no contiene Encabezado.")
        return encabezado

    def extract_detalles(self) -> List[etree._Element]:
        """Extrae una lista de todos los elementos Detalle."""
        return self.documento.findall('ns:Detalle', self.namespaces)

    def extract_referencias(self) -> List[etree._Element]:
        """Extrae una lista de todos los elementos Referencia."""
        return self.documento.findall('ns:Referencia', self.namespaces)

    def extract_timestamp(self) -> str:
        """Extrae el timestamp de la firma original."""
        tmst_firma = self.documento.find('ns:TmstFirma', self.namespaces)
        if tmst_firma is None:
            raise ValueError(f"Documento {self.document_id} no contiene TmstFirma.")
        return tmst_firma.text

    def extract_ted_data(self) -> Dict[str, Any]:
        """Extrae los datos clave del TED existente para la re-firma."""
        ted = self.documento.find('ns:TED', self.namespaces)
        if ted is None:
            raise ValueError(f"Documento {self.document_id} no contiene TED.")
        
        dd = ted.find('ns:DD', self.namespaces)
        if dd is None:
            raise ValueError(f"TED en {self.document_id} no contiene DD.")
            
        caf = dd.find('ns:CAF', self.namespaces)
        if caf is None:
            raise ValueError(f"DD en {self.document_id} no contiene CAF.")

        return {
            'dd_element': dd,
            'caf_element': caf,
        }
