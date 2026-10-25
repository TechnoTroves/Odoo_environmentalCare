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
    'depends': ['base','mail','stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu_views.xml',
        'views/event_views.xml',
        'views/workshop_views.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}