
from lxml import etree
from datetime import datetime

file_path = '/home/butcherwutcher/projects/l10n_cl_edi_certification/generatedDTEs/LGD_2025-07_DEFINITIVO.xml'

try:
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    tree = etree.parse(file_path, parser)
    root = tree.getroot()

    ns = {'sii': 'http://www.sii.cl/SiiDte'}
    envio_libro = root.find('sii:EnvioLibro', ns)

    if envio_libro is not None:
        # Check if TmstFirma already exists to avoid adding duplicates
        if envio_libro.find('sii:TmstFirma', ns) is None:
            tmst_firma = etree.SubElement(envio_libro, 'TmstFirma')
            tmst_firma.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            
            with open(file_path, 'wb') as f:
                f.write(etree.tostring(root, pretty_print=True, encoding='ISO-8859-1', xml_declaration=True))
            print(f"Successfully added TmstFirma to {file_path}")
        else:
            print(f"TmstFirma already exists in {file_path}. No changes made.")
    else:
        print(f"Could not find EnvioLibro element in {file_path}")

except etree.XMLSyntaxError as e:
    print(f"Error de sintaxis XML en {file_path}: {e}")
except Exception as e:
    print(f"Error inesperado al procesar {file_path}: {e}")
