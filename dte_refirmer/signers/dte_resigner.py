import base64
from lxml import etree
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

from dte_refirmer.cleaners.xml_normalizer import canonicalize_c14n

class DTEResigner:
    """
    Re-construye y re-firma un DTE individual con una firma XMLDSig.
    """
    def __init__(self, cert_path: str, cert_password: str, namespaces: dict):
        self.cert_path = cert_path
        self.cert_password = cert_password.encode('utf-8')
        self.namespaces = namespaces
        self.ds_ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
        self._load_certificate()

    def _load_certificate(self):
        """Carga el archivo PFX y extrae los componentes."""
        try:
            with open(self.cert_path, 'rb') as f:
                pfx_data = f.read()
            
            self.private_key, self.public_cert, _ = pkcs12.load_key_and_certificates(
                pfx_data,
                self.cert_password
            )
        except ValueError as e:
            if "MAC verify failed" in str(e) or "decryption failed" in str(e):
                raise ValueError("La contraseña del certificado PFX es incorrecta.")
            raise e
        except Exception as e:
            raise RuntimeError(f"No se pudo cargar el certificado PFX desde {self.cert_path}: {e}")

    def resign_dte(self, dte_data: dict, new_ted: etree._Element) -> etree._Element:
        """
        Re-arma el DTE y le añade una nueva firma XMLDSig.
        """
        documento = self._build_documento(dte_data, new_ted)
        dte_element = etree.Element('DTE', version='1.0')
        dte_element.append(documento)
        signature = self._generate_xmldsig_signature(documento, dte_data['id'])
        dte_element.append(signature)
        return dte_element

    def _build_documento(self, dte_data: dict, new_ted: etree._Element) -> etree._Element:
        documento = etree.Element('Documento', ID=dte_data['id'])
        documento.append(dte_data['encabezado'])
        for detalle in dte_data['detalles']:
            documento.append(detalle)
        for referencia in dte_data['referencias']:
            documento.append(referencia)
        documento.append(new_ted)
        tmst_firma = etree.SubElement(documento, 'TmstFirma')
        tmst_firma.text = dte_data['timestamp']
        return documento

    def _generate_xmldsig_signature(self, element_to_sign: etree._Element, reference_uri: str) -> etree._Element:
        c14n_element = canonicalize_c14n(element_to_sign)
        digest = hashes.Hash(hashes.SHA1())
        digest.update(c14n_element)
        digest_value = base64.b64encode(digest.finalize()).decode('ascii')

        signature = etree.Element(etree.QName(self.ds_ns['ds'], 'Signature'), nsmap=self.ds_ns)
        signed_info = etree.SubElement(signature, etree.QName(self.ds_ns['ds'], 'SignedInfo'))

        c14n_method = etree.SubElement(signed_info, etree.QName(self.ds_ns['ds'], 'CanonicalizationMethod'))
        c14n_method.set('Algorithm', 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
        sig_method = etree.SubElement(signed_info, etree.QName(self.ds_ns['ds'], 'SignatureMethod'))
        sig_method.set('Algorithm', 'http://www.w3.org/2000/09/xmldsig#rsa-sha1')

        reference = etree.SubElement(signed_info, etree.QName(self.ds_ns['ds'], 'Reference'))
        reference.set('URI', f'#{reference_uri}')
        digest_method = etree.SubElement(reference, etree.QName(self.ds_ns['ds'], 'DigestMethod'))
        digest_method.set('Algorithm', 'http://www.w3.org/2000/09/xmldsig#sha1')
        digest_value_el = etree.SubElement(reference, etree.QName(self.ds_ns['ds'], 'DigestValue'))
        digest_value_el.text = digest_value

        c14n_signed_info = canonicalize_c14n(signed_info)
        private_key = self.private_key
        signature_value_b64 = base64.b64encode(private_key.sign(
            c14n_signed_info,
            padding.PKCS1v15(),
            hashes.SHA1()
        )).decode('ascii')

        sig_value_element = etree.SubElement(signature, etree.QName(self.ds_ns['ds'], 'SignatureValue'))
        sig_value_element.text = signature_value_b64
        signature.append(self._build_key_info())

        return signature

    def _build_key_info(self) -> etree._Element:
        from cryptography.hazmat.primitives import serialization
        public_numbers = self.private_key.public_key().public_numbers()
        modulus_b64 = base64.b64encode(public_numbers.n.to_bytes(
            (public_numbers.n.bit_length() + 7) // 8, 'big')).decode('ascii')
        exponent_b64 = base64.b64encode(public_numbers.e.to_bytes(
            (public_numbers.e.bit_length() + 7) // 8, 'big')).decode('ascii')

        cert_bytes = self.public_cert.public_bytes(serialization.Encoding.PEM)
        cert_b64 = "".join(line for line in cert_bytes.decode('ascii').split('\n') if not line.startswith('---'))

        key_info = etree.Element(etree.QName(self.ds_ns['ds'], 'KeyInfo'))
        key_value = etree.SubElement(key_info, etree.QName(self.ds_ns['ds'], 'KeyValue'))
        rsa_key_value = etree.SubElement(key_value, etree.QName(self.ds_ns['ds'], 'RSAKeyValue'))
        modulus = etree.SubElement(rsa_key_value, etree.QName(self.ds_ns['ds'], 'Modulus'))
        modulus.text = modulus_b64
        exponent = etree.SubElement(rsa_key_value, etree.QName(self.ds_ns['ds'], 'Exponent'))
        exponent.text = exponent_b64

        x509_data = etree.SubElement(key_info, etree.QName(self.ds_ns['ds'], 'X509Data'))
        x509_cert = etree.SubElement(x509_data, etree.QName(self.ds_ns['ds'], 'X509Certificate'))
        x509_cert.text = cert_b64

        return key_info