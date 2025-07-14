# Informe: Proceso de Firma para Envíos DTE Consolidados - SII Chile

## Resumen Ejecutivo

**Problema Identificado**: El documento consolidado (SetDTE) pasa la validación de schema XML y la firma general del envío, pero **falla específicamente en la validación de las firmas individuales de cada DTE contenido**.

**Causa Raíz**: El proceso de firma de documentos consolidados requiere un **triple mecanismo de firmado específico** que debe ejecutarse en orden estricto, con consideraciones técnicas críticas para la canonicalización XML y el manejo de namespaces.

## 1. Arquitectura del Proceso de Firma

### 1.1 Estructura Jerárquica de Firmas

El sistema SII requiere **tres niveles de firma independientes**:

```xml
EnvioDTE
└── SetDTE (ID="SetDoc") ← Firma XMLDSig #3 (Firma del Set completo)
    ├── Caratula
    └── DTE ← Firma XMLDSig #2 (Firma individual por DTE)
        └── Documento (ID="...")
            ├── Encabezado, Detalle, etc.
            └── TED
                ├── DD ← Firma FRMT #1 (Firma con clave CAF)
                └── FRMT (algoritmo="SHA1withRSA")
```

### 1.2 Orden Crítico de Ejecución

**OBLIGATORIO - De adentro hacia afuera:**

1. **Firma FRMT del TED**: Cada documento debe tener su timbre (TED) firmado con la clave privada CAF
2. **Firma XMLDSig individual**: Cada DTE se firma individualmente con el certificado digital del emisor  
3. **Firma XMLDSig del SetDTE**: El conjunto completo se firma con el mismo certificado digital

## 2. Proceso Detallado de Firma

### 2.1 Paso 1: Firma FRMT (Timbre Electrónico)

**Propósito**: Validar autenticidad del folio autorizado por SII

**Proceso**:
```xml
<TED version="1.0">
  <DD>
    <RE>RUT-EMISOR</RE>
    <TD>TIPO-DTE</TD>
    <F>FOLIO</F>
    <FE>FECHA-EMISION</FE>
    <RR>RUT-RECEPTOR</RR>
    <RSR>RAZON-SOCIAL-RECEPTOR</RSR>
    <MNT>MONTO-TOTAL</MNT>
    <IT1>PRIMER-ITEM</IT1>
    <CAF version="1.0">...</CAF>
    <TSTED>TIMESTAMP</TSTED>
  </DD>
  <FRMT algoritmo="SHA1withRSA">FIRMA-CALCULADA</FRMT>
</TED>
```

**Algoritmo de Firma FRMT**:
1. Extraer elemento `<DD>` completo
2. **"Aplanar"** removiendo espacios en blanco entre elementos: `<DD><RE>...</RE><TD>...</TD>...</DD>`
3. Codificar en **ISO-8859-1** (no UTF-8)
4. Firmar con clave privada CAF (512 bits) usando SHA1withRSA
5. Codificar resultado en Base64

**Escaping Crítico para FRMT**:
- `&` → `&amp;`
- `<` → `&lt;`  
- `>` → `&gt;`
- `"` → `&quot;`
- `'` → `&apos;`

### 2.2 Paso 2: Firma XMLDSig Individual (DTE)

**Propósito**: Validar integridad y autenticidad de cada documento

**Elemento a Firmar**: `<Documento ID="ID_UNICO">`

**Consideraciones Técnicas**:
- Algoritmo de canonicalización: `http://www.w3.org/TR/2001/REC-xml-c14n-20010315`
- Algoritmo de firma: `http://www.w3.org/2000/09/xmldsig#rsa-sha1`
- Algoritmo de digest: `http://www.w3.org/2000/09/xmldsig#sha1`
- Reference URI debe apuntar al ID del documento: `#ID_UNICO`

### 2.3 Paso 3: Firma XMLDSig del SetDTE

**Propósito**: Validar integridad del envío consolidado

**Elemento a Firmar**: `<SetDTE ID="SetDoc">`

**⚠️ PROBLEMA CRÍTICO IDENTIFICADO:**

Durante la canonicalización del SetDTE, los elementos DTE internos pueden introducir declaraciones de namespace superfluos que invalidan la firma:

```xml
<!-- INCORRECTO - namespace superfluo -->
<SetDTE ID="SetDoc" xmlns="http://www.sii.cl/SiiDte">
  <DTE xmlns="http://www.sii.cl/SiiDte" version="1.0"> <!-- ← namespace redundante -->
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#"> <!-- ← namespace redundante -->
```

```xml
<!-- CORRECTO - namespace limpio -->
<SetDTE ID="SetDoc" xmlns="http://www.sii.cl/SiiDte">
  <DTE version="1.0">
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <SignedInfo>
```

## 3. Problemas Comunes y Soluciones

### 3.1 Error "RFR - Rechazado por Error en Firma"

**Causas Principales**:

1. **Encoding Incorrecto**
   - ❌ Firmar en UTF-8 
   - ✅ Firmar en ISO-8859-1

2. **Modificación Post-Firma**
   - ❌ Reformatear o "pretty-print" después del firmado
   - ✅ Preservar espaciado exacto post-firma

3. **Canonicalización Incorrecta**
   - ❌ Namespaces superfluos en SetDTE
   - ✅ Limpieza de namespaces durante canonicalización

4. **Referencias XML Incorrectas**
   - ❌ Reference URI que no coincide con ID
   - ✅ Verificar correspondencia exacta URI/ID

### 3.2 Validación de Firmas Individuales que Falla

**Síntomas**: El SetDTE es aceptado pero las firmas individuales fallan

**Diagnóstico**:
1. Verificar que cada DTE tenga su propia firma XMLDSig
2. Confirmar que el ID del Documento coincida con la Reference URI
3. Validar que la firma FRMT de cada TED sea correcta
4. Revisar encoding de caracteres especiales (acentos, &, etc.)

## 4. Implementación Recomendada

### 4.1 Alternativa: Herramienta Python Independiente

Dada la complejidad del proceso y los problemas identificados, **se recomienda desarrollar una herramienta Python independiente**:

**Ventajas**:
- Control total sobre el proceso de canonicalización
- Manejo preciso de encoding ISO-8859-1
- Separación clara de responsabilidades de firma
- Facilidad para debugging del proceso

**Arquitectura Propuesta**:
```python
class DTEConsolidator:
    def __init__(self, certificado_digital, clave_caf):
        self.cert = certificado_digital
        self.caf_key = clave_caf
    
    def procesar_dtes(self, lista_dtes_xml):
        """
        1. Firmar cada DTE individualmente
        2. Construir SetDTE
        3. Firmar SetDTE consolidado
        """
        pass
    
    def firmar_frmt(self, dd_element):
        """Firma FRMT usando clave CAF"""
        pass
    
    def firmar_dte_individual(self, dte_xml):
        """Firma XMLDSig individual"""
        pass
    
    def firmar_setdte(self, setdte_xml):
        """Firma XMLDSig del conjunto"""
        pass
```

### 4.2 Librerías Python Recomendadas

- **lxml**: Para manipulación XML precisa
- **xmlsec**: Para firmas XMLDSig
- **cryptography**: Para operaciones criptográficas
- **signxml**: Alternativa para XMLDSig

### 4.3 Consideraciones de Integración con Odoo

**Opción 1 - Herramienta Externa**:
- Odoo genera DTEs individuales (sin firma consolidada)
- Script Python procesa y consolida
- Resultado se envía al SII

**Opción 2 - Módulo Odoo Mejorado**:
- Refactorizar proceso de firma actual
- Implementar canonicalización correcta
- Separar claramente los tres niveles de firma

## 5. Pasos Inmediatos Recomendados

### 5.1 Diagnóstico del Problema Actual

1. **Extraer y analizar un SetDTE fallido**:
   - Verificar estructura XML
   - Validar firmas individuales manualmente
   - Identificar discrepancias en canonicalización

2. **Comparar con ejemplos oficiales SII**:
   - Descargar ejemplos de documentos válidos
   - Analizar diferencias estructurales
   - Verificar proceso de canonicalización

### 5.2 Prototipo de Validación

1. **Crear herramienta de verificación**:
   ```python
   def verificar_setdte(archivo_xml):
       # Validar schema
       # Verificar firma SetDTE
       # Verificar cada firma DTE individual
       # Verificar cada firma FRMT
   ```

2. **Implementar proceso de firma paso a paso**:
   - Comenzar con un solo DTE
   - Validar cada nivel de firma independientemente
   - Escalar a múltiples DTEs

### 5.3 Criterios de Éxito

- ✅ Schema XML válido
- ✅ Firma SetDTE válida  
- ✅ Todas las firmas DTE individuales válidas
- ✅ Todas las firmas FRMT válidas
- ✅ Envío aceptado por SII sin errores

## 6. Conclusiones

El proceso de firma de DTEs consolidados es **significativamente más complejo** que la firma individual, requiriendo:

1. **Triple mecanismo de firma** en orden específico
2. **Canonicalización precisa** con limpieza de namespaces
3. **Encoding estricto** en ISO-8859-1
4. **Preservación exacta** del formato post-firma

La **implementación de una herramienta Python independiente** ofrece la mejor ruta para resolver los problemas identificados, proporcionando control granular sobre cada aspecto del proceso de firma y facilitando el debugging de problemas específicos.

El módulo Odoo actual puede mantener su responsabilidad de **generar DTEs individuales válidos**, mientras que la herramienta externa se encarga del **proceso de consolidación y firma múltiple**.