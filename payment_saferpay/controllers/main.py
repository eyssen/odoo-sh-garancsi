# -*- coding: utf-8 -*-

import base64
import json
import logging
import pprint
import requests
import werkzeug
from uuid import uuid4

from odoo import http
from odoo.http import request
from odoo.tools.float_utils import float_round


INT_CURRENCIES = [
    u'BIF', u'XAF', u'XPF', u'CLP', u'KMF', u'DJF', u'GNF', u'JPY', u'MGA', u'PYG', u'RWF', u'KRW',
    u'VUV', u'VND', u'XOF'
]


class SaferpayController(http.Controller):
    _return_url = '/payment/saferpay/return'
    _fail_url = '/payment/saferpay/fail'

    @http.route([_return_url, _fail_url], type='http', auth='public', csrf=False)
    def saferpay_return_feedback(self, **post):
        tx = request.env['payment.transaction'].sudo().search([('id', '=', post.get('id')), ('reference', '=', post.get('reference'))], limit=1)
        if tx and tx.saferpay_token:
            data = {}
            payload = {
                "RequestHeader": {
                    "SpecVersion": "1.20",
                    "CustomerId": tx.acquirer_id.saferpay_customer_id,
                    "RequestId": str(uuid4()),
                    "RetryIndicator": 0
                },
                "Token": tx.saferpay_token
            }
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "Authorization": 'Basic ' + base64.b64encode(('%s:%s' % (tx.acquirer_id.saferpay_username, tx.acquirer_id.saferpay_password)).encode()).decode()
            }
            environment = 'prod' if tx.acquirer_id.state == 'enabled' else 'test'
            url = tx.acquirer_id._get_saferpay_urls(environment) + '/Payment/v1/PaymentPage/Assert'
            response = requests.request("POST", url, data=json.dumps(payload), headers=headers)
            if response.status_code == 200:
                res = json.loads(response.text)
                data.update(res.get('Transaction'))
                capture_payload = {
                    "RequestHeader": {
                        "SpecVersion": "1.20",
                        "CustomerId": tx.acquirer_id.saferpay_customer_id,
                        "RequestId": str(uuid4()),
                        "RetryIndicator": 0
                    },
                    "TransactionReference": {
                        "TransactionId": "723n4MAjMdhjSAhAKEUdA8jtl9jb"
                    }
                }
                capture_url = tx.acquirer_id._get_saferpay_urls(environment) + '/Payment/v1/Transaction/Capture'
                response = requests.request("POST", capture_url, data=json.dumps(capture_payload), headers=headers)
                data['Status'] = 'CAPTURED'
            else:
                data.update(json.loads(response.text))
                data.update({
                    'OrderId': tx.reference,
                    'Amount': {
                        'CurrencyCode': tx.currency_id.name,
                        'Value': str(int(tx.amount if tx.currency_id.name in INT_CURRENCIES else float_round(tx.amount * 100, 2)))
                    }
                })
            request.env['payment.transaction'].sudo().form_feedback(data, 'saferpay')
            return werkzeug.utils.redirect('/payment/process')
        return werkzeug.utils.redirect('/shop')
