{
    'name': 'Certificación SII Chile',
    'version': '1.0',
    'category': 'Accounting/Localization/Chile',
    'summary': 'Herramientas para facilitar el proceso de certificación con el SII en Chile',
    'description': """
    Módulo para facilitar el proceso de certificación con el SII en Chile
    ====================================================================

    Este módulo proporciona herramientas que facilitan el proceso de certificación 
    con el Servicio de Impuestos Internos (SII) de Chile para la facturación electrónica.

    Funcionalidades:
    ---------------
    * Panel de control para el proceso de certificación
    * Preparación automática de la base de datos
    * Creación de CAFs de demostración
    * Procesamiento de set de pruebas
    * Seguimiento de documentos de prueba
    """,
    'author': 'Tomás Díaz',
    'website': 'https://www.withinplaygames.com',
    'depends': ['account', 'l10n_cl', 'l10n_cl_edi'],
    'data': [
        'security/ir.model.access.csv',
        'views/certification_process_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}