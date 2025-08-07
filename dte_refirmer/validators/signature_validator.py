import base64
from lxml import etree
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509 import load_pem_x509_certificate

from dte_refirmer.cleaners.xml_normalizer import flatten_xml_for_ted, canonicalize_c14n

class SignatureValidator:
    """
    Valida los tres niveles de firma de un EnvioDTE.
    """
    def __init__(self, signed_xml_path: str):
        parser = etree.XMLParser(remove_blank_text=True, recover=True)
        self.tree = etree.parse(signed_xml_path, parser)
        self.root = self.tree.getroot()
        self.namespaces = self.root.nsmap
        if None in self.namespaces:
            self.namespaces['ns'] = self.namespaces.pop(None)
        self.ds_ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}

    def verify_all(self) -> bool:
        """Ejecuta todas las validaciones y retorna True si todas son exitosas."""
        try:
            self.verify_ted_signatures()
            self.verify_dte_signatures()
            self.verify_setdte_signature()
            return True
        except Exception:
            return False

    def verify_ted_signatures(self):
        """Verifica la firma FRMT de cada TED en el documento."""
        for ted in self.root.findall('.//ns:TED', self.namespaces):
            dd = ted.find('ns:DD', self.namespaces)
            frmt = ted.find('ns:FRMT', self.namespaces)
            if dd is None or frmt is None or not frmt.text:
                raise ValueError("TED malformado: falta DD o FRMT.")

            m = dd.find('.//ns:RSAPK/ns:M', self.namespaces).text
            e = dd.find('.//ns:RSAPK/ns:E', self.namespaces).text
            modulus = int.from_bytes(base64.b64decode(m), 'big')
            exponent = int.from_bytes(base64.b64decode(e), 'big')
            public_key = rsa.RSAPublicNumbers(e=exponent, n=modulus).public_key()

            signature = base64.b64decode(frmt.text)
            data_to_verify = flatten_xml_for_ted(dd).encode('ISO-8859-1')
            
            public_key.verify(
                signature,
                data_to_verify,
                padding.PKCS1v15(),
                hashes.SHA1()
            )

    def _verify_xmldsig(self, element_id: str):
        """Lógica genérica para verificar una firma XMLDSig."""
        referenced_element = self.root.find(f'.//*[@ID=\'{element_id}\']', self.namespaces)
        if referenced_element is None:
            raise ValueError(f"No se encontró el elemento referenciado con ID: {element_id}")

        signature = None
        if referenced_element.tag == etree.QName(self.namespaces.get('ns'), 'Documento'):
            parent = referenced_element.getparent()
            if parent is not None:
                signature = parent.find('ds:Signature', self.ds_ns)
        else:
            signature = referenced_element.find('ds:Signature', self.ds_ns)

        if signature is None:
            raise ValueError(f"No se encontró la firma para el elemento con ID: {element_id}")

        signed_info = signature.find('ds:SignedInfo', self.ds_ns)
        signature_value = base64.b64decode(signature.find('ds:SignatureValue', self.ds_ns).text)
        cert_b64 = signature.find('.//ds:X509Certificate', self.ds_ns).text
        
        cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_b64}\n-----END CERTIFICATE-----".encode()
        cert = load_pem_x509_certificate(cert_pem)
        public_key = cert.public_key()

        c14n_signed_info = canonicalize_c14n(signed_info)
        public_key.verify(
            signature_value,
            c14n_signed_info,
            padding.PKCS1v15(),
            hashes.SHA1()
        )

        ref_uri = signed_info.find('ds:Reference', self.ds_ns).get('URI')[1:]
        digest_value_in_xml = signed_info.find('.//ds:DigestValue', self.ds_ns).text
        
        element_to_check = self.root.find(f'.//*[@ID=\'{ref_uri}\']', self.namespaces)
        c14n_element = canonicalize_c14n(element_to_check)
        
        digest = hashes.Hash(hashes.SHA1())
        digest.update(c14n_element)
        calculated_digest = base64.b64encode(digest.finalize()).decode('ascii')

        if digest_value_in_xml != calculated_digest:
            raise ValueError(f"El Digest para {ref_uri} no coincide. XML: {digest_value_in_xml}, Calculado: {calculated_digest}")

    def verify_dte_signatures(self):
        """Verifica las firmas XMLDSig de cada DTE individual."""
        for dte in self.root.findall('.//ns:DTE', self.namespaces):
            doc_id = dte.find('ns:Documento', self.namespaces).get('ID')
            self._verify_xmldsig(doc_id)

    def verify_setdte_signature(self):
        """Verifica la firma XMLDSig del SetDTE."""
        self._verify_xmldsig('SetDoc')