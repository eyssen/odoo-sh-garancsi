# -*- coding: utf-8 -*-

import base64
import logging
import requests
import json
from uuid import uuid4
from werkzeug import urls

from odoo import api, fields, models
from odoo.addons.payment_saferpay.controllers.main import SaferpayController
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.tools.float_utils import float_round


INT_CURRENCIES = [
    u'BIF', u'XAF', u'XPF', u'CLP', u'KMF', u'DJF', u'GNF', u'JPY', u'MGA', u'PYG', u'RWF', u'KRW',
    u'VUV', u'VND', u'XOF'
]


class PaymentAcquirerSaferpay(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('saferpay', 'Saferpay')], ondelete={'saferpay': 'set default'})
    saferpay_username = fields.Char(string='Username', required_if_provider='saferpay', groups='base.group_user')
    saferpay_password = fields.Char(string='Password', required_if_provider='saferpay', groups='base.group_user')
    saferpay_terminal_id = fields.Char(string='Terminal ID', required_if_provider='saferpay', groups='base.group_user')
    saferpay_customer_id = fields.Char(string='Customer ID', required_if_provider='saferpay', groups='base.group_user')

    def _get_feature_support(self):
        res = super(PaymentAcquirerSaferpay, self)._get_feature_support()
        res['fees'].append('saferpay')
        return res

    def saferpay_compute_fees(self, amount, currency_id, country_id):
        if not self.fees_active:
            return 0.0
        country = self.env['res.country'].browse(country_id)
        if country and self.company_id.country_id.id == country.id:
            percentage = self.fees_dom_var
            fixed = self.fees_dom_fixed
        else:
            percentage = self.fees_int_var
            fixed = self.fees_int_fixed
        fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
        return fees

    @api.model
    def _get_saferpay_urls(self, environment):
        """ Saferpay URLS """
        if environment == 'prod':
            return 'https://www.saferpay.com/api'
        else:
            return 'https://test.saferpay.com/api'

    def saferpay_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.get_base_url()

        environment = 'prod' if self.state == 'enabled' else 'test'
        url = self._get_saferpay_urls(environment) + '/Payment/v1/PaymentPage/Initialize'

        tx = self.env['payment.transaction'].search([('reference', '=', values['reference'])], limit=1)
        payload = {
            "RequestHeader": {
                "SpecVersion": "1.20",
                "CustomerId": self.saferpay_customer_id,
                "RequestId": str(uuid4()),
                "RetryIndicator": 0
            },
            "TerminalId": self.saferpay_terminal_id,
            "Payment": {
                "Amount": {
                    "Value": str(int(values['amount'] if values['currency'].name in INT_CURRENCIES else float_round(values['amount'] * 100, 2))),
                    "CurrencyCode": values['currency'] and values['currency'].name or ""
                },
                "OrderId": values['reference'],
                "Description": values['reference']
            },
            "ReturnUrls": {
                "Success": urls.url_join(base_url, SaferpayController._return_url) + "?reference=%s&id=%s" % (values['reference'], str(tx.id)),
                "Fail": urls.url_join(base_url, SaferpayController._fail_url) + "?reference=%s&id=%s" % (values['reference'], str(tx.id))
            }
        }
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Authorization": 'Basic ' + base64.b64encode(('%s:%s' % (self.saferpay_username, self.saferpay_password)).encode()).decode()
        }
        response = requests.request("POST", url, data=json.dumps(payload), headers=headers)
        res = json.loads(response.text)
        url = res.get('RedirectUrl')
        tx.write({'saferpay_token': res.get('Token')})
        values.update({
            'form_url': url,
        })
        return values


class PaymentTransactionSaferpay(models.Model):
    _inherit = 'payment.transaction'

    saferpay_token = fields.Char('Saferpay Token')

    @api.model
    def _saferpay_form_get_tx_from_data(self, data):
        reference = data.get('OrderId')
        if not reference:
            error_msg = 'Saferpay: received data with missing reference (%s)' % reference
            raise ValidationError(error_msg)

        tx = self.env['payment.transaction'].search([('reference', '=', reference)])

        if not tx or len(tx) > 1:
            error_msg = 'Saferpay: received data for reference %s' % (reference)
            if not tx:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            raise ValidationError(error_msg)
        return tx[0]

    def _saferpay_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        # check what is buyed
        if int(data.get('Amount').get('Value', '0')) != int(self.amount if self.currency_id.name in INT_CURRENCIES else float_round(self.amount * 100, 2)):
            invalid_parameters.append(('Amount', data.get('Amount').get('Value', '0'), int(self.amount * 100)))
        if data.get('Amount').get('CurrencyCode') != self.currency_id.name:
            invalid_parameters.append(('currency', data.get('Amount').get('CurrencyCode'), self.currency_id.name))
        return invalid_parameters

    def _saferpay_form_validate(self, data):
        if self.state == 'done':
            return True
        status_code = data.get('Status')
        self.write({
            'date': fields.Datetime.now(),
        })
        if status_code == 'CAPTURED':
            self.write({'acquirer_reference': data.get('Id')})
            self._set_transaction_done()
        else:
            error = data.get('Behavior') + ': ' + data.get('ErrorMessage')
            if data.get('ErrorDetail'):
                error += '\n,'.join(e for e in data.get('ErrorDetail'))
            self.write({
                'state_message': error,
            })
            self.write({'acquirer_reference': data.get('TransactionId') or ""})
            self._set_transaction_error(msg=error)
