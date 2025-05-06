#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para probar el parser de set de pruebas SII de forma independiente.
Permite validar el funcionamiento antes de integrarlo con Odoo.
"""

import os
import sys
import json
from sii_test_set_parser import SiiTestSetParser

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_parser.py <ruta_al_archivo>")
        return 1
    
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: El archivo '{file_path}' no existe.")
        return 1
    
    print(f"Procesando archivo: {file_path}")
    
    content = None
    encodings_to_try = ['utf-8', 'latin-1']

    for enc in encodings_to_try:
        try:
            print(f"Intentando leer el archivo con codificación: {enc}")
            with open(file_path, 'r', encoding=enc) as file:
                content = file.read()
            print(f"Archivo leído exitosamente con {enc}")
            break 
        except UnicodeDecodeError:
            print(f"Falló la decodificación con {enc}.")
        except FileNotFoundError:
            print(f"Error: El archivo '{file_path}' no fue encontrado al intentar leer con {enc}.")
            content = None 
            break 
        except Exception as e:
            print(f"Error inesperado al leer el archivo '{file_path}' con {enc}: {e}")
            content = None 
            break

    if content is None:
        print(f"Error: No se pudo leer el archivo '{file_path}' con las codificaciones probadas ({', '.join(encodings_to_try)}).")
        return 1
    
    try:
        parser = SiiTestSetParser(content)
        result = parser.parse()
        
        # Guardar resultado en un archivo JSON para revisión
        output_path = f"{os.path.splitext(file_path)[0]}_parsed.json"
        with open(output_path, 'w', encoding='utf-8') as out_file:
            json.dump(result, out_file, indent=2, ensure_ascii=False)
        
        # Guardar resultado en un archivo de texto formateado para mejor lectura
        txt_output_path = f"{os.path.splitext(file_path)[0]}_parsed.txt"
        with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write("=========================================\n")
            txt_file.write("RESULTADO DEL ANÁLISIS DEL SET DE PRUEBAS\n")
            txt_file.write("=========================================\n\n")
            
            # Información general
            txt_file.write(f"Archivo procesado: {file_path}\n")
            txt_file.write(f"Sets encontrados: {len(result['sets'])}\n")
            txt_file.write(f"Casos totales: {len(result['cases'])}\n\n")
            
            # Detallar cada set
            txt_file.write("DETALLE DE SETS DE PRUEBA\n")
            txt_file.write("========================\n\n")
            
            for i, set_data in enumerate(result['sets']):
                txt_file.write(f"SET {i+1}: {set_data['set_type'].upper()}\n")
                txt_file.write(f"Número de atención: {set_data['attention_number']}\n")
                txt_file.write(f"Casos en este set: {len(set_data['cases'])}\n")
                txt_file.write("-" * 50 + "\n\n")
            
            # Detallar cada caso
            txt_file.write("DETALLE DE CASOS\n")
            txt_file.write("===============\n\n")
            
            for i, case in enumerate(result['cases']):
                txt_file.write(f"CASO {i+1}: {case['case_number']}\n")
                txt_file.write(f"Tipo de Set: {case['set_type']}\n")
                txt_file.write(f"Número de atención: {case['set_attention_number']}\n")
                txt_file.write(f"Tipo de documento: {case['document_type'] or 'No especificado'}\n")
                
                if case.get('reference_document'):
                    txt_file.write(f"Referencia a: {case['reference_document']}\n")
                    if case.get('reference_id'):
                        txt_file.write(f"ID de referencia: {case['reference_id']}\n")
                
                if case.get('reference_reason'):
                    txt_file.write(f"Razón de referencia: {case['reference_reason']}\n")
                
                if case.get('motivo'):
                    txt_file.write(f"Motivo: {case['motivo']}\n")
                
                if case.get('traslado_por'):
                    txt_file.write(f"Traslado por: {case['traslado_por']}\n")
                
                if case.get('global_discount'):
                    txt_file.write(f"Descuento global: {case['global_discount']}%\n")
                
                # Información adicional
                if case['additional_info']:
                    txt_file.write("\nInformación Adicional:\n")
                    for key, value in case['additional_info'].items():
                        txt_file.write(f"  {key}: {value}\n")
                
                # Ítems
                txt_file.write(f"\nÍtems ({len(case['items'])}):\n")
                for j, item in enumerate(case['items']):
                    txt_file.write(f"  Ítem {j+1}: {item.get('name', 'Sin nombre')}\n")
                    
                    if 'quantity' in item:
                        txt_file.write(f"    Cantidad: {item['quantity']}\n")
                    
                    if 'uom' in item and item['uom']:
                        txt_file.write(f"    Unidad de medida: {item['uom']}\n")
                    
                    if 'price_unit' in item:
                        txt_file.write(f"    Precio unitario: {item['price_unit']}\n")
                    
                    if 'discount_percent' in item:
                        txt_file.write(f"    Descuento: {item['discount_percent']}%\n")
                    
                    txt_file.write(f"    Exento: {'Sí' if item.get('is_exempt') else 'No'}\n")
                
                txt_file.write("\n" + "=" * 70 + "\n\n")
            
            # Análisis de referencias entre documentos
            txt_file.write("ANÁLISIS DE RELACIONES ENTRE DOCUMENTOS\n")
            txt_file.write("======================================\n\n")
            
            references_found = 0
            for case in result['cases']:
                if case.get('reference_id'):
                    references_found += 1
                    txt_file.write(f"Documento {case['case_number']} ({case.get('document_type', 'Sin tipo')}) referencia a {case['reference_id']}\n")
                    txt_file.write(f"  Razón: {case.get('reference_reason', case.get('reference_document', 'No especificada'))}\n\n")
            
            if references_found == 0:
                txt_file.write("No se encontraron referencias entre documentos.\n\n")
            else:
                txt_file.write(f"Total de referencias encontradas: {references_found}\n\n")
            
            # Resumen por tipo de documento
            txt_file.write("RESUMEN POR TIPO DE DOCUMENTO\n")
            txt_file.write("============================\n\n")
            
            document_types = {}
            for case in result['cases']:
                doc_type = case.get('document_type', 'unknown')
                if doc_type:
                    document_types[doc_type] = document_types.get(doc_type, 0) + 1
            
            for doc_type, count in document_types.items():
                txt_file.write(f"{doc_type}: {count} documento(s)\n")
        
        print(f"Resultado guardado en: {output_path}")
        print(f"Reporte detallado guardado en: {txt_output_path}")
        
        # Mostrar un resumen en la consola
        print("\nResumen del parsing:")
        print(f"Sets encontrados: {len(result['sets'])}")
        print(f"Casos encontrados: {len(result['cases'])}")
        
        # Mostrar los sets
        print("\nSets:")
        for i, set_data in enumerate(result['sets']):
            print(f"  {i+1}. Tipo: {set_data['set_type']} - Atención: {set_data['attention_number']} - Casos: {len(set_data['cases'])}")
        
        # Mostrar algunos casos como ejemplo
        print("\nEjemplos de casos:")
        for i, case in enumerate(result['cases'][:5]):  # Mostrar los primeros 5
            print(f"  {i+1}. Caso {case['case_number']} - Documento: {case['document_type']}")
            if case.get('reference_document'):
                print(f"     Referencia: {case['reference_document']}")
                if case.get('reference_id'):
                    print(f"     Referencia a: {case['reference_id']}")
            print(f"     Items: {len(case['items'])}")
            if case['items']:
                for j, item in enumerate(case['items'][:2]):  # Mostrar solo primeros 2 items
                    print(f"       - {item.get('name', 'Sin nombre')}")
                    if 'quantity' in item:
                        print(f"         Cantidad: {item['quantity']}")
                    if 'price_unit' in item:
                        print(f"         Precio: {item['price_unit']}")
        
        if len(result['cases']) > 5:
            print(f"  ... y {len(result['cases']) - 5} más")
        
        return 0
    except Exception as e:
        print(f"Error durante el parseo o escritura de resultados: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())