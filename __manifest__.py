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
    * Preparación automática de la base de datos para certificación
    * Creación correcta del tipo de documento SET para referencias
    * Validación de documentos para el set de pruebas
    """,
    'author': 'Tomás Díaz',
    'website': 'https://www.withinplaygames.com',
    'depends': ['account', 'l10n_cl', 'l10n_cl_edi'],
    'data': [
        'security/ir.model.access.csv',
        'views/certification_menu.xml',
        'data/document_type_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}