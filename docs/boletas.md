NSTRUCTIVO TÉCNICO - BOLETA ELECTRÓNICA
Sii - Servicio de Impuestos Internos
Instructivo para la Emisión y Envío de las Boletas Electrónicas de Ventas y Servicios
28/10/2021

Objetivo
Entregar los antecedentes necesarios para que los contribuyentes autorizados por el SII para emitir boleta electrónica, puedan generar y enviar al SII documentos válidos, de acuerdo a la normativa vigente.

Introducción
La Ley 21.210, que Moderniza la Legislación Tributaria, establece la obligatoriedad de emitir la boleta electrónica de ventas y servicios.

Contribuyentes que emiten factura electrónica: Obligatorio desde el 24 de agosto de 2020.

Contribuyentes que no emiten factura electrónica: Obligatorio desde el 24 de febrero de 2021.

La Resolución Exenta SII N° 74 instruye sobre el procedimiento, estableciendo la obligatoriedad a contar del 01 de enero de 2021 para facturadores electrónicos y del 01 de marzo de 2021 para los no facturadores.

Principales Cambios Introducidos por la Normativa
Obligatoriedad de emitir boleta electrónica.

Obligatoriedad de enviar al SII copia de cada boleta emitida.

Obligatoriedad de enviar diariamente el Resumen de Ventas Diarias (RVD).

La boleta electrónica deberá indicar separadamente el IVA y otros impuestos.

Se elimina la obligación de llevar el libro de boletas electrónicas.

Este es un resumen. Revise la Res. SII N° 74 completa en el sitio del SII.

Consideraciones Técnicas para la Generación y Envío
El modelo es similar al de la factura electrónica, pero con diferencias clave:

Protocolo de Seguridad: Todos los servicios de automatización deben usar TLS 1.2 o superior (Certificación desde 19/11/2021, Producción desde enero de 2022).

Servidores de Recepción: Se usarán servidores dedicados y distintos a los de factura electrónica.

Servicios Web: Para boleta electrónica se habilitarán servicios REST para autenticación y consultas (factura electrónica continúa con SOAP).

Token de Autenticación: Se debe obtener un token específico para boleta electrónica.

Folios: No hay cambios en la obtención de folios.

Resumen de Ventas (RVD): Utiliza el mismo schema XML que el antiguo RCOF, pero sin el detalle de folios.

Schema XML de Boleta: Actualizado. Límite de 500 boletas por envío.

Diagnóstico de Envíos: Se entregará mediante un servicio REST, consultando por el track id.

Track ID: Tendrá 15 dígitos (factura electrónica mantiene 10).

Términos de Uso de la API SII
El SII provee esta API para que los contribuyentes integren sus sistemas y cumplan con la normativa. El SII se reserva el derecho de suspender el acceso ante cualquier anormalidad o uso indebido.

Términos de uso general en el sitio web del SII.

Documentación de Referencia
Para más detalles, revise el Instructivo Técnico de Factura Electrónica en el sitio del SII.

Nuevos Servicios para Boleta Electrónica
La documentación de los nuevos servicios REST está disponible en la URL de la API del SII (https://www4c.sii.cl/bolcoreinternetui/api/).

Funcionalidades habilitadas:

Servicios de Autenticación (Semilla y Token).

Envío de Boleta Electrónica.

Consulta del estado del envío.

Consulta de Boleta Electrónica.

Esta documentación se generó de acuerdo al estándar OAS 3.0 (Swagger).

