# -*- coding: utf-8 -*-

from . import models
from . import wizard

def uninstall_hook(cr, registry):
    """
    Hook ejecutado al desinstalar el módulo.
    Elimina todos los registros creados por los modelos del módulo de certificación.
    """
    from odoo import api, SUPERUSER_ID
    import logging
    
    _logger = logging.getLogger(__name__)
    _logger.info("Iniciando limpieza de registros del módulo l10n_cl_edi_certification...")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        # Lista de modelos a limpiar en orden inverso de dependencias
        # (eliminar primero los registros dependientes)
        models_to_clean = [
            # Primero los modelos hijo/dependientes
            'l10n_cl_edi.certification.case.dte.item',
            'l10n_cl_edi.certification.case.dte.reference', 
            'l10n_cl_edi.certification.case.dte',
            'l10n_cl_edi.certification.purchase_book.entry',
            'l10n_cl_edi.certification.instructional_set',
            'l10n_cl_edi.certification.parsed_set',
            # Finalmente el modelo principal
            'l10n_cl_edi.certification.process'
        ]
        
        total_deleted = 0
        
        for model_name in models_to_clean:
            try:
                if model_name in env:
                    model = env[model_name]
                    records = model.search([])
                    if records:
                        count = len(records)
                        records.unlink()
                        total_deleted += count
                        _logger.info(f"Eliminados {count} registros del modelo {model_name}")
                    else:
                        _logger.info(f"No se encontraron registros en el modelo {model_name}")
                else:
                    _logger.warning(f"Modelo {model_name} no encontrado en el entorno")
            except Exception as e:
                _logger.error(f"Error eliminando registros del modelo {model_name}: {str(e)}")
        
        # Eliminar el tipo de documento SET si fue creado por el módulo
        try:
            set_doc_type = env['l10n_latam.document.type'].search([
                ('code', '=', 'SET'),
                ('country_id.code', '=', 'CL')
            ])
            if set_doc_type:
                set_doc_type.unlink()
                _logger.info("Eliminado tipo de documento SET")
        except Exception as e:
            _logger.error(f"Error eliminando tipo de documento SET: {str(e)}")
        
        # Limpiar registros de account.move que tengan referencia al módulo
        try:
            moves_with_certification = env['account.move'].search([
                ('l10n_cl_edi_certification_id', '!=', False)
            ])
            if moves_with_certification:
                # Solo limpiar la referencia, no eliminar los documentos
                moves_with_certification.write({'l10n_cl_edi_certification_id': False})
                _logger.info(f"Limpiada referencia de certificación en {len(moves_with_certification)} documentos account.move")
        except Exception as e:
            _logger.error(f"Error limpiando referencias en account.move: {str(e)}")
        
        # Confirmar transacción
        cr.commit()
        
        _logger.info(f"Limpieza completada. Total de registros eliminados: {total_deleted}")
        
    except Exception as e:
        _logger.error(f"Error durante la limpieza del módulo: {str(e)}")
        cr.rollback()
        raise