import base64
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from dte_refirmer.cleaners.xml_normalizer import flatten_xml_for_ted
from dte_refirmer.utils.caf_manager import CAFManager

class TEDResigner:
    """
    Re-firma el Timbre Electrónico Digital (TED) de un DTE, obteniendo la clave
    correcta desde un CAFManager.
    """
    def __init__(self, caf_manager: CAFManager):
        self.caf_manager = caf_manager

    def resign_ted(self, dd_element: etree._Element, namespaces: dict) -> etree._Element:
        """
        Construye un nuevo elemento TED, re-calculando la firma FRMT.
        """
        # 1. Actualizar el timestamp del TED al momento de la firma
        tsted_element = dd_element.find('.//ns:TSTED', namespaces)
        if tsted_element is not None:
            tsted_element.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        else:
            tsted_element = etree.SubElement(dd_element, 'TSTED')
            tsted_element.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # 2. Generar la nueva firma FRMT
        frmt_signature = self._generate_frmt_signature(dd_element, namespaces)

        # 3. Construir el nuevo elemento TED
        new_ted = etree.Element('TED', version='1.0')
        new_ted.append(dd_element)
        
        frmt_element = etree.SubElement(new_ted, 'FRMT', algoritmo='SHA1withRSA')
        frmt_element.text = frmt_signature

        return new_ted

    def _generate_frmt_signature(self, dd_element: etree._Element, namespaces: dict) -> str:
        """
        Genera la firma FRMT siguiendo el algoritmo específico del SII.
        """
        # Obtener el tipo de DTE desde el propio elemento DD
        dte_type_element = dd_element.find('ns:TD', namespaces)
        if dte_type_element is None or not dte_type_element.text:
            raise ValueError("El elemento DD no contiene el Tipo de DTE (TD).")
        dte_type = int(dte_type_element.text)

        # Obtener la clave privada correcta para este tipo de DTE
        private_key = self.caf_manager.get_key_for_dte_type(dte_type)

        # 1. Aplanar el XML del DD
        flattened_dd = flatten_xml_for_ted(dd_element)

        # 2. Codificar en ISO-8859-1
        dd_bytes = flattened_dd.encode('ISO-8859-1')

        # 3. Firmar con SHA1withRSA usando la clave privada del CAF
        signature = private_key.sign(
            dd_bytes,
            padding.PKCS1v15(),
            hashes.SHA1()
        )

        # 4. Codificar el resultado en Base64
        return base64.b64encode(signature).decode('ascii')