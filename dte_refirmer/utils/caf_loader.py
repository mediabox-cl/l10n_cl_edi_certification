
from lxml import etree
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import rsa

def load_caf_private_key_from_xml(xml_file_path: str) -> rsa.RSAPrivateKey:
    """
    Carga un archivo de autorización XML del SII, extrae la clave privada 
    de la etiqueta <RSASK> y la retorna como un objeto de clave privada.
    """
    try:
        parser = etree.XMLParser(remove_blank_text=True, recover=True)
        tree = etree.parse(xml_file_path, parser)
        root = tree.getroot()

        # Buscar la etiqueta RSASK
        rsask_element = root.find('RSASK')
        if rsask_element is None or not rsask_element.text:
            raise ValueError(f"No se encontró la etiqueta <RSASK> con la clave privada en {xml_file_path}")

        # El contenido de la etiqueta es la clave en formato PEM
        key_pem = rsask_element.text.strip().encode('utf-8')

        # Cargar la clave PEM
        private_key = load_pem_private_key(key_pem, password=None)
        return private_key

    except etree.XMLSyntaxError as e:
        raise ValueError(f"Error de sintaxis XML en {xml_file_path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error inesperado al cargar la clave CAF desde {xml_file_path}: {e}")
