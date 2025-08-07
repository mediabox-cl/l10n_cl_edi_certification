
from lxml import etree
from typing import List, Dict, Any

class XMLParser:
    """
    Parsea un archivo XML de EnvioDTE y extrae sus componentes principales.
    """
    def __init__(self, xml_file_path: str):
        self.xml_path = xml_file_path
        self.root = None
        self.setdte_element = None
        self.caratula = None
        self.dte_elements = []
        self.namespaces = {}

    def parse(self) -> None:
        """Parsea el archivo XML y carga los elementos estructurales."""
        try:
            # Usamos un parser que remueve "blank text" para simplificar la estructura
            parser = etree.XMLParser(remove_blank_text=True, recover=True)
            tree = etree.parse(self.xml_path, parser)
            self.root = tree.getroot()
            self.namespaces = self.root.nsmap

            # El namespace por defecto puede ser None, lo asignamos a 'ns' para búsquedas
            if None in self.namespaces:
                self.namespaces['ns'] = self.namespaces.pop(None)

            self.setdte_element = self.root.find('ns:SetDTE', self.namespaces)
            if self.setdte_element is None:
                raise ValueError("No se encontró el elemento SetDTE en el XML.")

            self.caratula = self.setdte_element.find('ns:Caratula', self.namespaces)
            if self.caratula is None:
                raise ValueError("No se encontró el elemento Caratula en el SetDTE.")

            # Buscar elementos DTE y extraer su contenido (Documento o Exportaciones)
            for dte_wrapper in self.setdte_element.findall('ns:DTE', self.namespaces):
                documento_element = dte_wrapper.find('ns:Documento', self.namespaces)
                exportaciones_element = dte_wrapper.find('ns:Exportaciones', self.namespaces)
                
                if documento_element is not None:
                    self.dte_elements.append(documento_element)
                elif exportaciones_element is not None:
                    self.dte_elements.append(exportaciones_element)
                else:
                    raise ValueError("DTE no contiene un elemento Documento ni Exportaciones.")

            if not self.dte_elements:
                raise ValueError("No se encontraron elementos DTE válidos en el SetDTE.")

        except etree.XMLSyntaxError as e:
            raise ValueError(f"Error de sintaxis XML en {self.xml_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error inesperado al parsear {self.xml_path}: {e}")

    def get_envelope_structure(self) -> Dict[str, Any]:
        """Retorna la estructura y atributos del elemento raíz EnvioDTE."""
        if self.root is None:
            raise RuntimeError("El XML no ha sido parseado. Llama a .parse() primero.")
        return {
            'namespaces': self.namespaces,
            'attributes': self.root.attrib,
            'version': self.root.get('version')
        }

    def get_caratula(self) -> etree._Element:
        """Retorna el elemento Caratula completo."""
        if self.caratula is None:
            raise RuntimeError("El XML no ha sido parseado. Llama a .parse() primero.")
        return self.caratula

    def get_dte_elements(self) -> List[etree._Element]:
        """Retorna una lista de todos los elementos DTE."""
        if not self.dte_elements:
            raise RuntimeError("El XML no ha sido parseado. Llama a .parse() primero.")
        return self.dte_elements
