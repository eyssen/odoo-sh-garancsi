# -*- coding: utf-8 -*-
{
    "name": 'Saferpay Payment Gateway',
    "author": 'Warlock Technologies Pvt Ltd.',
    "description": """Saferpay Payment Gateway
    """,
    "summary": """Saferpay Payment Gateway""",
    "version": '14.0.1.0',
    "license": 'OPL-1',
    "support": 'support@warlocktechnologies.com',
    "website": 'http://warlocktechnologies.com',
    "price": 100.00,
    "currency": "USD",
    "category": 'Payment',
    "depends": ['payment'],
    "images": ['images/screen_image.png'],
    "data": [
        'views/saferpay.xml',
        'views/saferpay_view.xml',
        'data/saferpay_data.xml',
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "post_init_hook": 'create_missing_journal_for_acquirers',
    "uninstall_hook": 'uninstall_hook',
}
