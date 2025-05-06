## 1. Tipos de DTEs

| Código | Descripción                                | Autorizado   |
|--------|-------------------------------------------|--------------|
| 33     | FACTURA ELECTRONICA                       | 26-03-2025   |
| 34     | FACTURA NO AFECTA O EXENTA ELECTRONICA    | 26-03-2025   |
| 39     | BOLETA ELECTRONICA                        | 26-03-2025   |
| 41     | BOLETA EXENTA ELECTRONICA                 | 26-03-2025   |
| 43     | LIQUIDACION FACTURA ELECTRONICA           | 26-03-2025   |
| 46     | FACTURA COMPRA ELECTRONICA                | 26-03-2025   |
| 52     | GUIA DESPACHO ELECTRONICA                 | 26-03-2025   |
| 56     | NOTA DEBITO ELECTRONICA                   | 26-03-2025   |
| 61     | NOTA CREDITO ELECTRONICA                  | 26-03-2025   |
| 110    | FACTURA DE EXPORTACION ELECTRONICA        | 26-03-2025   |
| 111    | NOTA DE DEBITO EXPORTACION ELECTRONICA    | 26-03-2025   |
| 112    | NOTA DE CREDITO EXPORTACION ELECTRONICA   | 26-03-2025   |

## 2. Estructura General de los DTEs

Los DTEs se estructuran en formato XML y tienen las siguientes secciones:

| Zonas del Documento          | Obligatoriedad de la Zona |
|------------------------------|---------------------------|
| Encabezado                   | 1 (Obligatorio)           |
| Detalle                      | 2 (Condicional)           |
| Subtotales Informativos      | 2 (Condicional)           |
| Descuentos y Recargos        | 2 (Condicional)           |
| Datos de Referencia          | 3 (Opcional)              |
| Datos de Georreferenciación  | 2 (Condicional)           |
| Timbre                       | 1 (Obligatorio)           |
| Firma                        | 1 (Obligatorio)           |

### Códigos de Obligatoriedad:
- **1**: Dato obligatorio. Debe estar siempre, independiente de las características de la transacción.
- **2**: Dato condicional. No es obligatorio en todos los documentos, pero pasa a ser obligatorio en determinadas operaciones si se cumple una cierta condición.
- **3**: Opcional.

### Impresión (Representación Digital):
- **N**: No es obligatorio que esté impreso.
- **I**: Debe estar impreso. La impresión debe ser en formato editado.
- **P**: Debe estar impreso traduciendo el código a palabras.

## 3. Secciones Principales

### 3.1 Encabezado (Campos Clave)

| Campo            | Descripción                         | Tipo  | Largo | Obligatoriedad |
|------------------|-------------------------------------|-------|-------|----------------|
| VERSIÓN          | Versión del Formato utilizado       | ALFA  | 3     | 1              |
| TipoDTE          | Tipo de Documento (39, 41, etc.)    | NUM   | 2     | 1              |
| Folio            | Folio autorizado por el SII         | NUM   | 10    | 1              |
| FchEmis          | Fecha de emisión (AAAA-MM-DD)       | ALFA  | 10    | 1              |
| IndServicio      | Indica tipo de transacción          | NUM   | 1     | 1              |
| IndMntNeto       | Indicador Montos Netos              | NUM   | 1     | 3 (boleta)/0 (exenta) |
| MedioPago        | Medio de pago utilizado             | NUM   | 1     | 2              |
| RUTEmisor        | RUT del emisor con DV               | ALFA  | 10    | 1              |
| RznSocEmisor     | Nombre o Razón Social Emisor        | ALFA  | 100   | 3              |
| GiroEmisor       | Giro del negocio                    | ALFA  | 80    | 3              |
| DirOrigen        | Dirección de origen                 | ALFA  | 70    | 3              |
| RUTRecep         | RUT receptor con DV                 | ALFA  | 10    | 1              |
| RznSocRecep      | Nombre receptor                     | ALFA  | 40    | 2              |
| CorreoRecep      | Correo electrónico receptor         | ALFA  | 80    | 2              |
| TelefonoRecep    | Teléfono receptor                   | ALFA  | 20    | 2              |
| DirRecep         | Dirección receptor                  | ALFA  | 70    | 2              |
| MntNeto          | Monto neto                          | NUM   | 18    | 1/0            |
| MntExe           | Monto exento                        | NUM   | 18    | 2              |
| IVA              | IVA                                 | NUM   | 18    | 1/0            |
| MntTotal         | Monto total                         | NUM   | 18    | 1              |
| MontoNF          | Monto no facturable                 | NUM   | 18    | 2              |

### 3.2 Detalle de Productos o Servicios

Corresponde a la información de cada ítem. Máximo: 1000 ítems.

| Campo            | Descripción                          | Tipo  | Largo | Obligatoriedad |
|------------------|--------------------------------------|-------|-------|----------------|
| NroLinDet        | Número del ítem                      | NUM   | 4     | 1              |
| TpoCodigo        | Tipo de codificación                 | ALFA  | 10    | 3              |
| VlrCodigo        | Código del producto                  | ALFA  | 35    | 3              |
| IndExe           | Indicador de exención                | NUM   | 1     | 2              |
| NmbItem          | Nombre del producto o servicio       | ALFA  | 80    | 1              |
| DscItem          | Descripción adicional                | ALFA  | 1000  | 3              |
| QtyItem          | Cantidad                             | NUM   | 18    | 2              |
| UnmdItem         | Unidad de medida                     | ALFA  | 4     | 3              |
| PrcItem          | Precio unitario                      | NUM   | 18    | 2              |
| DescuentoPct     | Porcentaje de descuento              | NUM   | 5     | 3              |
| DescuentoMonto   | Monto descuento                      | NUM   | 18    | 2              |
| RecargoPct       | Porcentaje de recargo                | NUM   | 5     | 3              |
| RecargoMonto     | Monto recargo                        | NUM   | 18    | 2              |
| MontoItem        | Valor por línea de detalle           | NUM   | 18    | 1              |

#### Para documentos de espectáculos (Indicador Servicio = 4)
Cuando el ítem corresponde a un espectáculo (ItemEspectaculo = 01), se deben incluir los siguientes datos adicionales:

| Campo                 | Descripción                         | Tipo  | Largo | Obligatoriedad |
|-----------------------|-------------------------------------|-------|-------|----------------|
| FolioTicket           | Numeración única para el evento     | NUM   | 6     | 1              |
| FchGenera             | Fecha generación del ticket         | ALFA  | 16    | 1              |
| NmbEvento             | Nombre del espectáculo              | ALFA  | 80    | 1              |
| TpoTicket             | Tipo de ticket                      | ALFA  | 10    | 1              |
| CdgEvento             | Código del evento                   | ALFA  | 5     | 1              |
| FchEvento             | Fecha y hora del evento             | ALFA  | 16    | 1              |
| LugarEvento           | Lugar del evento                    | ALFA  | 80    | 1              |
| UbicEvento            | Ubicación en el evento              | ALFA  | 20    | 1              |

### 3.3 Subtotales, Descuentos y Recargos

#### Subtotales Informativos (opcionales)
Pueden ser de 0 hasta 20 líneas. Son informativos, no afectan la base del impuesto.

| Campo               | Descripción                   | Tipo  | Largo | Obligatoriedad |
|---------------------|-------------------------------|-------|-------|----------------|
| NroSTI              | Número de subtotal            | NUM   | 2     | 1              |
| GlosaSTI            | Especificación del subtotal   | ALFA  | 80    | 3              |
| ValSubtotSTI        | Valor de la línea de subtotal | NUM   | 18    | 3              |

#### Descuentos y Recargos 
Pueden ser de 0 hasta 20 líneas. Estos aumentan o disminuyen la base del impuesto.

| Campo            | Descripción                   | Tipo  | Largo | Obligatoriedad |
|------------------|-------------------------------|-------|-------|----------------|
| NroLinDR         | Número de línea               | NUM   | 3     | 1              |
| TpoMov           | D(descuento) o R(recargo)     | ALFA  | 1     | 1              |
| GlosaDR          | Especificación                | ALFA  | 45    | 3              |
| TpoValor         | % o $                         | ALFA  | 1     | 1              |
| ValorDR          | Valor del descuento o recargo | NUM   | 18    | 1              |
| IndExeDR         | Indicador exención            | NUM   | 1     | 2              |

### 3.4 Datos de Referencia
Datos opcionales. Pueden ir hasta 40 repeticiones.

| Campo            | Descripción                      | Tipo  | Largo | Obligatoriedad |
|------------------|----------------------------------|-------|-------|----------------|
| NroLinRef        | Número de línea                  | NUM   | 2     | 1              |
| TpoDocRef        | Tipo documento referenciado      | ALFA  | 3     | 2              |
| FolioRef         | Folio del documento              | ALFA  | 18    | 2              |
| CodRef           | Código referencia                | ALFA  | 18    | 3              |
| RazonRef         | Razón referencia                 | ALFA  | 90    | 3              |
| CodVndor         | Código vendedor                  | ALFA  | 8     | 3              |
| CodCaja          | Código caja                      | ALFA  | 8     | 3              |

### 3.5 Datos de Georreferenciación (opcionales)

| Campo             | Descripción                      | Tipo  | Largo | Obligatoriedad |
|-------------------|----------------------------------|-------|-------|----------------|
| LatitudEmision    | Latitud de emisión               | ALFA  | 30    | 3              |
| LongitudEmision   | Longitud de emisión              | ALFA  | 30    | 3              |
| SistemaReferencia | Sistema de referencia (1-WGS84)  | NUM   | 1     | 3              |

### 3.6 Timbre Electrónico SII
El timbre electrónico contiene la firma sobre campos representativos del DTE y el Código de Autorización de Folios (CAF) entregado por el SII. Corresponde a la información del código de barras bidimensional PDF417.

## 4. Reglas de Validación y Consideraciones Importantes

### 4.1 Límites de Envío
- Máximo 500 boletas por envío para asegurar óptimo procesamiento.

### 4.2 Cambios Recientes (Versión 4.1 2024-12-31)
- Se agregaron los campos `<MedioPago>`, `<CorreoRecep>` y `<TelefonoRecep>` en la sección Encabezado.
- Se modificó la descripción y obligatoriedad de los campos `<RutRecep>` y `<RznSocEmisor>`.
- Obligatoriedad de información para montos mayores a 135 UF (Ley 21.713).

### 4.3 Indicadores para Boletas
El campo `<IndServicio>` indica el tipo de transacción:
- 1: Boletas de servicios periódicos
- 2: Boletas de servicios periódicos domiciliarios
- 3: Boletas de venta y servicios
- 4: Boleta de espectáculo emitida por cuenta de terceros

### 4.4 Medios de Pago
El campo `<MedioPago>` indica:
- 1: Efectivo
- 2: Pago electrónico
- 3: Transferencia electrónica
- 4: Cheque
- 5: Otro

### 4.5 Cálculos Críticos
- **Monto neto**: Suma de valores totales de ítems afectos - descuentos + recargos.
- **Monto total**: Monto neto + IVA + Monto exento.
- **Valor por línea de detalle**: (Precio unitario * Cantidad) - Monto descuento + Monto recargo.

### 4.6 Indicadores de Exención
- 1: Producto o servicio es exento o no afecto
- 2: Producto o servicio no es facturable
- 6: Producto o servicio no es facturable (negativo)

## 5. Requisitos de Conservación y Publicación

- Las boletas se deben mantener en la empresa durante seis años en formato XML.
- Deben estar disponibles para consulta en línea en la sucursal para el mes en curso y los dos meses anteriores.
- El emisor debe generar y enviar diariamente al SII un "Reporte de Consumo de Folios".
- El emisor debe publicar las boletas electrónicas en un sitio web para consulta por parte de los clientes durante tres meses.