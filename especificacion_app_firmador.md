# Especificación: Aplicación Firmador de DTEs - SII Chile

## 1. Resumen Ejecutivo

### Objetivo
Desarrollar una aplicación Python independiente que implemente el proceso **triple de firma** requerido por el SII para documentos consolidados (SetDTE), resolviendo los problemas de rechazo actuales.

### Problema a Resolver
- El módulo Odoo actual genera DTEs que fallan en la validación de firmas individuales del SII
- Necesidad de control granular sobre canonicalización XML y proceso de firma
- Separación de responsabilidades entre generación de DTEs y proceso de firma

### Solución Propuesta
Aplicación Python que toma DTEs sin firmar desde Odoo y aplica el proceso de firma completo según especificación SII.

---

## 2. Arquitectura de la Aplicación

### 2.1 Componentes Principales

```
dte_signer/
├── main.py                 # Punto de entrada y CLI
├── config/
│   ├── __init__.py
│   ├── settings.py         # Configuración global
│   └── logging_config.py   # Configuración de logging
├── models/
│   ├── __init__.py
│   ├── caf_handler.py      # Manejo de archivos CAF
│   ├── certificate_handler.py  # Manejo de certificados PFX
│   ├── dte_document.py     # Modelo de documento DTE
│   └── batch_processor.py  # Procesador de lotes
├── signers/
│   ├── __init__.py
│   ├── frmt_signer.py      # Firma FRMT (TED)
│   ├── xmldsig_signer.py   # Firma XMLDSig individual
│   └── setdte_signer.py    # Firma XMLDSig consolidada
├── utils/
│   ├── __init__.py
│   ├── xml_canonicalizer.py    # Canonicalización XML
│   ├── xml_validator.py        # Validación XML
│   ├── encoding_handler.py     # Manejo de encoding
│   └── sii_validator.py        # Validaciones específicas SII
├── tests/
│   ├── __init__.py
│   ├── test_caf_handler.py
│   ├── test_certificate_handler.py
│   ├── test_signers.py
│   └── test_integration.py
└── requirements.txt
```

### 2.2 Flujo de Datos

```
[XML sin firmar] → [Aplicación] → [XML firmado]
       ↓              ↓              ↓
  - DTEs Odoo    - Proceso Triple   - Listo para SII
  - Sin TED      - Validación      - Triple firma
  - Sin firmas   - Canonicalización - Validado
```

---

## 3. Especificaciones Técnicas

### 3.1 Requisitos de Entrada

**Formato de Entrada:**
```xml
<?xml version="1.0" encoding="ISO-8859-1"?>
<EnvioDTE xmlns="http://www.sii.cl/SiiDte" version="1.0">
    <SetDTE ID="SetDoc">
        <Caratula>...</Caratula>
        <DTE version="1.0">
            <Documento ID="F{FOLIO}T{TIPO}">
                <!-- SIN TED -->
                <!-- SIN Signature -->
            </Documento>
        </DTE>
        <!-- Más DTEs -->
        <!-- SIN Signature del SetDTE -->
    </SetDTE>
</EnvioDTE>
```

**Archivos Requeridos:**
- `input.xml` - XML sin firmar desde Odoo
- `caf_33.xml` - Archivo CAF del SII con clave privada
- `certificado.pfx` - Certificado digital empresa
- `config.json` - Configuración de la aplicación

### 3.2 Requisitos de Salida

**Formato de Salida:**
```xml
<?xml version="1.0" encoding="ISO-8859-1"?>
<EnvioDTE xmlns="http://www.sii.cl/SiiDte" version="1.0">
    <SetDTE ID="SetDoc">
        <Caratula>...</Caratula>
        <DTE version="1.0">
            <Documento ID="F{FOLIO}T{TIPO}">
                <!-- CON TED firmado -->
                <!-- CON TmstFirma -->
            </Documento>
            <!-- CON Signature individual -->
        </DTE>
        <!-- Más DTEs firmados -->
        <!-- CON Signature del SetDTE -->
    </SetDTE>
</EnvioDTE>
```

---

## 4. Especificaciones de Componentes

### 4.1 CAFHandler

**Responsabilidades:**
- Cargar archivos CAF completos del SII
- Extraer clave privada para firma FRMT
- Validar rangos de folios
- Generar elementos CAF para TED

**Métodos Principales:**
```python
class CAFHandler:
    def __init__(self, caf_file_path: str)
    def load_caf(self) -> None
    def validate_folio(self, folio: int) -> bool
    def get_caf_element(self) -> etree.Element
    def get_private_key(self) -> RSAPrivateKey
    def get_caf_data(self) -> Dict
```

**Formato CAF Esperado:**
```xml
<AUTORIZACION>
    <CAF version="1.0">
        <DA>
            <RE>RUT-EMISOR</RE>
            <RS>RAZON-SOCIAL</RS>
            <TD>TIPO-DTE</TD>
            <RNG><D>1</D><H>100</H></RNG>
            <FA>FECHA-AUTORIZACION</FA>
            <RSAPK>
                <M>MODULO-CLAVE-PUBLICA</M>
                <E>EXPONENTE</E>
            </RSAPK>
            <IDK>ID-CLAVE</IDK>
        </DA>
        <FRMA algoritmo="SHA1withRSA">FIRMA-SII</FRMA>
    </CAF>
    <RSASK>CLAVE-PRIVADA-BASE64</RSASK>
</AUTORIZACION>
```

### 4.2 CertificateHandler

**Responsabilidades:**
- Cargar certificados PFX con password
- Extraer clave privada para XMLDSig
- Obtener información de clave pública
- Generar elementos KeyInfo para XMLDSig

**Métodos Principales:**
```python
class CertificateHandler:
    def __init__(self, pfx_path: str, password: str)
    def load_certificate(self) -> None
    def get_private_key(self) -> RSAPrivateKey
    def get_public_key_info(self) -> Dict[str, str]
    def get_certificate_b64(self) -> str
    def get_subject_info(self) -> Dict
```

### 4.3 FRMTSigner

**Responsabilidades:**
- Generar firma FRMT para timbre electrónico
- Construir elemento TED completo
- Manejar canonicalización específica para FRMT
- Validar folios contra CAF

**Algoritmo de Firma FRMT:**
```python
def generate_frmt_signature(self, dd_element: etree.Element) -> str:
    # 1. Aplanar XML removiendo espacios entre elementos
    dd_flattened = self._flatten_xml(dd_element)
    
    # 2. Escapar caracteres especiales
    dd_escaped = self._escape_xml_chars(dd_flattened)
    
    # 3. Codificar en ISO-8859-1
    dd_bytes = dd_escaped.encode('ISO-8859-1')
    
    # 4. Firmar con SHA1withRSA
    signature = caf_private_key.sign(dd_bytes, padding.PKCS1v15(), hashes.SHA1())
    
    # 5. Codificar en Base64
    return base64.b64encode(signature).decode('ascii')
```

### 4.4 XMLDSigSigner

**Responsabilidades:**
- Firmar DTEs individuales con XMLDSig
- Firmar SetDTE consolidado
- Manejar canonicalización C14N
- Generar estructura completa de firma

**Algoritmo XMLDSig:**
```python
def sign_element(self, element: etree.Element, reference_id: str) -> etree.Element:
    # 1. Canonicalizar elemento target
    canonicalized = self._canonicalize_c14n(element)
    
    # 2. Calcular digest SHA1
    digest = hashlib.sha1(canonicalized.encode('utf-8')).digest()
    
    # 3. Construir SignedInfo
    signed_info = self._build_signed_info(reference_id, digest)
    
    # 4. Canonicalizar SignedInfo
    canonicalized_signed_info = self._canonicalize_c14n(signed_info)
    
    # 5. Firmar con RSA-SHA1
    signature = cert_private_key.sign(canonicalized_signed_info, padding.PKCS1v15(), hashes.SHA1())
    
    # 6. Construir elemento Signature completo
    return self._build_signature_element(signed_info, signature)
```

### 4.5 XMLCanonicalizer

**Responsabilidades:**
- Implementar canonicalización C14N estándar
- Manejar namespaces correctamente
- Preservar orden de atributos
- Normalizar espacios en blanco

**Métodos:**
```python
class XMLCanonicalizer:
    def canonicalize_c14n(self, element: etree.Element) -> str
    def normalize_namespaces(self, element: etree.Element) -> etree.Element
    def clean_whitespace(self, xml_str: str) -> str
```

### 4.6 SIIValidator

**Responsabilidades:**
- Validar estructura según especificación SII
- Verificar consistencia de firmas
- Validar elementos obligatorios
- Reportar errores detallados

**Validaciones:**
```python
class SIIValidator:
    def validate_dte_structure(self, dte_element: etree.Element) -> ValidationResult
    def validate_ted_signature(self, ted_element: etree.Element) -> ValidationResult
    def validate_xmldsig_signature(self, signature_element: etree.Element) -> ValidationResult
    def validate_setdte_consistency(self, setdte_element: etree.Element) -> ValidationResult
```

---

## 5. Configuración de la Aplicación

### 5.1 Archivo de Configuración (config.json)

```json
{
    "logging": {
        "level": "INFO",
        "file": "dte_signer.log",
        "max_size": "10MB",
        "backup_count": 5
    },
    "validation": {
        "strict_mode": true,
        "validate_caf": true,
        "validate_certificate": true,
        "validate_output": true
    },
    "encoding": {
        "input_encoding": "ISO-8859-1",
        "output_encoding": "ISO-8859-1"
    },
    "canonicalization": {
        "method": "c14n",
        "preserve_whitespace": false,
        "normalize_namespaces": true
    }
}
```

### 5.2 Variables de Entorno

```bash
# Rutas de archivos
DTE_SIGNER_CONFIG_PATH=/path/to/config.json
DTE_SIGNER_LOG_PATH=/path/to/logs/

# Configuración de certificados
CERT_PASSWORD_FILE=/path/to/cert_password.txt

# Configuración de debugging
DEBUG_MODE=false
SAVE_INTERMEDIATE_FILES=false
```

---

## 6. Interfaz de Línea de Comandos

### 6.1 Uso Básico

```bash
# Firmar un batch de DTEs
python -m dte_signer sign \
    --input /path/to/input.xml \
    --output /path/to/output.xml \
    --caf /path/to/caf_33.xml \
    --cert /path/to/certificate.pfx \
    --password "cert_password"

# Validar archivos sin firmar
python -m dte_signer validate \
    --input /path/to/input.xml \
    --caf /path/to/caf_33.xml

# Verificar firma existente
python -m dte_signer verify \
    --input /path/to/signed.xml \
    --cert /path/to/certificate.pfx
```

### 6.2 Opciones Avanzadas

```bash
# Modo debug con archivos intermedios
python -m dte_signer sign \
    --input input.xml \
    --output output.xml \
    --caf caf_33.xml \
    --cert cert.pfx \
    --password "pass" \
    --debug \
    --save-intermediate

# Validación estricta
python -m dte_signer sign \
    --input input.xml \
    --output output.xml \
    --caf caf_33.xml \
    --cert cert.pfx \
    --password "pass" \
    --strict-validation

# Configuración personalizada
python -m dte_signer sign \
    --config /path/to/custom_config.json \
    --input input.xml \
    --output output.xml \
    --caf caf_33.xml \
    --cert cert.pfx \
    --password "pass"
```

---

## 7. Dependencias y Requisitos

### 7.1 Dependencias Python

```
# requirements.txt
lxml>=4.9.0                 # Manipulación XML
cryptography>=38.0.0        # Operaciones criptográficas
xmlsec>=1.3.0              # Firmas XMLDSig (opcional)
click>=8.0.0               # CLI framework
pydantic>=1.10.0           # Validación de datos
pytest>=7.0.0              # Testing
black>=22.0.0              # Code formatting
mypy>=0.991                # Type checking
```

### 7.2 Requisitos del Sistema

- **Python**: 3.8+
- **Sistema Operativo**: Linux, macOS, Windows
- **Memoria**: 512MB mínimo
- **Espacio en disco**: 100MB
- **Librerías del sistema**: libxml2, libxslt

---

## 8. Testing y Validación

### 8.1 Suite de Tests

```python
# Test unitarios
test_caf_handler.py         # Carga y validación de CAF
test_certificate_handler.py # Carga de certificados PFX
test_frmt_signer.py         # Firma FRMT
test_xmldsig_signer.py      # Firma XMLDSig
test_xml_canonicalizer.py   # Canonicalización

# Test de integración
test_full_signing_process.py # Proceso completo
test_batch_processing.py     # Procesamiento de lotes
test_validation.py           # Validación SII

# Test de rendimiento
test_performance.py          # Tiempo de procesamiento
test_memory_usage.py         # Uso de memoria
```

### 8.2 Casos de Prueba

1. **Documentos válidos**: DTEs que deben firmarse correctamente
2. **Documentos inválidos**: DTEs con errores que deben ser rechazados
3. **Folios fuera de rango**: Validación de CAF
4. **Certificados expirados**: Manejo de errores
5. **XML malformado**: Manejo de errores de parsing
6. **Firmas incorrectas**: Validación de firmas existentes

---

## 9. Logging y Monitoreo

### 9.1 Estructura de Logs

```
INFO  - 2025-01-01 10:00:00 - Iniciando proceso de firma
INFO  - 2025-01-01 10:00:01 - CAF cargado: tipo=33, rango=1-100
INFO  - 2025-01-01 10:00:02 - Certificado cargado: CN=EMPRESA S.A.
INFO  - 2025-01-01 10:00:03 - Procesando DTE F17T33
DEBUG - 2025-01-01 10:00:04 - TED generado para folio 17
DEBUG - 2025-01-01 10:00:05 - Firma FRMT calculada
INFO  - 2025-01-01 10:00:06 - DTE F17T33 firmado exitosamente
INFO  - 2025-01-01 10:00:10 - SetDTE firmado exitosamente
INFO  - 2025-01-01 10:00:11 - Proceso completado: 8 DTEs firmados
```

### 9.2 Métricas de Rendimiento

- Tiempo total de procesamiento
- Tiempo por DTE individual
- Uso de memoria durante el proceso
- Errores por tipo
- Tasa de éxito de firmas

---

## 10. Manejo de Errores

### 10.1 Categorías de Errores

```python
class DTESignerError(Exception):
    """Error base de la aplicación"""
    pass

class CAFError(DTESignerError):
    """Errores relacionados con CAF"""
    pass

class CertificateError(DTESignerError):
    """Errores relacionados con certificados"""
    pass

class SignatureError(DTESignerError):
    """Errores en proceso de firma"""
    pass

class ValidationError(DTESignerError):
    """Errores de validación"""
    pass
```

### 10.2 Códigos de Error

```python
ERROR_CODES = {
    'CAF_001': 'Archivo CAF no encontrado',
    'CAF_002': 'CAF inválido o corrupto',
    'CAF_003': 'Folio fuera de rango autorizado',
    'CERT_001': 'Certificado PFX no encontrado',
    'CERT_002': 'Password incorrecto',
    'CERT_003': 'Certificado expirado',
    'SIGN_001': 'Error en firma FRMT',
    'SIGN_002': 'Error en firma XMLDSig',
    'SIGN_003': 'Error en canonicalización',
    'VAL_001': 'XML malformado',
    'VAL_002': 'Estructura DTE inválida',
    'VAL_003': 'Firma inválida'
}
```

---

## 11. Integración con Odoo

### 11.1 Flujo de Integración

```python
# En el módulo Odoo
def generate_unsigned_xml(self):
    # Generar XML sin firmar
    unsigned_xml = self._build_consolidated_setdte_unsigned()
    
    # Llamar aplicación externa
    result = self._call_external_signer(unsigned_xml)
    
    if result.success:
        # Guardar XML firmado
        self._save_signed_xml(result.signed_xml)
    else:
        # Manejar error
        raise UserError(f'Error en firma: {result.error}')

def _call_external_signer(self, xml_content):
    # Llamar aplicación Python
    import subprocess
    
    cmd = [
        'python', '-m', 'dte_signer', 'sign',
        '--input', temp_input_file,
        '--output', temp_output_file,
        '--caf', self.company_id.caf_file_path,
        '--cert', self.company_id.cert_file_path,
        '--password', self.company_id.cert_password
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return {'success': True, 'signed_xml': load_output_file()}
    else:
        return {'success': False, 'error': result.stderr}
```

### 11.2 Configuración en Odoo

```python
# Nuevos campos en res.company
class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # Rutas de archivos
    caf_file_path = fields.Char('Ruta archivo CAF')
    cert_file_path = fields.Char('Ruta certificado PFX')
    cert_password = fields.Char('Password certificado')
    
    # Configuración firmador
    dte_signer_config = fields.Text('Configuración firmador')
    enable_external_signer = fields.Boolean('Usar firmador externo')
```

---

## 12. Entregables

### 12.1 Código Fuente

- [ ] Aplicación Python completa
- [ ] Suite de tests unitarios
- [ ] Tests de integración
- [ ] Documentación técnica
- [ ] Ejemplos de uso

### 12.2 Documentación

- [ ] Manual de instalación
- [ ] Guía de configuración
- [ ] Referencia API
- [ ] Guía de troubleshooting
- [ ] Ejemplos de integración

### 12.3 Herramientas

- [ ] Scripts de instalación
- [ ] Configuración Docker
- [ ] Scripts de testing
- [ ] Herramientas de debugging

---

## 13. Criterios de Aceptación

### 13.1 Funcionales

- [ ] Genera firmas FRMT válidas para TED
- [ ] Genera firmas XMLDSig válidas para DTEs individuales
- [ ] Genera firmas XMLDSig válidas para SetDTE
- [ ] Valida estructura según especificación SII
- [ ] Maneja múltiples tipos de DTE (33, 61, 56, etc.)
- [ ] Procesa lotes de DTEs eficientemente

### 13.2 No Funcionales

- [ ] Procesa 100 DTEs en menos de 30 segundos
- [ ] Uso de memoria menor a 512MB
- [ ] Logs detallados y útiles
- [ ] Manejo robusto de errores
- [ ] Código bien documentado
- [ ] Cobertura de tests > 90%

### 13.3 Integración

- [ ] Integración transparente con Odoo
- [ ] Compatibilidad con certificados PFX
- [ ] Compatibilidad con archivos CAF del SII
- [ ] Salida compatible con validadores SII
- [ ] Encoding ISO-8859-1 consistente

---

## 14. Cronograma Estimado

### Fase 1: Desarrollo Core (2 semanas)
- Implementar CAFHandler y CertificateHandler
- Desarrollar FRMTSigner básico
- Crear XMLDSigSigner básico
- Tests unitarios básicos

### Fase 2: Integración (1 semana)
- Integrar componentes en flujo completo
- Implementar BatchProcessor
- Crear CLI básica
- Tests de integración

### Fase 3: Validación (1 semana)
- Implementar SIIValidator
- Mejorar manejo de errores
- Optimizar rendimiento
- Tests exhaustivos

### Fase 4: Documentación (0.5 semanas)
- Documentación técnica
- Ejemplos de uso
- Guías de instalación
- Manual de troubleshooting

**Total Estimado: 4.5 semanas**