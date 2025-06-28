# Especificación SII para EnvioDTE Consolidado - Certificación

## 📄 Estructura Técnica Requerida por SII

### 1. Elemento Raíz: `<EnvioDTE>`

```xml
<?xml version="1.0" encoding="ISO-8859-1"?>
<EnvioDTE xmlns="http://www.sii.cl/SiiDte" 
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
          xsi:schemaLocation="http://www.sii.cl/SiiDte EnvioDTE_v10.xsd" 
          version="1.0">
  <!-- Contenido del envío -->
</EnvioDTE>
```

**Características técnicas obligatorias:**
- **Encoding:** ISO-8859-1 (crítico)
- **Schema:** EnvioDTE_v10.xsd (validación SII)
- **Namespace:** http://www.sii.cl/SiiDte
- **Version:** 1.0

### 2. Sección `<SetDTE ID="SetDoc">`

```xml
<SetDTE ID="SetDoc">
  <Caratula version="1.0">
    <!-- Metadatos del envío consolidado -->
  </Caratula>
  
  <!-- Múltiples DTEs -->
  <DTE version="1.0"><!-- Documento 1 --></DTE>
  <DTE version="1.0"><!-- Documento 2 --></DTE>
  <DTE version="1.0"><!-- Documento N --></DTE>
</SetDTE>
```

**Crítico:** El ID "SetDoc" es referenciado por la firma digital XML.

### 3. Estructura de Carátula (OBLIGATORIA)

```xml
<Caratula version="1.0">
  <!-- IDENTIFICACIÓN -->
  <RutEmisor>76235291-5</RutEmisor>
  <RutEnvia>12345678-9</RutEnvia>        <!-- Usuario certificado -->
  <RutReceptor>60803000-K</RutReceptor>   <!-- SIEMPRE SII -->
  
  <!-- CERTIFICACIÓN -->
  <FchResol>2023-09-02</FchResol>        <!-- Fecha resolución -->
  <NroResol>0</NroResol>                 <!-- 0 = certificación -->
  
  <!-- TIMESTAMP -->
  <TmstFirmaEnv>2023-09-08T12:31:59</TmstFirmaEnv>
  
  <!-- TOTALES POR TIPO (CRÍTICO) -->
  <SubTotDTE>
    <TpoDTE>33</TpoDTE>    <!-- Factura Electrónica -->
    <NroDTE>3</NroDTE>     <!-- Cantidad -->
  </SubTotDTE>
  <SubTotDTE>
    <TpoDTE>61</TpoDTE>    <!-- Nota de Crédito -->
    <NroDTE>2</NroDTE>     <!-- Cantidad -->
  </SubTotDTE>
  <SubTotDTE>
    <TpoDTE>56</TpoDTE>    <!-- Nota de Débito -->
    <NroDTE>1</NroDTE>     <!-- Cantidad -->
  </SubTotDTE>
</Caratula>
```

**Lógica SubTotDTE:**
1. Analizar todos los DTEs del envío
2. Contar documentos por tipo único
3. Crear un `<SubTotDTE>` por cada tipo encontrado
4. El conteo debe ser exacto vs DTEs incluidos

### 4. Estructura DTE Individual

```xml
<DTE version="1.0">
  <Documento ID="F27T33">      <!-- ID único en envío -->
    <Encabezado>
      <IdDoc>
        <TipoDTE>33</TipoDTE>
        <Folio>27</Folio>
        <!-- ... -->
      </IdDoc>
      <!-- ... -->
    </Encabezado>
    <Detalle><!-- Líneas --></Detalle>
    <Referencias>
      <!-- CRÍTICO para certificación -->
      <Referencia>
        <TpoDocRef>SET</TpoDocRef>
        <RazonRef>CASO 4329504-1</RazonRef>
      </Referencia>
    </Referencias>
    <TED version="1.0"><!-- Timbre SII --></TED>
  </Documento>
  
  <!-- FIRMA DEL DTE INDIVIDUAL -->
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <!-- Firma específica del documento -->
  </Signature>
</DTE>
```

## 🔐 Sistema de Firmas Digitales (DOS NIVELES)

### Nivel 1: Firma Individual DTE
- **Elemento firmado:** `<Documento ID="...">`
- **Propósito:** Integridad del documento específico
- **Estado:** Ya existe en DTEs generados por Odoo
- **Preservar:** NO re-firmar, mantener firma original

### Nivel 2: Firma Consolidada SetDTE
- **Elemento firmado:** `<SetDTE ID="SetDoc">`
- **Propósito:** Integridad del envío completo
- **Reference URI:** "#SetDoc"
- **Estado:** NUEVA - Debe generarse para consolidado

```xml
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
  <SignedInfo>
    <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
    <SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
    <Reference URI="#SetDoc">
      <Transforms>
        <Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
      </Transforms>
      <DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
      <DigestValue>...</DigestValue>
    </Reference>
  </SignedInfo>
  <SignatureValue>...</SignatureValue>
  <KeyInfo><!-- Certificado empresa --></KeyInfo>
</Signature>
```

## 🔧 Proceso de Construcción Requerido

### Paso 1: Extracción DTEs
```python
# Extraer nodo <DTE> completo con firma interna
dte_node = tree.find('.//{http://www.sii.cl/SiiDte}DTE')
# Resultado: <DTE><Documento>...</Documento><Signature>...</Signature></DTE>
```

### Paso 2: Carátula con Conteo
```python
# Contar tipos únicos
doc_counts = Counter()
for dte in dte_nodes:
    tipo = dte.find('.//{http://www.sii.cl/SiiDte}TipoDTE').text
    doc_counts[tipo] += 1

# Generar SubTotDTE
for tipo, cantidad in doc_counts.items():
    # <SubTotDTE><TpoDTE>33</TpoDTE><NroDTE>4</NroDTE></SubTotDTE>
```

### Paso 3: Ensamblaje SetDTE
```python
setdte = etree.Element('SetDTE', attrib={'ID': 'SetDoc'})
setdte.append(caratula)
for dte_node in dte_nodes_extraidos:
    setdte.append(dte_node)  # Preserva firmas internas
```

### Paso 4: Firmado SetDTE
```python
# Firmar SOLO el SetDTE completo
# URI="#SetDoc"
# Algoritmos: rsa-sha1, xml-c14n
# Certificado: Empresa emisora
```

## ⚠️ Consideraciones Críticas

### Técnicas
- **Encoding:** ISO-8859-1 en todo el proceso
- **Schema:** Validación contra EnvioDTE_v10.xsd
- **IDs únicos:** Cada `<Documento ID="...">` único en envío
- **Namespaces:** Consistentes en toda la estructura

### Certificación SII
- **Referencias SET:** Cada DTE debe referenciar caso de prueba
- **Folios CAF:** Usar folios reales proporcionados por SII
- **Trazabilidad:** Mantener vínculos con sets de prueba originales

### Validación
- **SubTotDTE exacto:** Conteo debe coincidir con DTEs incluidos
- **Firmas preservadas:** DTEs individuales mantienen firmas originales
- **Firma consolidada:** SetDTE firmado completamente
- **Estructura válida:** Cumplir schema SII exacto

## 📝 Preguntas para Investigación

1. **¿El template `l10n_cl_edi.envio_dte` de Odoo soporta múltiples DTEs?**
2. **¿Nuestros overrides de certificación afectan la generación de EnvioDTE?**
3. **¿El método `_sign_full_xml` puede firmar SetDTE con Reference URI="#SetDoc"?**
4. **¿Los DTEs batch mantienen las referencias SET correctas?**
5. **¿El encoding ISO-8859-1 se preserva en todo el flujo?**

## 🎯 Objetivo

Generar EnvioDTE consolidado que:
- Pase validación schema SII (EnvioDTE_v10.xsd)
- Contenga firma digital válida en dos niveles
- Mantenga trazabilidad completa a sets de prueba
- Sea aceptado por sistema de certificación SII

## 📊 Estado Actual del Proyecto

### ✅ Logros
- Extracción exitosa de 8 DTEs individuales
- Carátula con SubTotDTE implementada
- Proceso batch funcional para generación de documentos

### ❌ Pendientes Críticos
- Firmado digital del SetDTE consolidado
- Validación de cumplimiento con schema SII
- Preservación correcta de firmas individuales
- Encoding ISO-8859-1 consistente