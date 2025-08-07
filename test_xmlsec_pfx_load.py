import xmlsec

pfx_file = "test_cert.pfx"
pfx_password = "testpass"

print("Probando constantes de xmlsec.KeyFormat para cargar PFX...")

found_correct_constant = False
for attr_name in dir(xmlsec.KeyFormat):
    if not attr_name.startswith('__'):
        constant = getattr(xmlsec.KeyFormat, attr_name)
        try:
            key = xmlsec.Key.from_file(pfx_file, constant, pfx_password)
            print(f"  ÉXITO: xmlsec.KeyFormat.{attr_name} cargó la clave.")
            found_correct_constant = True
        except xmlsec.Error as e:
            print(f"  FALLO: xmlsec.KeyFormat.{attr_name} - {e}")
        except Exception as e:
            print(f"  ERROR INESPERADO: xmlsec.KeyFormat.{attr_name} - {e}")

if not found_correct_constant:
    print("\nNo se encontró ninguna constante de xmlsec.KeyFormat que cargue el PFX.")

