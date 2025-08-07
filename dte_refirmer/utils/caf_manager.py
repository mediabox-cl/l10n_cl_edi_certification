
import os
from lxml import etree
from typing import Dict
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import rsa

class CAFManager:
    """
    Escanea un directorio de archivos CAF, los carga en memoria y proporciona
    la clave privada correcta para un tipo de DTE específico.
    """
    def __init__(self, caf_folder_path: str):
        if not os.path.isdir(caf_folder_path):
            raise FileNotFoundError(f"El directorio de CAFs especificado no existe: {caf_folder_path}")
        self.caf_folder_path = caf_folder_path
        self.key_map: Dict[int, rsa.RSAPrivateKey] = {}
        self._load_all_cafs()

    def _load_all_cafs(self):
        """Escanea el directorio y sus subdirectorios para cargar todas las claves privadas de los CAF."""
        for root, _, files in os.walk(self.caf_folder_path):
            for filename in files:
                # Procesar solo archivos XML
                if filename.lower().endswith('.xml'):
                    file_path = os.path.join(root, filename)
                    try:
                        parser = etree.XMLParser(remove_blank_text=True, recover=True)
                        tree = etree.parse(file_path, parser)
                        xml_root = tree.getroot()

                        # Extraer el tipo de DTE (TD)
                        td_element = xml_root.find('.//DA/TD')
                        if td_element is None or not td_element.text:
                            continue # Archivo no parece ser un CAF válido, lo saltamos
                        dte_type = int(td_element.text)

                        # Extraer la clave privada de la etiqueta RSASK
                        rsask_element = xml_root.find('RSASK')
                        if rsask_element is None or not rsask_element.text:
                            continue # No se encontró la clave privada, saltamos
                        
                        key_pem = rsask_element.text.strip().encode('utf-8')
                        private_key = load_pem_private_key(key_pem, password=None)
                        
                        # Guardar la clave en el mapa
                        self.key_map[dte_type] = private_key

                    except (etree.XMLSyntaxError, ValueError, TypeError):
                        # Ignorar archivos que no se puedan parsear o no tengan el formato esperado
                        continue
        
        if not self.key_map:
            raise RuntimeError(f"No se pudo cargar ninguna clave CAF válida desde el directorio: {self.caf_folder_path}")

    def get_key_for_dte_type(self, dte_type: int) -> rsa.RSAPrivateKey:
        """Retorna la clave privada para un tipo de DTE dado."""
        key = self.key_map.get(dte_type)
        if key is None:
            raise ValueError(f"No se encontró un archivo CAF con su clave privada para el Tipo de DTE: {dte_type}")
        return key
