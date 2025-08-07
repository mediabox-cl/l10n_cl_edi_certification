import click
from lxml import etree
from datetime import datetime, timedelta

# Importar todos los componentes
from dte_refirmer.parsers.xml_parser import XMLParser
from dte_refirmer.parsers.dte_extractor import DTEExtractor
from dte_refirmer.cleaners.signature_cleaner import SignatureCleaner
from dte_refirmer.utils.caf_manager import CAFManager
from dte_refirmer.signers.ted_resigner import TEDResigner
from dte_refirmer.signers.dte_resigner import DTEResigner
from dte_refirmer.signers.setdte_resigner import SetDTEResigner
from dte_refirmer.validators.signature_validator import SignatureValidator

def update_dte_data_interactive(dte_element, namespaces):
    """Función interactiva para actualizar fecha y folio de un DTE."""
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    
    id_doc = dte_element.find('.//ns:Encabezado/ns:IdDoc', namespaces)
    dd = dte_element.find('.//ns:TED/ns:DD', namespaces)
    if id_doc is None or dd is None:
        raise ValueError("DTE no tiene IdDoc o DD, no se puede procesar.")

    tipo_dte = id_doc.find('ns:TipoDTE', namespaces).text
    folio_actual = id_doc.find('ns:Folio', namespaces).text

    click.echo("-" * 40)
    click.echo(f"Procesando DTE Tipo: {click.style(tipo_dte, bold=True)}, Folio actual: {click.style(folio_actual, bold=True)}")

    # Actualizar Fecha Emisión
    id_doc.find('ns:FchEmis', namespaces).text = today_str
    dd.find('ns:FE', namespaces).text = today_str
    click.echo(f"  - Fecha de Emisión actualizada a: {today_str}")

    # Actualizar Fecha de Vencimiento (30 días después de la fecha de emisión)
    fch_venc_element = id_doc.find('ns:FchVenc', namespaces)
    if fch_venc_element is not None:
        fch_venc_element.text = (today + timedelta(days=30)).strftime('%Y-%m-%d')
        click.echo(f"  - Fecha de Vencimiento actualizada a: {fch_venc_element.text}")

    # Actualizar Folio (interactivo)
    nuevo_folio_str = click.prompt(f"  - Ingrese nuevo folio", default=folio_actual)
    nuevo_folio = int(nuevo_folio_str)

    id_doc.find('ns:Folio', namespaces).text = str(nuevo_folio)
    dd.find('ns:F', namespaces).text = str(nuevo_folio)
    
    doc_element = dte_element.find('ns:Documento', namespaces)
    if doc_element is not None:
        new_id = f"F{nuevo_folio}T{tipo_dte}"
        doc_element.set('ID', new_id)
        click.echo(f"  - Folio actualizado a: {nuevo_folio} (ID: {new_id})")

def update_dte_data_non_interactive(dte_element, namespaces):
    """Función NO interactiva para actualizar fecha y mantener folio."""
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    
    id_doc = dte_element.find('.//ns:Encabezado/ns:IdDoc', namespaces)
    dd = dte_element.find('.//ns:TED/ns:DD', namespaces)
    if id_doc is None or dd is None:
        raise ValueError("DTE no tiene IdDoc o DD, no se puede procesar.")

    tipo_dte = id_doc.find('ns:TipoDTE', namespaces).text
    folio_actual = id_doc.find('ns:Folio', namespaces).text

    click.echo("-" * 40)
    click.echo(f"Procesando DTE Tipo: {click.style(tipo_dte, bold=True)}, Folio: {click.style(folio_actual, bold=True)} (modo no interactivo)")

    # Actualizar Fecha Emisión
    id_doc.find('ns:FchEmis', namespaces).text = today_str
    dd.find('ns:FE', namespaces).text = today_str
    click.echo(f"  - Fecha de Emisión actualizada a: {today_str}")
    click.echo(f"  - Folio conservado: {folio_actual}")

    # Actualizar Fecha de Vencimiento (30 días después de la fecha de emisión)
    fch_venc_element = id_doc.find('ns:FchVenc', namespaces)
    if fch_venc_element is not None:
        fch_venc_element.text = (today + timedelta(days=30)).strftime('%Y-%m-%d')
        click.echo(f"  - Fecha de Vencimiento actualizada a: {fch_venc_element.text}")

@click.group()
def cli():
    """Herramienta para re-firmar y actualizar DTEs generados por Odoo."""
    pass

@cli.command()
@click.option('--input', required=True, type=click.Path(exists=True), help='Ruta al archivo XML de entrada.')
@click.option('--output', required=True, type=click.Path(), help='Ruta para guardar el archivo XML re-firmado.')
@click.option('--caf-folder', required=True, type=click.Path(exists=True), help='Ruta a la carpeta con todos los archivos CAF.')
@click.option('--cert', required=True, type=click.Path(exists=True), help='Ruta al certificado digital (.pfx).')
@click.option('--cert-password', required=True, help='Contraseña del certificado digital.')
@click.option('--non-interactive', is_flag=True, default=False, help='Ejecuta en modo no interactivo, actualizando fechas y manteniendo folios originales.')
def resign(input, output, caf_folder, cert, cert_password, non_interactive):
    """
    Re-firma un SetDTE completo, actualizando fechas y (opcionalmente) folios.
    """
    if non_interactive:
        click.echo(click.style("Ejecutando en modo NO INTERACTIVO.", bg='yellow', fg='black'))
    
    click.echo(f"Iniciando proceso de re-firmado para: {input}")

    try:
        click.echo("Cargando claves CAF...")
        caf_manager = CAFManager(caf_folder)
        click.echo(f"{len(caf_manager.key_map)} tipos de CAF cargados exitosamente.")

        click.echo("Parseando XML de entrada...")
        parser = XMLParser(input)
        parser.parse()
        
        click.echo("Limpiando firmas existentes...")
        cleaner = SignatureCleaner(parser.root, parser.namespaces)
        cleaner.clean_all_signatures()

        ted_resigner = TEDResigner(caf_manager)
        dte_resigner = DTEResigner(cert, cert_password, parser.namespaces)
        resigned_dtes = []
        
        for dte_element in parser.get_dte_elements():
            # If the DTE element is an Exportaciones, rename it to Documento for compliance
            if dte_element.tag == etree.QName(parser.namespaces['ns'], 'Exportaciones'):
                dte_element.tag = etree.QName(parser.namespaces['ns'], 'Documento')
                click.echo(f"  - Elemento <Exportaciones> renombrado a <Documento> para cumplimiento de esquema.")

            if non_interactive:
                update_dte_data_non_interactive(dte_element, parser.namespaces)
            else:
                update_dte_data_interactive(dte_element, parser.namespaces)

            extractor = DTEExtractor(dte_element, parser.namespaces)
            dte_data = extractor.extract_document_structure()
            ted_data = extractor.extract_ted_data()

            new_ted = ted_resigner.resign_ted(ted_data['dd_element'], parser.namespaces)
            new_dte = dte_resigner.resign_dte(dte_data, new_ted)
            resigned_dtes.append(new_dte)

        click.echo("-" * 40)
        click.echo("Firmando el SetDTE consolidado...")
        setdte_resigner = SetDTEResigner(cert, cert_password, parser.namespaces)
        final_envelope = setdte_resigner.resign_setdte(
            parser.get_envelope_structure(),
            parser.get_caratula(),
            resigned_dtes
        )

        click.echo(f"Guardando XML re-firmado en: {output}")
        xml_declaration = '<?xml version="1.0" encoding="ISO-8859-1"?>'
        final_xml_bytes = etree.tostring(final_envelope, encoding='ISO-8859-1', xml_declaration=False, pretty_print=True)
        
        with open(output, 'wb') as f:
            f.write(xml_declaration.encode('ISO-8859-1'))
            f.write(b'\n')
            f.write(final_xml_bytes)

        click.secho(f"\nProceso completado exitosamente!", fg='green')
        click.secho(f"Archivo guardado en: {output}", fg='cyan')

    except Exception as e:
        click.secho(f"\nError durante el proceso: {e}", fg='red', err=True)
        import traceback
        click.secho(traceback.format_exc(), fg='yellow', err=True)

@cli.command()
@click.option('--input', required=True, type=click.Path(exists=True), help='Ruta al archivo XML firmado que se desea verificar.')
def verify(input):
    """Verifica la integridad de las firmas de un archivo EnvioDTE usando xmlsec."""
    click.echo(f"Verificando firmas para el archivo: {input}")
    try:
        validator = SignatureValidator(input)
        validator.verify_all()
        click.secho("\nVERIFICACIÓN EXITOSA: Todas las firmas XMLDSig son correctas y coinciden con los datos.", fg='green', bold=True)

    except Exception as e:
        click.secho(f"\nERROR DE VALIDACIÓN: {e}", fg='red', err=True)
        import traceback
        click.secho(traceback.format_exc(), fg='yellow', err=True)


if __name__ == '__main__':
    cli()
