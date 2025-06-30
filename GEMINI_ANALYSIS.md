# Análisis del Módulo de Certificación SII (l10n_cl_edi_certification)

Este documento resume la arquitectura y el flujo de datos del módulo, con un enfoque en la generación de Documentos Tributarios Electrónicos (DTE) para el proceso de certificación del SII en Chile.

## 1. Arquitectura General

El módulo está diseñado como un orquestador sobre los módulos de localización chilena de Odoo (`l10n_cl`, `l10n_cl_edi`, etc.). Su objetivo es automatizar y guiar al usuario a través de las etapas del proceso de certificación del SII.

### Modelos Principales

-   **`l10n_cl_edi.certification.process`**:
    -   Es el modelo central que actúa como "panel de control".
    -   Mantiene el estado general del proceso (`preparation`, `configuration`, `generation`, `completed`).
    -   Almacena la configuración global (diario de certificación, partner del SII, etc.).
    -   Contiene los `One2many` a los sets de pruebas, casos DTE y documentos generados.
    -   Dispara las acciones principales (cargar sets, generar DTEs, generar libros, etc.).

-   **`l10n_cl_edi.certification.parsed_set`**:
    -   Representa un "Set de Pruebas" completo proporcionado por el SII (Ej: Set Básico, Set de Guías de Despacho).
    -   Se crea a partir del archivo XML cargado por el usuario.
    -   Agrupa un conjunto de `certification.case.dte`.

-   **`l10n_cl_edi.certification.case.dte`**:
    -   Representa un caso de prueba individual dentro de un set (Ej: "Emitir Factura Exenta a Cliente Extranjero").
    -   Contiene toda la información específica para generar un único DTE: tipo de documento, ítems, descuentos, referencias, etc.
    -   Tiene dos campos clave para vincular los documentos generados:
        -   `generated_account_move_id`: Almacena el `account.move` (DTE) generado para la validación individual.
        -   `generated_batch_account_move_id`: Almacena el `account.move` **regenerado** para el envío consolidado.

-   **`l10n_cl_edi.certification.document.generator`** (`TransientModel`):
    -   Actúa como un motor de generación. No almacena datos permanentemente.
    -   Toma un `certification.case.dte` y ejecuta la lógica para crear el `account.move` o `stock.picking` correspondiente.
    -   Implementa el flujo recomendado: **`sale.order` -> `account.move`**, lo que asegura que todos los campos y relaciones se configuren correctamente a través de la lógica nativa de Odoo.
    -   Su método `generate_document(for_batch=False)` es el punto de entrada. El parámetro `for_batch` es crítico para diferenciar la generación individual de la regeneración para el envío consolidado.

-   **`l10n_cl_edi.certification.batch_file`**:
    -   Representa el archivo XML final de "Envío DTE" que se envía al SII.
    -   Contiene la lógica para agrupar múltiples DTEs en un solo envío.
    -   Este es el componente central del problema actual.

## 2. Flujo de Datos: Generación de DTE Individual

El proceso para generar un DTE para un caso de prueba es el siguiente:

1.  El usuario, desde la vista de `certification.process`, ejecuta la acción para generar documentos.
2.  El sistema itera sobre los `certification.case.dte` pendientes.
3.  Para cada caso, se instancia un `certification.document.generator`.
4.  Se llama a `document_generator.generate_document(for_batch=False)`.
5.  Dentro del generador:
    a. Se crea un `sale.order` con los datos del caso (cliente, productos/ítems, etc.).
    b. Se confirma el `sale.order`.
    c. Se invoca `sale_order._create_invoices()` para crear un `account.move` en estado `draft`.
    d. Se configuran los campos específicos de la localización chilena en el `account.move` (tipo de documento, referencias, etc.).
    e. El `account.move` generado se vincula al `case.dte` a través del campo `generated_account_move_id`.
6.  El usuario debe validar manualmente este `account.move` (publicarlo). Al hacerlo, el módulo `l10n_cl_edi` se encarga de generar el XML del DTE individual y lo adjunta al `account.move` en el campo `l10n_cl_dte_file`.

## 3. Flujo de Datos: Generación de Envío DTE Consolidado (El Proceso que Falla)

Este proceso es más complejo y se encapsula en el modelo `certification.batch_file`.

1.  El usuario dispara la acción para generar un envío consolidado (Ej: "Generar SET BÁSICO").
2.  Se llama al método `_generate_batch_file` en `certification.batch_file`.
3.  **Paso 1: Regenerar Documentos (`_regenerate_test_documents`)**
    a. Se identifican los `case.dte` relevantes para el set.
    b. Se itera sobre cada caso y se llama a `document_generator.generate_document(for_batch=True)`.
    c. Esta llamada crea un **nuevo** `account.move` (diferente al de la validación individual).
    d. Este nuevo `account.move` se vincula al campo `generated_batch_account_move_id` del caso.
    e. **Crucial**: Dentro del generador, si `for_batch` es `True`, el `account.move` se confirma (`action_post()`) programáticamente para forzar la generación del XML del DTE por parte del módulo `l10n_cl_edi`.

4.  **Paso 2: Extraer Nodos DTE (`_extract_dte_nodes`)**
    a. El método itera sobre los `account.move` recién regenerados (los del campo `generated_batch_account_move_id`).
    b. Para cada `account.move`, intenta acceder al XML adjunto (`l10n_cl_dte_file`).
    c. Parsea el contenido del XML y extrae únicamente el nodo `<DTE>`.
    d. **Punto de Falla Potencial #1**: Si el XML no se generó en el paso anterior (por un error o un problema de timing), la extracción falla. El log "No se encontró nodo DTE en documento" apunta a este problema.

5.  **Paso 3: Construir XML Consolidado (`_build_consolidated_setdte`)**
    a. Se crea una nueva estructura XML (`<EnvioDTE>`) desde cero usando `lxml`.
    b. Se genera una `<Caratula>` (portada) consolidada con los totales.
    c. Se insertan todos los nodos `<DTE>` extraídos en el paso anterior dentro del `<SetDTE>`.
    d. **Punto de Falla Potencial #2**: Errores en la construcción de este XML (namespaces, estructura, etc.) o en el proceso de firma digital (`_sign_full_xml`) pueden causar la falla final.

## 4. Hipótesis del Problema Actual

El error descrito ("el proceso parece generar todos los DTEs correctamente pero falla al generar el nuevo documento") se alinea perfectamente con una falla en el **Paso 2 (`_extract_dte_nodes`)** del flujo de envío consolidado.

La hipótesis principal es que la llamada `invoice.action_post()` dentro del generador en modo `for_batch=True` no está resultando en la creación y guardado del `l10n_cl_dte_file` en el `account.move` de manera síncrona. Cuando `_extract_dte_nodes` se ejecuta inmediatamente después, el archivo aún no existe, y el proceso se interrumpe.

### Próximos Pasos para Debugging

1.  **Añadir Logging Detallado**: Incrementar los logs en `_regenerate_test_documents` y `_extract_dte_nodes` para verificar:
    -   Si el `l10n_cl_dte_file` existe en el `account.move` batch inmediatamente después de la llamada a `action_post()`.
    -   El contenido del XML si se encuentra, para asegurar que es válido.
    -   La estructura del XML si no se encuentra el nodo `<DTE>`.
2.  **Inspección Manual**: Detener el proceso (si es posible) después de la regeneración y antes de la extracción para inspeccionar manualmente los `account.move` generados en el campo `generated_batch_account_move_id` y ver si tienen un XML adjunto.
3.  **Forzar Sincronización**: Si es un problema de timing, podría ser necesario forzar un refresco del registro (`invoice.refresh()`) o un commit a la base de datos (`self.env.cr.commit()`) entre la regeneración y la extracción, aunque esto último debe usarse con precaución.
