# Roadmap: Módulo de Certificación SII Chile

## Visión General
Este roadmap define las próximas etapas de desarrollo para el módulo de Certificación SII de Chile, con el objetivo de facilitar el proceso oficial de certificación ante el Servicio de Impuestos Internos (SII).

## Principios Guía
- **Utilizar funcionalidad existente**: Aprovechar las capacidades del módulo l10n_cl_edi siempre que sea posible
- **Foco en seguimiento**: El módulo debe coordinar y dar seguimiento al proceso, no reimplementar funcionalidad
- **Automatización de tareas repetitivas**: Facilitar los pasos mecánicos pero mantener control en decisiones críticas

## Plan de Desarrollo

### Fase 1: Procesamiento del Set de Pruebas

#### 1.1 Parser para Archivos Set de Pruebas (Alta Prioridad)
- Desarrollar parser para archivos de texto del SII (formato .txt)
- Identificar los diferentes casos de prueba dentro del archivo
- Extraer la información necesaria para cada caso (montos, productos, fechas, etc.)

#### 1.2 Generación Automática de Maestros (Alta Prioridad)
- Crear productos automáticamente basados en el set de pruebas
- Generar partners necesarios para los documentos
- Configurar impuestos y otros datos requeridos

#### 1.3 Generación de Documentos (Alta Prioridad)
- Implementar la creación automática de documentos según los casos
- Configurar referencias y datos adicionales
- Asegurar que los documentos cumplan con los requisitos SII

### Fase 2: Integración con CAFs

#### 2.1 Acceso a Gestión de CAFs (Media Prioridad)
- Integrar acceso directo a la funcionalidad de carga de CAFs
- Implementar validaciones para verificar CAFs necesarios
- Mostrar estado de CAFs requeridos vs. disponibles

#### 2.2 Validación de Asignación de CAFs (Media Prioridad)
- Verificar asignación correcta de CAFs a documentos
- Reportar problemas o inconsistencias
- Guiar en la resolución de problemas

### Fase 3: Seguimiento del Envío de Documentos

#### 3.1 Integración con Flujo de Envío (Media Prioridad)
- Utilizar funcionalidad existente de envío de documentos
- Implementar seguimiento del estado de envío
- Reportar resultados y problemas

#### 3.2 Panel de Control de Estado (Media Prioridad)
- Desarrollar dashboard para visualizar estado de documentos
- Agrupar por casos del set de pruebas
- Mostrar estado de cada documento en el proceso

### Fase 4: Integración con Etapa de Intercambio

#### 4.1 Seguimiento de Intercambio (Baja Prioridad)
- Implementar registro de intercambios de documentos
- Utilizar funcionalidad existente para intercambios
- Validar requisitos del SII para esta etapa

### Fase 5: Gestión de Muestras de Impresión

#### 5.1 Generación de Muestras (Media Prioridad)
- Integrar con funcionalidad existente de generación de PDFs
- Facilitar agrupación de documentos para envío de muestras
- Verificar presencia de timbre electrónico

#### 5.2 Control de Envío de Muestras (Baja Prioridad)
- Registrar envío de muestras
- Seguimiento de aprobación

### Fase 6: Declaración y Cierre de Certificación

#### 6.1 Asistente de Verificación Final (Baja Prioridad)
- Verificar que todos los pasos han sido completados correctamente
- Generar reporte de estado para revisión
- Preparar declaración final

#### 6.2 Registro de Certificación (Baja Prioridad)
- Implementar registro formal de certificación completada
- Almacenar datos relevantes (fechas, resoluciones, etc.)
- Generar documentación de referencia

## Cronograma Propuesto

| Fase | Actividad | Prioridad | Semanas Estimadas |
|------|-----------|-----------|-------------------|
| 1.1 | Parser para Set de Pruebas | Alta | 2 |
| 1.2 | Generación de Maestros | Alta | 1 |
| 1.3 | Generación de Documentos | Alta | 2 |
| 2.1 | Acceso a Gestión CAFs | Media | 1 |
| 2.2 | Validación de CAFs | Media | 1 |
| 3.1 | Integración con Envío | Media | 2 |
| 3.2 | Panel de Control | Media | 2 |
| 4.1 | Seguimiento de Intercambio | Baja | 1 |
| 5.1 | Gestión de Muestras | Media | 1 |
| 5.2 | Control de Envío | Baja | 1 |
| 6.1 | Verificación Final | Baja | 1 |
| 6.2 | Registro de Certificación | Baja | 1 |

## Próximos Pasos Inmediatos
1. Desarrollar el parser para el set de pruebas
2. Implementar la creación de maestros (productos, partners)
3. Desarrollar la generación automática de documentos

## Consideraciones Técnicas
- El módulo debe ser compatible con instalaciones existentes de l10n_cl
- Se debe mantener trazabilidad completa del proceso
- Las acciones automáticas deben ser reversibles o tener opciones de corrección manual
- Considerar implementar un modelo de "Sesión de Certificación" para manejar múltiples intentos