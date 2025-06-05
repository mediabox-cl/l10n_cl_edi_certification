# Script de Migración - Limitaciones de Longitud de Campos DTE

## 📋 **Objetivo**
Crear un script de migración independiente para aplicar en producción que normalice campos que excedan los límites del esquema XSD del SII.

## 🎯 **Campos a Migrar**

### **res.partner (Partners/Clientes)**
| Campo | Límite SII | Descripción | Acción |
|-------|------------|-------------|---------|
| `name` | 100 chars | Razón Social | Truncar por palabras + "..." |
| `l10n_cl_activity_description` | 40 chars | Giro/Actividad | Truncar por palabras + "..." |
| `street` | 60 chars | Dirección | Truncar por palabras + "..." |

### **product.product (Productos)**
| Campo | Límite SII | Descripción | Acción |
|-------|------------|-------------|---------|
| `name` | 80 chars | Nombre del Item | Truncar por palabras + "..." |
| `description_sale` | 1000 chars | Descripción del Item | Truncar por palabras + "..." |

## 🔍 **Funcionalidades del Script**

### **1. Análisis Previo**
```python
def analyze_data():
    """
    Analiza la base de datos para identificar registros problemáticos
    """
    # Contar registros que excedan límites por tabla/campo
    # Generar reporte de impacto
    # Mostrar ejemplos de truncados propuestos
    # Calcular tiempo estimado de migración
```

### **2. Backup Automático**
```python
def create_backup():
    """
    Crea backup de tablas afectadas antes de migrar
    """
    # Backup de res_partner (campos: name, l10n_cl_activity_description, street)
    # Backup de product_product (campos: name, description_sale)
    # Timestamp en nombre del backup
    # Verificación de integridad del backup
```

### **3. Migración Inteligente**
```python
def smart_truncate(text, max_length):
    """
    Trunca texto de forma inteligente respetando palabras
    """
    # Si texto <= max_length: no cambiar
    # Truncar por palabras completas
    # Agregar "..." solo si se truncó
    # Preservar mayúsculas/minúsculas originales
    # Limpiar espacios múltiples
```

### **4. Procesamiento por Lotes**
```python
def migrate_in_batches():
    """
    Procesa registros en lotes para evitar timeouts
    """
    # Lotes de 100 registros
    # Commit cada lote
    # Progress bar con ETA
    # Manejo de errores por registro individual
    # Log detallado de cambios
```

### **5. Validación Post-Migración**
```python
def validate_migration():
    """
    Valida que la migración fue exitosa
    """
    # Verificar que no hay campos que excedan límites
    # Comparar conteos antes/después
    # Verificar integridad referencial
    # Generar reporte de cambios realizados
```

## 📊 **Reportes Generados**

### **1. Reporte de Análisis Previo**
```
=== ANÁLISIS DE CAMPOS LARGOS ===
Tabla: res.partner
- Campo 'name': 15 registros exceden 100 chars (máx: 156 chars)
- Campo 'l10n_cl_activity_description': 8 registros exceden 40 chars (máx: 67 chars)
- Campo 'street': 23 registros exceden 60 chars (máx: 89 chars)

Tabla: product.product  
- Campo 'name': 42 registros exceden 80 chars (máx: 134 chars)
- Campo 'description_sale': 3 registros exceden 1000 chars (máx: 1245 chars)

TOTAL REGISTROS A MIGRAR: 91
TIEMPO ESTIMADO: 2-3 minutos
```

### **2. Reporte de Cambios Realizados**
```
=== MIGRACIÓN COMPLETADA ===
Fecha: 2025-01-XX XX:XX:XX
Backup creado: backup_field_migration_20250101_123456.sql

CAMBIOS REALIZADOS:
res.partner (ID: 123):
  name: "Empresa de Servicios Tecnológicos y Consultoría Avanzada Limitada" 
     -> "Empresa de Servicios Tecnológicos y Consultoría Avanzada..."
  
product.product (ID: 456):
  name: "Servicio de Consultoría Especializada en Implementación de Sistemas ERP Complejos"
     -> "Servicio de Consultoría Especializada en Implementación de Sistemas..."

RESUMEN:
- res.partner: 46 registros modificados
- product.product: 45 registros modificados
- Errores: 0
- Tiempo total: 2m 34s
```

## 🛠 **Estructura del Script**

### **Archivos Necesarios**
```
migration_field_limits/
├── migrate.py              # Script principal
├── config.py              # Configuración de límites
├── utils.py               # Funciones auxiliares
├── backup.py              # Manejo de backups
├── reports.py             # Generación de reportes
└── README.md              # Instrucciones de uso
```

### **Configuración**
```python
# config.py
FIELD_LIMITS = {
    'res.partner': {
        'name': 100,
        'l10n_cl_activity_description': 40,
        'street': 60,
    },
    'product.product': {
        'name': 80,
        'description_sale': 1000,
    }
}

BATCH_SIZE = 100
BACKUP_ENABLED = True
DRY_RUN = False  # True para simular sin cambios
```

## 🚀 **Uso del Script**

### **1. Análisis (Sin Cambios)**
```bash
python migrate.py --analyze
```

### **2. Migración Completa**
```bash
python migrate.py --migrate --backup
```

### **3. Solo Backup**
```bash
python migrate.py --backup-only
```

### **4. Validación Post-Migración**
```bash
python migrate.py --validate
```

## ⚠️ **Consideraciones de Seguridad**

1. **Backup Obligatorio**: El script debe crear backup antes de cualquier cambio
2. **Dry Run**: Opción para simular cambios sin aplicarlos
3. **Rollback**: Procedimiento para revertir cambios si es necesario
4. **Logs Detallados**: Registro completo de todas las operaciones
5. **Validación de Conexión**: Verificar conexión a BD antes de iniciar
6. **Permisos**: Verificar permisos de escritura en tablas objetivo

## 📝 **Notas de Implementación**

- **Independiente**: No debe depender del módulo l10n_cl_edi_certification
- **Portable**: Debe funcionar en cualquier instalación de Odoo con datos chilenos
- **Configurable**: Límites y campos deben ser fácilmente modificables
- **Robusto**: Manejo de errores y recuperación automática
- **Informativo**: Reportes claros y detallados para el usuario

## 🔄 **Procedimiento de Rollback**

En caso de necesitar revertir los cambios:

```sql
-- Restaurar desde backup
-- (Los comandos específicos dependerán del formato del backup)
```

El script debe incluir instrucciones claras de rollback y verificación de que la restauración fue exitosa. 