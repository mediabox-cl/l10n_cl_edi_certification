
from lxml import etree
from typing import Dict, Tuple

class CAFExtractor:
    """
    Extrae y valida información de un elemento CAF.
    """
    def __init__(self, caf_element: etree._Element, namespaces: Dict[str, str]):
        self.caf_element = caf_element
        self.namespaces = namespaces
        self.da = self.caf_element.find('ns:DA', self.namespaces)
        if self.da is None:
            raise ValueError("Elemento CAF no contiene un elemento DA.")

    def extract_caf_data(self) -> Dict[str, any]:
        """Extrae los datos principales del CAF."""
        return {
            'rut_emisor': self._get_text('.//ns:RE'),
            'tipo_dte': int(self._get_text('.//ns:TD')),
            'rango_folios': self._get_rango_folios(),
            'fecha_autorizacion': self._get_text('.//ns:FA'),
        }

    def _get_text(self, xpath: str) -> str:
        element = self.da.find(xpath, self.namespaces)
        if element is None or not element.text:
            raise ValueError(f"No se pudo encontrar o está vacío el elemento en la ruta: {xpath}")
        return element.text.strip()

    def _get_rango_folios(self) -> Tuple[int, int]:
        """Extrae el rango de folios (Desde, Hasta)."""
        rango_element = self.da.find('ns:RNG', self.namespaces)
        if rango_element is None:
            raise ValueError("No se encontró el elemento RNG en el CAF.")
        
        desde = rango_element.find('ns:D', self.namespaces)
        hasta = rango_element.find('ns:H', self.namespaces)
        
        if desde is None or hasta is None or not desde.text or not hasta.text:
            raise ValueError("El elemento RNG está incompleto.")
            
        return int(desde.text), int(hasta.text)

    def validate_folio(self, folio: int) -> bool:
        """Valida si un folio está dentro del rango autorizado por el CAF."""
        rango_desde, rango_hasta = self._get_rango_folios()
        return rango_desde <= folio <= rango_hasta
