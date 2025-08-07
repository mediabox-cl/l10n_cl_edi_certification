
from lxml import etree
from typing import Dict

class SignatureCleaner:
    """
    Elimina las firmas existentes de un árbol XML para prepararlo para el re-firmado.
    """
    def __init__(self, xml_root: etree._Element, namespaces: Dict[str, str]):
        self.root = xml_root
        self.namespaces = namespaces
        # El namespace de la firma digital es estándar
        self.ds_ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}

    def clean_all_signatures(self) -> None:
        """Ejecuta todos los pasos de limpieza de firmas."""
        self.clean_frmt_signatures()
        self.clean_dte_signatures()
        self.clean_setdte_signature()

    def clean_frmt_signatures(self) -> int:
        """Remueve los elementos FRMT de todos los TED en el documento."""
        # XPath para encontrar todos los elementos FRMT dentro de un TED
        xpath = ".//ns:TED/ns:FRMT"
        frmt_elements = self.root.findall(xpath, self.namespaces)
        
        count = 0
        for frmt in frmt_elements:
            parent = frmt.getparent()
            if parent is not None:
                parent.remove(frmt)
                count += 1
        return count

    def clean_dte_signatures(self) -> int:
        """Remueve las firmas XMLDSig de cada DTE individual."""
        # XPath para encontrar los DTEs y luego buscar sus firmas
        dte_elements = self.root.findall('.//ns:DTE', self.namespaces)
        count = 0
        for dte in dte_elements:
            # La firma es hija directa del DTE
            signatures = dte.findall('ds:Signature', self.ds_ns)
            for sig in signatures:
                dte.remove(sig)
                count += 1
        return count

    def clean_setdte_signature(self) -> int:
        """Remueve la firma XMLDSig del SetDTE consolidado."""
        setdte = self.root.find('ns:SetDTE', self.namespaces)
        if setdte is None:
            return 0
        
        # La firma es hija directa del SetDTE
        signatures = setdte.findall('ds:Signature', self.ds_ns)
        count = 0
        for sig in signatures:
            setdte.remove(sig)
            count += 1
        return count
