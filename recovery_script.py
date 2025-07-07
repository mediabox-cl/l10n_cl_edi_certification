#!/usr/bin/env python3
"""
Script para recuperar documentos batch faltantes del SET básico
Ejecutar desde la consola de Odoo:

# Obtener el proceso de certificación
process = env['l10n_cl_edi.certification.process'].browse(PROCESS_ID)

# Recuperar documentos batch faltantes para SET básico 
# (especificar parsed_set_id si es para un set específico)
result = process.action_recover_missing_batch_documents('basico', parsed_set_id=PARSED_SET_ID)

# Luego regenerar el consolidado sin crear nuevos documentos
result = process.action_generate_batch_basico(parsed_set_id=PARSED_SET_ID)
"""

# Ejemplo de uso directo:
def recover_missing_batch_documents_basico(env, process_id, parsed_set_id=None):
    """
    Función helper para recuperar documentos batch faltantes del SET básico
    
    Args:
        env: Environment de Odoo
        process_id: ID del proceso de certificación
        parsed_set_id: ID del parsed set específico (opcional)
    """
    process = env['l10n_cl_edi.certification.process'].browse(process_id)
    if not process.exists():
        print(f"❌ Proceso {process_id} no encontrado")
        return False
    
    print(f"🔍 Recuperando documentos batch faltantes para proceso {process_id}")
    
    # Recuperar documentos faltantes
    recovery_result = process.action_recover_missing_batch_documents('basico', parsed_set_id=parsed_set_id)
    print(f"✅ Recuperación completada")
    
    return recovery_result

# Para usar desde consola:
# recovery_result = recover_missing_batch_documents_basico(env, PROCESS_ID, PARSED_SET_ID)