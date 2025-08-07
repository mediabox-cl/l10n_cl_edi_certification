# Proceso de Firma Ideal para DTEs - Especificación SII Chile

## Resumen Ejecutivo

Este documento describe el proceso de firma **triple** requerido por el SII para documentos consolidados (SetDTE), basado en el análisis del módulo `l10n_cl_edi` y la especificación técnica del SII.

## Arquitectura Triple de Firma

### Orden de Ejecución (CRÍTICO)
```
1. Firma FRMT (Timbre Electrónico) ← Usa clave privada CAF
2. Firma XMLDSig Individual (DTE) ← Usa certificado digital empresa
3. Firma XMLDSig Consolidada (SetDTE) ← Usa certificado digital empresa
```

---

## 1. PRIMERA FIRMA: Timbre Electrónico (TED)

### Propósito
Validar la autenticidad del folio autorizado por el SII usando la clave privada del CAF.

### Proceso Detallado

#### 1.1 Construcción del Elemento DD
```xml
<DD>
    <RE>RUT-EMISOR</RE>
    <TD>TIPO-DTE</TD>
    <F>FOLIO</F>
    <FE>FECHA-EMISION</FE>
    <RR>RUT-RECEPTOR</RR>
    <RSR>RAZON-SOCIAL-RECEPTOR</RSR>
    <MNT>MONTO-TOTAL</MNT>
    <IT1>PRIMER-ITEM</IT1>
    <CAF version="1.0">
        <!-- CAF completo con clave pública -->
    </CAF>
    <TSTED>TIMESTAMP</TSTED>
</DD>
```

#### 1.2 Algoritmo de Firma FRMT
```python
def generar_firma_frmt(dd_element, clave_privada_caf):
    # 1. Aplanar DD removiendo espacios entre elementos
    dd_flattened = flatten_xml(dd_element)  # <DD><RE>...</RE><TD>...</TD>...</DD>
    
    # 2. Escapar caracteres especiales (CRÍTICO)
    dd_escaped = escape_xml_chars(dd_flattened)
    # & → &amp;, < → &lt;, > → &gt;, " → &quot;, ' → &apos;
    
    # 3. Codificar en ISO-8859-1 (NO UTF-8)
    dd_bytes = dd_escaped.encode('ISO-8859-1')
    
    # 4. Firmar con SHA1withRSA usando clave privada CAF
    signature_bytes = sign_sha1_rsa(dd_bytes, clave_privada_caf)
    
    # 5. Codificar en Base64
    frmt_signature = base64.b64encode(signature_bytes).decode('ascii')
    
    return frmt_signature
```

#### 1.3 Estructura Final TED
```xml
<TED version="1.0">
    <DD>
        <!-- Contenido del DD -->
    </DD>
    <FRMT algoritmo="SHA1withRSA">FIRMA-CALCULADA</FRMT>
</TED>
```

---

## 2. SEGUNDA FIRMA: XMLDSig Individual (DTE)

### Propósito
Validar la integridad y autenticidad de cada documento usando el certificado digital de la empresa.

### Proceso Detallado

#### 2.1 Preparación del Documento
```xml
<DTE xmlns="http://www.sii.cl/SiiDte" version="1.0">
    <Documento ID="F{FOLIO}T{TIPO}">
        <Encabezado>...</Encabezado>
        <Detalle>...</Detalle>
        <TED>...</TED>  <!-- Ya firmado con FRMT -->
        <TmstFirma>TIMESTAMP</TmstFirma>
    </Documento>
</DTE>
```

#### 2.2 Algoritmo de Firma XMLDSig
```python
def firmar_dte_individual(dte_xml, certificado_digital, document_id):
    # 1. Canonicalizar el elemento Documento
    documento_element = extract_element_by_id(dte_xml, document_id)
    canonicalized_doc = canonicalize_c14n(documento_element)
    
    # 2. Calcular Digest SHA1
    digest = hashlib.sha1(canonicalized_doc.encode('utf-8')).digest()
    digest_b64 = base64.b64encode(digest).decode('ascii')
    
    # 3. Construir SignedInfo
    signed_info = f"""
    <SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
        <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
        <SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
        <Reference URI="#{document_id}">
            <Transforms>
                <Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
            </Transforms>
            <DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
            <DigestValue>{digest_b64}</DigestValue>
        </Reference>
    </SignedInfo>
    """
    
    # 4. Canonicalizar SignedInfo
    canonicalized_signed_info = canonicalize_c14n(signed_info)
    
    # 5. Firmar SignedInfo con RSA-SHA1
    signature_bytes = sign_rsa_sha1(canonicalized_signed_info, certificado_digital.private_key)
    signature_b64 = base64.b64encode(signature_bytes).decode('ascii')
    
    # 6. Construir elemento Signature completo
    signature_element = f"""
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
        {signed_info}
        <SignatureValue>{signature_b64}</SignatureValue>
        <KeyInfo>
            <KeyValue>
                <RSAKeyValue>
                    <Modulus>{certificado_digital.public_key.n_b64}</Modulus>
                    <Exponent>{certificado_digital.public_key.e_b64}</Exponent>
                </RSAKeyValue>
            </KeyValue>
            <X509Data>
                <X509Certificate>{certificado_digital.certificate_b64}</X509Certificate>
            </X509Data>
        </KeyInfo>
    </Signature>
    """
    
    # 7. Insertar Signature en el DTE
    return insert_signature_in_dte(dte_xml, signature_element)
```

#### 2.3 Consideraciones Críticas
- **Reference URI**: Debe coincidir exactamente con el ID del documento (`#F{FOLIO}T{TIPO}`)
- **Canonicalización**: Usar C14N estándar, no exclusivo
- **Encoding**: Mantener ISO-8859-1 consistente
- **Namespaces**: Evitar declaraciones redundantes

---

## 3. TERCERA FIRMA: XMLDSig Consolidada (SetDTE)

### Propósito
Validar la integridad del envío consolidado completo.

### Proceso Detallado

#### 3.1 Estructura del SetDTE
```xml
<EnvioDTE xmlns="http://www.sii.cl/SiiDte" version="1.0">
    <SetDTE ID="SetDoc">
        <Caratula>...</Caratula>
        <DTE>...</DTE>  <!-- Ya firmado individualmente -->
        <DTE>...</DTE>  <!-- Ya firmado individualmente -->
        <!-- Más DTEs -->
    </SetDTE>
</EnvioDTE>
```

#### 3.2 Algoritmo de Firma SetDTE
```python
def firmar_setdte_consolidado(setdte_xml, certificado_digital):
    # 1. Canonicalizar el elemento SetDTE
    setdte_element = extract_element_by_id(setdte_xml, "SetDoc")
    canonicalized_setdte = canonicalize_c14n(setdte_element)
    
    # 2. Calcular Digest SHA1
    digest = hashlib.sha1(canonicalized_setdte.encode('utf-8')).digest()
    digest_b64 = base64.b64encode(digest).decode('ascii')
    
    # 3. Construir SignedInfo
    signed_info = f"""
    <SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
        <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
        <SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
        <Reference URI="#SetDoc">
            <Transforms>
                <Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
            </Transforms>
            <DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
            <DigestValue>{digest_b64}</DigestValue>
        </Reference>
    </SignedInfo>
    """
    
    # 4. Resto del proceso igual a firma individual
    # ... (mismo algoritmo)
    
    # 5. Insertar Signature al final del SetDTE
    return insert_signature_in_setdte(setdte_xml, signature_element)
```

---

## 4. MANEJO DE CAF (Código de Autorización de Folios)

### ¿Se puede extraer del DTE existente?

**SÍ, PARCIALMENTE**. Del DTE generado por Odoo se puede extraer:

#### 4.1 Información Disponible en el DTE
```xml
<CAF version="1.0">
    <DA>
        <RE>RUT-EMISOR</RE>
        <RS>RAZON-SOCIAL</RS>
        <TD>TIPO-DTE</TD>
        <RNG>
            <D>FOLIO-DESDE</D>
            <H>FOLIO-HASTA</H>
        </RNG>
        <FA>FECHA-AUTORIZACION</FA>
        <RSAPK>
            <M>MODULO-CLAVE-PUBLICA</M>
            <E>EXPONENTE-CLAVE-PUBLICA</E>
        </RSAPK>
        <IDK>ID-CLAVE</IDK>
    </DA>
    <FRMA algoritmo="SHA1withRSA">FIRMA-SII</FRMA>
</CAF>
```

#### 4.2 Lo que NO está disponible
- **Clave privada CAF**: Necesaria para firmar el TED
- **Certificado completo**: Solo tenemos la clave pública

### Opciones de Implementación

#### Opción 1: Extraer CAF del DTE + Clave Privada Externa
```python
def extraer_caf_de_dte(dte_xml):
    # Extraer elemento CAF completo del DTE
    caf_element = extract_caf_from_dte(dte_xml)
    
    # Necesitamos la clave privada de otra fuente
    # (archivo .key proporcionado por el SII)
    private_key = load_caf_private_key("path/to/caf.key")
    
    return {
        'caf_data': caf_element,
        'private_key': private_key
    }
```

#### Opción 2: Implementar Consumo Propio de CAF
```python
def cargar_caf_completo(caf_file_path):
    # Cargar archivo CAF completo del SII
    with open(caf_file_path, 'rb') as f:
        caf_data = f.read()
    
    # Parsear CAF y extraer clave privada
    caf_parsed = parse_caf_file(caf_data)
    
    return {
        'public_data': caf_parsed['DA'],
        'private_key': caf_parsed['private_key'],
        'sii_signature': caf_parsed['FRMA']
    }
```

### Recomendación
**Usar Opción 1** por simplicidad:
- Extraer CAF del DTE generado por Odoo
- Cargar clave privada del archivo .key del SII
- Combinar ambos para la firma FRMT

---

## 5. ARQUITECTURA DE APLICACIÓN PYTHON

### 5.1 Estructura Propuesta
```
dte_signer/
├── main.py
├── models/
│   ├── dte_document.py
│   ├── caf_handler.py
│   └── certificate_handler.py
├── signers/
│   ├── frmt_signer.py
│   ├── xmldsig_signer.py
│   └── setdte_signer.py
├── utils/
│   ├── xml_canonicalizer.py
│   ├── xml_validator.py
│   └── encoding_handler.py
└── tests/
    └── test_signing_process.py
```

### 5.2 Flujo Principal
```python
def process_dte_batch(input_xml_path, output_xml_path, caf_path, cert_path):
    # 1. Cargar XML sin firmar
    dte_batch = load_dte_batch(input_xml_path)
    
    # 2. Cargar CAF y certificado
    caf_handler = CAFHandler(caf_path)
    cert_handler = CertificateHandler(cert_path)
    
    # 3. Procesar cada DTE
    signed_dtes = []
    for dte in dte_batch.dtes:
        # 3.1 Firmar TED con CAF
        ted_signed = FRMTSigner.sign_ted(dte.ted, caf_handler)
        dte.ted = ted_signed
        
        # 3.2 Firmar DTE individual
        dte_signed = XMLDSigSigner.sign_dte(dte, cert_handler)
        signed_dtes.append(dte_signed)
    
    # 4. Construir SetDTE
    setdte = build_setdte(signed_dtes)
    
    # 5. Firmar SetDTE consolidado
    setdte_signed = SetDTESigner.sign_setdte(setdte, cert_handler)
    
    # 6. Guardar resultado
    save_signed_xml(setdte_signed, output_xml_path)
```

### 5.3 Librerías Recomendadas
```python
# requirements.txt
lxml>=4.6.0              # Manipulación XML
xmlsec>=1.3.0            # Firmas XMLDSig
cryptography>=3.4.0     # Operaciones criptográficas
pyOpenSSL>=20.0.0        # Manejo de certificados
```

---

## 6. PUNTOS CRÍTICOS DE IMPLEMENTACIÓN

### 6.1 Encoding Consistente
- **SIEMPRE** usar ISO-8859-1
- **NUNCA** mezclar UTF-8 con ISO-8859-1
- Manejar caracteres especiales correctamente

### 6.2 Canonicalización
- Usar C14N estándar (no exclusivo)
- Preservar orden de atributos
- Mantener espacios en blanco significativos

### 6.3 Validación
- Verificar cada firma independientemente
- Validar estructura XML contra schema
- Confirmar que Reference URI coincide con ID

### 6.4 Debugging
- Logging detallado de cada paso
- Guardar XML intermedio para análisis
- Validar contra ejemplos oficiales del SII

---

## 7. EJEMPLO DE USO

```python
# Ejemplo de implementación
from dte_signer import DTESigner

# Configurar firmador
signer = DTESigner(
    caf_path="caf_33_001_020.xml",
    cert_path="certificado_empresa.p12",
    cert_password="password123"
)

# Procesar batch
result = signer.process_batch(
    input_xml="batch_sin_firmar.xml",
    output_xml="batch_firmado.xml"
)

if result.success:
    print(f"Batch firmado exitosamente: {result.output_path}")
    print(f"DTEs procesados: {result.dte_count}")
else:
    print(f"Error: {result.error_message}")
```

---

## 8. CONSIDERACIONES FINALES

### Ventajas de App Separada
- **Control total** sobre el proceso de firma
- **Debugging detallado** de cada paso
- **Independencia** del módulo Odoo
- **Flexibilidad** para ajustes específicos

### Integración con Odoo
- Odoo genera DTEs sin firmar
- App Python firma y valida
- Resultado se sube de vuelta a Odoo

Esta arquitectura permite un control granular sobre el proceso de firma y facilita la resolución de problemas específicos del SII.