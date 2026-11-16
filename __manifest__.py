# -*- coding: utf-8 -*-
{
    'name': 'Env Care',
    'version': '18.0.1.0.0',
    'category': 'Services',
    'summary': 'Test Summary',
    'author': 'Env - IT',
    'website': '',
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'depends': ['base','mail','stock','website'],
    'data': [
        'security/envcare_security.xml',
        'security/ir.model.access.csv',
        'views/menu_views.xml',
        'views/event_views.xml',
        'views/workshop_views.xml',
        'views/hr_views.xml',
        'views/website_templates.xml'
    ],
    'assets': {
        'web.assets_frontend': [
            'environmental_care/static/src/js/table_search.js',
            'environmental_care/static/src/js/html_input.js',
            'environmental_care/static/src/js/row_editor.js',
            'environmental_care/static/src/scss/html_input.scss',
            'environmental_care/static/src/scss/envcare_website.scss'
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}