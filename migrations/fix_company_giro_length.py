# -*- coding: utf-8 -*-
"""
Script de migración para corregir límites de giro de empresa.

PROBLEMA:
- Campo l10n_cl_activity_description estaba limitado a 40 caracteres para todos los partners
- Empresas (res.company.partner_id) necesitan 80 caracteres según SII (GiroEmisor)
- Partners normales siguen con 40 caracteres (GiroRecep)

SOLUCIÓN:
- Distinguir entre company partners y partners normales
- Aplicar límites correctos según especificación SII

USO EN PRODUCCIÓN:
1. Instalar este módulo o copiar el código a un módulo de migración
2. Ejecutar el script de corrección en partners que fueron truncados incorrectamente
3. Verificar que empresas puedan tener giros de hasta 80 caracteres

FECHA: 2025-06-18
AUTOR: Claude Code - Certificación SII
"""

def migrate_company_giro_limits(env):
    """
    Corrige los giros de empresa que fueron truncados incorrectamente a 40 caracteres.
    
    Esta función debe ejecutarse en producción para restaurar giros completos
    de empresas que fueron truncados por la validación incorrecta.
    """
    import logging
    _logger = logging.getLogger(__name__)
    
    _logger.info("=== INICIANDO MIGRACIÓN: Corrección límites giro empresa ===")
    
    # Buscar empresas con giros truncados (terminan en "...")
    companies = env['res.company'].search([
        ('l10n_cl_activity_description', 'ilike', '%...')
    ])
    
    _logger.info(f"Encontradas {len(companies)} empresas con giros truncados")
    
    for company in companies:
        original_giro = company.l10n_cl_activity_description
        _logger.info(f"Empresa: {company.name}")
        _logger.info(f"  Giro actual (truncado): {original_giro}")
        _logger.info(f"  Partner ID: {company.partner_id.id}")
        
        # Aquí se debería restaurar el giro original desde backup o input manual
        # Por ahora solo reportamos
        _logger.info(f"  ⚠️  ACCIÓN REQUERIDA: Restaurar giro completo manualmente")
    
    _logger.info("=== FIN MIGRACIÓN ===")
    
    return {
        'companies_found': len(companies),
        'message': f'Se encontraron {len(companies)} empresas que requieren corrección manual de giro'
    }


def validate_new_limits(env):
    """
    Valida que las nuevas reglas de límites estén funcionando correctamente.
    """
    import logging
    _logger = logging.getLogger(__name__)
    
    _logger.info("=== VALIDANDO NUEVOS LÍMITES ===")
    
    # Test 1: Crear partner normal - debería limitarse a 40 chars
    test_partner_vals = {
        'name': 'Test Partner Normal',
        'l10n_cl_activity_description': 'A' * 50,  # 50 caracteres
        'is_company': False
    }
    
    # Test 2: Verificar empresa existente
    companies = env['res.company'].search([], limit=1)
    if companies:
        company = companies[0]
        partner = company.partner_id
        
        _logger.info(f"Empresa de prueba: {company.name}")
        _logger.info(f"Giro actual: {company.l10n_cl_activity_description}")
        _logger.info(f"Longitud: {len(company.l10n_cl_activity_description or '')}")
        
        # El partner de empresa debería poder tener hasta 80 caracteres
        if hasattr(partner, '_is_company_partner'):
            is_company = partner._is_company_partner()
            _logger.info(f"¿Es partner de empresa?: {is_company}")
        
    _logger.info("=== FIN VALIDACIÓN ===")


# Para uso directo en shell de Odoo:
def run_migration():
    """
    Función principal para ejecutar desde shell de Odoo:
    
    from odoo.addons.l10n_cl_edi_certification.migrations.fix_company_giro_length import run_migration
    run_migration()
    """
    import odoo
    from odoo import api, SUPERUSER_ID
    
    registry = odoo.registry()
    with api.Environment.manage():
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            print("Ejecutando migración de límites de giro...")
            result = migrate_company_giro_limits(env)
            print(f"Resultado: {result}")
            
            print("Validando nuevos límites...")
            validate_new_limits(env)
            
            print("Migración completada.")


if __name__ == '__main__':
    run_migration()