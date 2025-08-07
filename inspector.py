import xmlsec

print("--- xmlsec attributes ---")
for attr in dir(xmlsec):
    if not attr.startswith('__'):
        print(attr)