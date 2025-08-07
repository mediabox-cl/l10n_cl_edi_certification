# Especificación: Aplicación Re-Firmador de DTEs - SII Chile

## 1. Resumen Ejecutivo

### Objetivo
Desarrollar una aplicación Python que tome el XML **YA GENERADO por Odoo** (como `BASICO_762352915.xml`) y **regenere las firmas correctamente** para resolver los problemas de rechazo del SII.

### Problema a Resolver
- El XML generado por Odoo contiene toda la información necesaria pero las firmas fallan la validación individual del SII
- Necesidad de extraer, limpiar y re-firmar manteniendo toda la información existente

### Solución Propuesta
Aplicación que **parsea el XML existente**, **extrae todos los datos**, **limpia las firmas problemáticas** y **re-firma correctamente**.

---

## 2. Análisis del XML de Entrada

### 2.1 Estructura Actual del XML
```xml
<?xml version="1.0" encoding="ISO-8859-1" ?>
<EnvioDTE xmlns="http://www.sii.cl/SiiDte" version="1.0">
  <SetDTE ID="SetDoc">
    <Caratula>...</Caratula>
    <DTE version="1.0">
      <Documento ID="F17T33">
        <Encabezado>...</Encabezado>
        <Detalle>...</Detalle>
        <Referencia>...</Referencia>
        <TED version="1.0">          ← YA EXISTE
          <DD>...</DD>
          <FRMT>...</FRMT>           ← FIRMA PROBLEMÁTICA
        </TED>
        <TmstFirma>...</TmstFirma>
      </Documento>
      <Signature>...</Signature>      ← FIRMA PROBLEMÁTICA
    </DTE>
    <!-- Más DTEs -->
    <Signature>...</Signature>        ← FIRMA PROBLEMÁTICA
  </SetDTE>
</EnvioDTE>
```

### 2.2 Elementos a Extraer y Reutilizar

**✅ REUTILIZAR (Mantener exactamente igual):**
- `<Caratula>` completa
- `<Encabezado>` de cada DTE
- `<Detalle>` de cada DTE 
- `<Referencia>` de cada DTE
- `<TmstFirma>` de cada DTE
- **Elemento `<DD>` dentro del TED** (datos del timbre)
- **Elemento `<CAF>` dentro del TED** (datos del CAF)

**❌ REGENERAR (Firmas problemáticas):**
- `<FRMT>` dentro del TED
- `<Signature>` de cada DTE individual
- `<Signature>` del SetDTE

### 2.3 Información Disponible en el XML

**Del TED existente podemos extraer:**
```xml
<CAF version="1.0">
    <DA>
        <RE>76235291-5</RE>
        <RS>DISEÑO Y ENTRETENIMIENTOS WITHIN PLAY LI</RS>
        <TD>33</TD>
        <RNG><D>1</D><H>20</H></RNG>
        <FA>2025-04-11</FA>
        <RSAPK>
            <M>wLiKZijh1FweDUFLVO+J/KEI...</M>
            <E>Aw==</E>
        </RSAPK>
        <IDK>100</IDK>
    </DA>
    <FRMA algoritmo="SHA1withRSA">UyDhGevCqhJrA+lEOkIDMm2...</FRMA>
</CAF>
```

**Del DD existente podemos extraer:**
```xml
<DD>
    <RE>76235291-5</RE>
    <TD>33</TD>
    <F>17</F>
    <FE>2025-07-08</FE>
    <RR>77447842-6</RR>
    <RSR>Baca Juegos y Accesorios SPA</RSR>
    <MNT>1188861</MNT>
    <IT1>Cajón AFECTO</IT1>
    <CAF>...</CAF>
    <TSTED>2025-07-15T11:06:14</TSTED>
</DD>
```

---

## 3. Arquitectura de la Aplicación

### 3.1 Flujo Principal

```
[XML Odoo] → [Parser] → [Extractor] → [Limpiador] → [Re-Firmador] → [XML Corregido]
     ↓           ↓          ↓            ↓             ↓              ↓
- TED con     - Extraer   - Reutilizar  - Remover    - Re-firmar   - TED correcto
  FRMT malo   - CAF       - DD, CAF     - Firmas     - FRMT        - XMLDSig válido
- XMLDSig     - Extraer   - Reutilizar  - Remover    - Re-firmar   - SetDTE válido
  malo        - Datos     - Estructura  - Signatures - Individual
            - Validar   - Mantener    - Limpiar    - Re-firmar
                        - Orden       - Namespaces - Consolidado
```

### 3.2 Componentes Principales

```
dte_refirmer/
├── main.py                    # CLI principal
├── parsers/
│   ├── xml_parser.py          # Parser del XML de Odoo
│   ├── dte_extractor.py       # Extractor de datos DTE
│   └── caf_extractor.py       # Extractor de datos CAF
├── cleaners/
│   ├── signature_cleaner.py   # Limpiador de firmas
│   ├── namespace_cleaner.py   # Limpiador de namespaces
│   └── xml_normalizer.py      # Normalizador XML
├── signers/
│   ├── ted_resigner.py        # Re-firmador TED/FRMT
│   ├── dte_resigner.py        # Re-firmador DTE individual
│   └── setdte_resigner.py     # Re-firmador SetDTE
├── validators/
│   ├── structure_validator.py # Validador de estructura
│   └── signature_validator.py # Validador de firmas
└── utils/
    ├── caf_loader.py          # Cargador de CAF externo
    └── cert_loader.py         # Cargador de certificados
```

---

## 4. Especificación de Componentes

### 4.1 XMLParser

**Responsabilidad**: Parsear el XML de Odoo y extraer elementos estructurales

```python
class XMLParser:
    def __init__(self, xml_file_path: str):
        self.xml_path = xml_file_path
        self.root = None
        self.setdte_element = None
        self.caratula = None
        self.dte_elements = []
    
    def parse(self) -> None:
        """Parsear XML y extraer elementos principales"""
        
    def get_envelope_structure(self) -> Dict:
        """Obtener estructura del EnvioDTE"""
        return {
            'namespaces': self.root.nsmap,
            'attributes': self.root.attrib,
            'version': self.root.get('version')
        }
    
    def get_caratula(self) -> etree.Element:
        """Extraer carátula completa (reutilizar tal cual)"""
        
    def get_dte_elements(self) -> List[etree.Element]:
        """Extraer todos los elementos DTE"""
```

### 4.2 DTEExtractor

**Responsabilidad**: Extraer datos específicos de cada DTE

```python
class DTEExtractor:
    def __init__(self, dte_element: etree.Element):
        self.dte_element = dte_element
        self.documento = None
        self.document_id = None
    
    def extract_document_structure(self) -> Dict:
        """Extraer estructura del documento (sin firmas)"""
        return {
            'id': self.document_id,
            'encabezado': self.extract_encabezado(),
            'detalles': self.extract_detalles(),
            'referencias': self.extract_referencias(),
            'timestamp': self.extract_timestamp()
        }
    
    def extract_encabezado(self) -> etree.Element:
        """Extraer encabezado completo (reutilizar tal cual)"""
        
    def extract_detalles(self) -> List[etree.Element]:
        """Extraer todos los detalles (reutilizar tal cual)"""
        
    def extract_referencias(self) -> List[etree.Element]:
        """Extraer referencias (reutilizar tal cual)"""
        
    def extract_ted_data(self) -> Dict:
        """Extraer datos del TED existente"""
        return {
            'dd_element': self.extract_dd_element(),
            'caf_element': self.extract_caf_element(),
            'timestamp': self.extract_ted_timestamp()
        }
    
    def extract_dd_element(self) -> etree.Element:
        """Extraer DD completo (reutilizar para re-firmar)"""
        
    def extract_caf_element(self) -> etree.Element:
        """Extraer CAF completo (reutilizar tal cual)"""
```

### 4.3 CAFExtractor

**Responsabilidad**: Extraer información del CAF para validación

```python
class CAFExtractor:
    def __init__(self, caf_element: etree.Element):
        self.caf_element = caf_element
    
    def extract_caf_data(self) -> Dict:
        """Extraer datos del CAF para validación"""
        return {
            'rut_emisor': self.get_rut_emisor(),
            'tipo_dte': self.get_tipo_dte(),
            'rango_folios': self.get_rango_folios(),
            'fecha_autorizacion': self.get_fecha_autorizacion(),
            'public_key': self.get_public_key(),
            'idk': self.get_idk(),
            'sii_signature': self.get_sii_signature()
        }
    
    def validate_folio(self, folio: int) -> bool:
        """Validar que el folio esté en rango"""
        
    def get_public_key(self) -> Dict:
        """Extraer clave pública RSA"""
        return {
            'modulus': self.caf_element.find('.//M').text,
            'exponent': self.caf_element.find('.//E').text
        }
```

### 4.4 SignatureCleaner

**Responsabilidad**: Limpiar firmas problemáticas del XML

```python
class SignatureCleaner:
    def __init__(self, xml_root: etree.Element):
        self.root = xml_root
    
    def clean_all_signatures(self) -> None:
        """Limpiar todas las firmas problemáticas"""
        self.clean_frmt_signatures()
        self.clean_dte_signatures()
        self.clean_setdte_signature()
    
    def clean_frmt_signatures(self) -> None:
        """Remover elementos FRMT de todos los TED"""
        frmt_elements = self.root.findall('.//FRMT')
        for frmt in frmt_elements:
            frmt.getparent().remove(frmt)
    
    def clean_dte_signatures(self) -> None:
        """Remover firmas XMLDSig de DTEs individuales"""
        dte_elements = self.root.findall('.//{http://www.sii.cl/SiiDte}DTE')
        for dte in dte_elements:
            signatures = dte.findall('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
            for sig in signatures:
                sig.getparent().remove(sig)
    
    def clean_setdte_signature(self) -> None:
        """Remover firma XMLDSig del SetDTE"""
        setdte = self.root.find('.//{http://www.sii.cl/SiiDte}SetDTE')
        signatures = setdte.findall('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
        for sig in signatures:
            sig.getparent().remove(sig)
```

### 4.5 TEDResigner

**Responsabilidad**: Re-firmar TED usando DD existente + clave CAF externa

```python
class TEDResigner:
    def __init__(self, caf_private_key_path: str):
        self.caf_private_key = self.load_caf_private_key(caf_private_key_path)
    
    def resign_ted(self, dd_element: etree.Element, caf_element: etree.Element) -> etree.Element:
        """Re-firmar TED usando DD y CAF existentes"""
        
        # 1. Reutilizar DD tal como está
        dd_copy = copy.deepcopy(dd_element)
        
        # 2. Actualizar timestamp si es necesario
        tsted = dd_copy.find('.//TSTED')
        if tsted is not None:
            tsted.text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        # 3. Generar nueva firma FRMT
        frmt_signature = self.generate_frmt_signature(dd_copy)
        
        # 4. Construir TED completo
        ted_element = etree.Element('TED', version='1.0')
        ted_element.append(dd_copy)
        
        frmt_element = etree.SubElement(ted_element, 'FRMT', algoritmo='SHA1withRSA')
        frmt_element.text = frmt_signature
        
        return ted_element
    
    def generate_frmt_signature(self, dd_element: etree.Element) -> str:
        """Generar firma FRMT usando algorítmo SII"""
        # Mismo algoritmo que en especificación anterior
        # 1. Aplanar DD
        # 2. Escapar caracteres
        # 3. Codificar ISO-8859-1
        # 4. Firmar SHA1withRSA
        # 5. Base64
```

### 4.6 DTEResigner

**Responsabilidad**: Re-firmar DTEs individuales con nueva estructura

```python
class DTEResigner:
    def __init__(self, certificate_path: str, cert_password: str):
        self.certificate = self.load_certificate(certificate_path, cert_password)
    
    def resign_dte(self, dte_data: Dict, ted_element: etree.Element) -> etree.Element:
        """Re-construir y re-firmar DTE individual"""
        
        # 1. Construir DTE limpio
        dte_element = etree.Element('DTE', version='1.0')
        
        # 2. Construir Documento
        documento = etree.SubElement(dte_element, 'Documento', ID=dte_data['id'])
        
        # 3. Agregar elementos reutilizados
        documento.append(dte_data['encabezado'])
        for detalle in dte_data['detalles']:
            documento.append(detalle)
        for referencia in dte_data['referencias']:
            documento.append(referencia)
        
        # 4. Agregar TED re-firmado
        documento.append(ted_element)
        
        # 5. Agregar timestamp
        tmst_element = etree.SubElement(documento, 'TmstFirma')
        tmst_element.text = dte_data['timestamp']
        
        # 6. Generar firma XMLDSig
        signature = self.generate_xmldsig_signature(documento, dte_data['id'])
        dte_element.append(signature)
        
        return dte_element
    
    def generate_xmldsig_signature(self, documento: etree.Element, doc_id: str) -> etree.Element:
        """Generar firma XMLDSig para documento"""
        # Mismo algoritmo que en especificación anterior
```

### 4.7 SetDTEResigner

**Responsabilidad**: Re-firmar SetDTE consolidado

```python
class SetDTEResigner:
    def __init__(self, certificate_path: str, cert_password: str):
        self.certificate = self.load_certificate(certificate_path, cert_password)
    
    def resign_setdte(self, envelope_data: Dict, caratula: etree.Element, dtes: List[etree.Element]) -> etree.Element:
        """Re-construir y re-firmar SetDTE consolidado"""
        
        # 1. Construir EnvioDTE
        envelope = etree.Element('EnvioDTE', nsmap=envelope_data['namespaces'])
        for attr, value in envelope_data['attributes'].items():
            envelope.set(attr, value)
        
        # 2. Construir SetDTE
        setdte = etree.SubElement(envelope, 'SetDTE', ID='SetDoc')
        
        # 3. Agregar carátula reutilizada
        setdte.append(caratula)
        
        # 4. Agregar DTEs re-firmados
        for dte in dtes:
            setdte.append(dte)
        
        # 5. Generar firma XMLDSig del SetDTE
        signature = self.generate_xmldsig_signature(setdte, 'SetDoc')
        setdte.append(signature)
        
        return envelope
```

---

## 5. Uso de la Aplicación

### 5.1 Comando Principal

```bash
python -m dte_refirmer resign \
    --input /path/to/BASICO_762352915.xml \
    --output /path/to/BASICO_762352915_refirmado.xml \
    --caf-key /path/to/caf_private.key \
    --cert /path/to/certificate.pfx \
    --cert-password "password"
```

### 5.2 Flujo de Procesamiento

```python
def main_resign_process(input_xml, output_xml, caf_key, cert_path, cert_password):
    # 1. Parsear XML de Odoo
    parser = XMLParser(input_xml)
    parser.parse()
    
    # 2. Extraer estructura del envelope
    envelope_data = parser.get_envelope_structure()
    caratula = parser.get_caratula()
    
    # 3. Limpiar firmas problemáticas
    cleaner = SignatureCleaner(parser.root)
    cleaner.clean_all_signatures()
    
    # 4. Procesar cada DTE
    ted_resigner = TEDResigner(caf_key)
    dte_resigner = DTEResigner(cert_path, cert_password)
    
    resigned_dtes = []
    for dte_element in parser.get_dte_elements():
        # Extraer datos
        extractor = DTEExtractor(dte_element)
        dte_data = extractor.extract_document_structure()
        ted_data = extractor.extract_ted_data()
        
        # Re-firmar TED
        new_ted = ted_resigner.resign_ted(ted_data['dd_element'], ted_data['caf_element'])
        
        # Re-firmar DTE
        new_dte = dte_resigner.resign_dte(dte_data, new_ted)
        resigned_dtes.append(new_dte)
    
    # 5. Re-firmar SetDTE
    setdte_resigner = SetDTEResigner(cert_path, cert_password)
    final_envelope = setdte_resigner.resign_setdte(envelope_data, caratula, resigned_dtes)
    
    # 6. Guardar resultado
    save_xml(final_envelope, output_xml)
```

---

## 6. Validación y Testing

### 6.1 Validaciones Requeridas

```python
def validate_resignation_process(original_xml, resigned_xml):
    """Validar que el proceso de re-firmado fue exitoso"""
    
    # 1. Validar estructura preservada
    assert_structure_preserved(original_xml, resigned_xml)
    
    # 2. Validar datos de negocio intactos
    assert_business_data_intact(original_xml, resigned_xml)
    
    # 3. Validar nuevas firmas
    assert_signatures_valid(resigned_xml)
    
    # 4. Validar schema SII
    assert_sii_schema_valid(resigned_xml)

def assert_structure_preserved(original, resigned):
    """Verificar que la estructura se preservó"""
    # Verificar que Encabezado, Detalle, Referencias son idénticos
    # Verificar que Carátula es idéntica
    # Verificar que datos del DD son idénticos
    
def assert_business_data_intact(original, resigned):
    """Verificar que los datos de negocio no cambiaron"""
    # Verificar folios, montos, fechas, RUTs
    # Verificar items, cantidades, precios
    # Verificar referencias, razones sociales
```

### 6.2 Tests de Comparación

```python
def test_data_preservation():
    """Test que los datos se preservan correctamente"""
    # Comparar elemento por elemento
    # Verificar que solo cambiaron las firmas
    
def test_signature_improvement():
    """Test que las firmas mejoraron"""
    # Verificar que las nuevas firmas son válidas
    # Verificar canonicalización correcta
    # Verificar encoding consistente
```

---

## 7. Ventajas de Este Enfoque

### 7.1 Preservación de Datos
- **Reutiliza todo el trabajo de Odoo**: Encabezados, detalles, referencias
- **Mantiene consistencia**: Mismos folios, montos, fechas
- **Preserva carátula**: Conteos y estructura exacta

### 7.2 Corrección de Problemas
- **Limpia firmas problemáticas**: Remueve solo las firmas, mantiene datos
- **Aplica canonicalización correcta**: Proceso de firma limpio
- **Mantiene encoding**: ISO-8859-1 consistente

### 7.3 Debugging Simplificado
- **Comparación directa**: Antes vs después
- **Identificación precisa**: Qué cambió exactamente
- **Validación granular**: Cada componente por separado

---

## 8. Criterios de Éxito

### 8.1 Preservación de Datos
- [ ] Todos los datos de negocio idénticos
- [ ] Estructura XML preservada
- [ ] Encoding consistente
- [ ] Carátula idéntica

### 8.2 Mejora de Firmas
- [ ] Firmas FRMT válidas
- [ ] Firmas XMLDSig individuales válidas
- [ ] Firma SetDTE válida
- [ ] Canonicalización correcta

### 8.3 Validación SII
- [ ] Pasa validación de schema
- [ ] Pasa validación de firmas individuales
- [ ] Pasa validación de firma consolidada
- [ ] Aceptado por SII sin errores

---

## 9. Entregables

### 9.1 Aplicación Python
- [ ] Código fuente completo
- [ ] Tests unitarios y de integración
- [ ] CLI funcional
- [ ] Documentación técnica

### 9.2 Validación
- [ ] Herramientas de comparación
- [ ] Scripts de testing
- [ ] Casos de prueba con XML real
- [ ] Reportes de validación

### 9.3 Integración
- [ ] Script de integración con Odoo
- [ ] Documentación de uso
- [ ] Ejemplos de configuración
- [ ] Guía de troubleshooting

**Estimado: 2-3 semanas de desarrollo**