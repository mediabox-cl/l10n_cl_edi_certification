
from lxml import etree
import re

def canonicalize_c14n(element: etree._Element) -> bytes:
    """
    Canonicaliza un elemento XML usando el estándar C14N (XML-C14N 1.0).
    Esto es esencial para las firmas XMLDSig.
    Retorna el resultado como bytes, que es lo que las librerías de criptografía esperan.
    """
    # with_comments=False es el comportamiento estándar para C14N
    # strip_text=False preserva espacios en blanco significativos
    return etree.tostring(element, method='c14n', with_comments=False, strip_text=False)

def flatten_xml_for_ted(element: etree._Element) -> str:
    """
    "Aplana" un elemento XML para la firma FRMT del TED, como lo requiere el SII.
    Esto implica:
    1. Convertir el elemento a string.
    2. Remover saltos de línea y espacios entre etiquetas.
    3. No escapa caracteres especiales, eso se hace en un paso posterior.
    """
    # Serializa el XML a un string sin "pretty print"
    xml_string = etree.tostring(element, encoding='unicode')
    
    # Remueve espacios en blanco (incluyendo saltos de línea y tabulaciones) entre > y <
    # Esto colapsa la estructura a una sola línea sin afectar el contenido de las etiquetas.
    # Ejemplo: <A>\n  <B>texto</B>\n</A> -> <A><B>texto</B></A>
    flattened_string = re.sub(r'>\s+<', '><', xml_string).strip()
    
    return flattened_string

def escape_special_chars(xml_string: str) -> str:
    """
    Escapa los caracteres especiales de XML para la firma FRMT, como lo especifica el SII.
    El aplanado debe hacerse ANTES de este paso.
    """
    # El orden no importa aquí
    escaped = xml_string.replace('&', '&amp;')
    escaped = escaped.replace('<', '&lt;')
    escaped = escaped.replace('>', '&gt;')
    escaped = escaped.replace('"', '&quot;')
    escaped = escaped.replace('\'', '&apos;')
    return escaped
