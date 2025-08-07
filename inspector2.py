import xmlsec

print("--- xmlsec attributes ---")
for attr in dir(xmlsec):
    if not attr.startswith('__'):
        print(attr)

if hasattr(xmlsec, 'KeyFormat'):
    print("\n--- xmlsec.KeyFormat attributes ---")
    for attr in dir(xmlsec.KeyFormat):
        if not attr.startswith('__'):
            print(attr)
else:
    print("\n--- xmlsec has no attribute KeyFormat ---")

