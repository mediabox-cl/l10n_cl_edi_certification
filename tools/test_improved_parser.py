#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para probar el parser mejorado de set de pruebas SII de forma independiente.
Permite validar el funcionamiento antes de integrarlo con Odoo.
"""

import os
import sys
import json
from sii_test_set_parser_improved import SiiTestSetParser

def main():
    if len(sys.argv) < 2:
        print("Uso: python test_improved_parser.py <ruta_al_archivo>")
        return 1
    
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: El archivo '{file_path}' no existe.")
        return 1
    
    print(f"Procesando archivo: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
            content = file.read()
        
        parser = SiiTestSetParser(content)
        result = parser.parse()
        
        # Guardar resultado en un archivo JSON para revisión
        output_path = f"{os.path.splitext(file_path)[0]}_improved_parsed.json"
        with open(output_path, 'w', encoding='utf-8') as out_file:
            json.dump(result, out_file, indent=2, ensure_ascii=False)
        
        print(f"Resultado guardado en: {output_path}")
        
        # Mostrar un resumen
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
        print(f"Error al procesar el archivo: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())