from lxml import etree
from typing import List
from datetime import datetime

from dte_refirmer.signers.dte_resigner import DTEResigner # Reutilizamos la lógica de firma

class SetDTEResigner:
    """
    Re-construye el EnvioDTE y firma el SetDTE consolidado.
    """
    def __init__(self, cert_path: str, cert_password: str, namespaces: dict):
        # La firma del SetDTE usa el mismo certificado que los DTEs individuales
        self.signer = DTEResigner(cert_path, cert_password, namespaces)
        self.namespaces = namespaces

    def resign_setdte(self, envelope_data: dict, caratula: etree._Element, signed_dtes: List[etree._Element]) -> etree._Element:
        """
        Re-arma el envelope completo y firma el SetDTE.
        """
        nsmap = {k if k != 'ns' else None: v for k, v in self.namespaces.items()}
        
        envelope = etree.Element(etree.QName(self.namespaces['ns'], 'EnvioDTE'), nsmap=nsmap)
        for attr, value in envelope_data['attributes'].items():
            envelope.set(attr, value)

        setdte = etree.SubElement(envelope, 'SetDTE', ID='SetDoc')

        # Update TmstFirmaEnv in Caratula
        tmst_firma_env = caratula.find('ns:TmstFirmaEnv', self.namespaces)
        if tmst_firma_env is not None:
            tmst_firma_env.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        setdte.append(caratula)
        for dte in signed_dtes:
            setdte.append(dte)

        # Firmar el SetDTE usando la misma lógica de firma
        signature = self.signer._generate_xmldsig_signature(setdte, 'SetDoc')
        envelope.append(signature)

        return envelope