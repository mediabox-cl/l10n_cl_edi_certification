# ROADMAP del Módulo de Certificación SII (l10n_cl_edi_certification)

Este documento detalla las tareas completadas y los próximos pasos en el desarrollo y depuración del módulo.

## 1. Análisis Inicial del Código Base

*   **Estado**: Completado.
*   **Descripción**: Se realizó un análisis exhaustivo de la estructura del módulo, modelos clave (`CertificationProcess`, `CertificationCaseDte`, `CertificationDocumentGenerator`, `CertificationBatchFile`), y el flujo de generación de DTEs individuales y consolidados.
*   **Documentación Generada**: `GEMINI_ANALYSIS.md`

## 2. Corrección de Generación de Envío Consolidado (SET BÁSICO)

*   **Problema Identificado**: Error `Unicode strings with encoding declaration are not supported` al firmar el XML consolidado del SET BÁSICO.
*   **Causa Raíz**: La función `etree.tostring` estaba incluyendo la declaración XML (`<?xml ...?>`) cuando la función de firma de Odoo esperaba un fragmento sin ella.
*   **Solución Implementada**: Se modificó `models/certification_batch_file.py` para cambiar `xml_declaration=True` a `xml_declaration=False` en la llamada a `etree.tostring`.
*   **Estado**: **Completado y Verificado**. El archivo `BASICO_762352915.xml` se generó y validó correctamente.

## 3. Corrección de Generación de Envío Consolidado (SET GUÍAS DE DESPACHO)

*   **Problema Identificado**: Error `Los siguientes casos no tienen documentos generados` al intentar generar el envío consolidado de Guías de Despacho.
*   **Causa Raíz (Inicial)**: La validación en `_validate_ready_for_batch_generation` solo verificaba `generated_account_move_id`, ignorando `generated_stock_picking_id`.
*   **Solución Implementada (Parcial)**: Se modificó `models/certification_batch_file.py` para que la validación considere ambos tipos de documentos.
*   **Nuevo Problema Identificado**: Después de la corrección parcial, el log mostró que las guías se creaban en estado 'assigned' pero no se generaba su DTE.
*   **Causa Raíz (Actual)**: El método `_finalize_delivery_guide` en `models/certification_document_generator.py` no invoca la lógica de generación de DTE para `stock.picking` en modo batch. El método `create_delivery_guide()` del módulo base (`l10n_cl_edi_stock`) es el responsable de esto.
*   **Estado**: **Completado y Verificado**.
*   **Solución Implementada**:
    1.  Se añadió `generated_batch_stock_picking_id` a `models/certification_case_dte.py`.
    2.  Se modificó `_finalize_delivery_guide` en `models/certification_document_generator.py` para llamar a `picking.create_delivery_guide()` en modo batch, asegurando la generación del DTE de la guía.
    3.  Se actualizó `_regenerate_test_documents` en `models/certification_batch_file.py` para manejar correctamente la obtención y verificación del DTE (`l10n_cl_dte_file`) tanto de `account.move` como de `stock.picking` en modo batch.
