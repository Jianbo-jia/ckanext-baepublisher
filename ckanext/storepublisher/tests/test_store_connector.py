# -*- coding: utf-8 -*-

# Copyright (C) 2015 - 2017 Conwet Lab., Universidad Politécnica de Madrid

# This file is part of CKAN Store Publisher Extension.

# CKAN Store Publisher Extension is free software: you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# CKAN Store Publisher Extension is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with CKAN Store Publisher Extension.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals
import ckanext.storepublisher.store_connector as store_connector

import unittest
import requests
from decimal import Decimal

from mock import MagicMock, call
from nose_parameterized import parameterized

# Need to be defined here, since it will be used as tests parameter
ConnectionError = requests.ConnectionError

DATASET = {
    'id': 'example_id',
    'title': 'Dataset A',
    'version': '1.0',
    'notes': 'Dataset description. This can be a very long field and can include markdown syntax',
    'href': 'www.imanexample.com',
    'type': 'testField',
    'name': 'Dataset A',
    'license_title': 'Beerware',
}

OFFERING_INFO_BASE = {
    'pkg_id': 'identifier',
    'name': 'Offering 1',
    'description': 'Dataset description. This can be a very long field and can include markdown syntax',
    'catalog': 'catalog1',
    'version': '1.7',
    'categories': ['tag1', 'tag2', 'tag3'],
    'license_title': 'Creative Commons',
    'license_description': 'This is an example description',
    'price': 1,
    'is_open': True,
    'image_base64': 'IMGB4/png/data'
}

EXCEPTION_MSG = 'Exception Message'
BASE_SITE_URL = 'https://localhost:8474'
BASE_STORE_URL = 'https://store.example.com:7458'
CONNECTION_ERROR_MSG = 'It was impossible to connect with the Store'


class StoreConnectorTest(unittest.TestCase):

    def setUp(self):

        # Mocks
        self._toolkit = store_connector.plugins.toolkit
        store_connector.plugins.toolkit = MagicMock()
        store_connector.plugins.toolkit.NotAuthorized = self._toolkit.NotAuthorized

        self._model = store_connector.model
        store_connector.model = MagicMock()

        self._OAuth2Session = store_connector.OAuth2Session

        self.config = {
            'ckan.site_url': BASE_SITE_URL,
            'ckan.storepublisher.store_url': BASE_STORE_URL,
        }

        self.instance = store_connector.StoreConnector(self.config)

        # Save controller functions since it will be mocked in some tests
        self._make_request = self.instance._make_request
        self._rollback = self.instance._rollback
        self._get_product = self.instance._get_product
        self._get_offering = self.instance._get_offering
        self._create_offering = self.instance.create_offering

    def tearDown(self):
        store_connector.plugins.toolkit = self._toolkit
        store_connector.OAuth2Session = self._OAuth2Session
        store_connector.model = self._model

        # Restore controller functions
        self.instance._make_request = self._make_request
        self.instance._rollback = self._rollback
        self.instance.create_offering = self._create_offering
        self.instance._get_product = self._get_product
        self.instance._get_offering = self._get_offering

    @parameterized.expand([
        ('%s' % BASE_SITE_URL, '%s' % BASE_STORE_URL),
        ('%s/' % BASE_SITE_URL, '%s' % BASE_STORE_URL),
        ('%s' % BASE_SITE_URL, '%s/' % BASE_STORE_URL),
        ('%s/' % BASE_SITE_URL, '%s/' % BASE_STORE_URL)
    ])
    def test_init(self, site_url, store_url):

        config = {
            'ckan.site_url': site_url,
            'ckan.storepublisher.store_url': store_url,
        }

        instance = store_connector.StoreConnector(config)
        self.assertEquals(BASE_SITE_URL, instance.site_url)
        self.assertEquals(BASE_STORE_URL, instance.store_url)

    @parameterized.expand([
        (0,),
        (100,)
    ])
    def test_get_offering(self, price):
        user_nickname = 'smg'
        store_connector.plugins.toolkit.c.user = user_nickname
        offering_info = OFFERING_INFO_BASE.copy()
        offering_info['price'] = price
        resource = {'id': 'example_id', 'name': 'resource_name', 'version': '1.0', 'href': 'example.com'}
        offering = self.instance._get_offering(offering_info, resource)
        free_offering = []
        nonfree_offering = [{
            'name': 'One time fee',
            'description': 'One time fee of {} EUR'.format(
                offering_info['price']),
            'priceType': 'one time',
            'price': {
                'taxIncludedAmount': offering_info['price'],
                'dutyFreeAmount': str(price - (price * Decimal(0.2))),
                'taxRate': '20',
                'currencyCode': 'EUR'
            }
        }]
        expected_offering = {
            'name': offering_info['name'],
            'version': offering_info['version'],
            'description': offering_info['description'],
            'lifecycleStatus': 'Launched',
            'productSpecification': resource,
            'category': offering_info['categories']
        }
        if price == 0:
            expected_offering['productOfferingPrice'] = free_offering
        else:
            expected_offering['productOfferingPrice'] = nonfree_offering

        # Check the values
        self.assertEquals(offering, expected_offering)

    @parameterized.expand([
        ('get', {}, None, 200),
        ('post', {}, None, 200),
        ('put', {}, None, 200),
        ('delete', {}, None, 200),
        ('get', {}, None, 400),
        ('post', {}, None, 402),
        ('put', {}, None, 457),
        ('delete', {}, None, 499),
        ('get', {}, None, 500),
        ('post', {}, None, 502),
        ('put', {}, None, 557),
        ('delete', {}, None, 599),
        ('get', {'Content-Type': 'a'}, 'TEST DATA', 200),
        ('post', {'Content-Type': 'b'}, 'TEST DATA', 200),
        ('put', {'Content-Type': 'c'}, 'TEST DATA', 200),
        ('delete', {'Content-Type': 'd'}, 'TEST DATA', 200),
        ('get', {}, None, 401),
        ('post', {}, None, 401),
        ('put', {}, None, 401),
        ('delete', {}, None, 401),
        ('get', {'Content-Type': 'a'}, 'TEST DATA', 401),
        ('post', {'Content-Type': 'b'}, 'TEST DATA', 401),
        ('put', {'Content-Type': 'c'}, 'TEST DATA', 401),
        ('delete', {'Content-Type': 'd'}, 'TEST DATA', 401)
    ])
    def test_make_request(self, method, headers, data, response_status):
        url = 'http://example.com'
        ERROR_MSG = 'This is an example error!'

        # Set the environ
        usertoken = store_connector.plugins.toolkit.c.usertoken = {
            'token_type': 'bearer',
            'access_token': 'access_token',
            'refresh_token': 'refresh_token'
        }

        newtoken = {
            'token_type': 'bearer',
            'access_token': 'new_access_token',
            'refresh_token': 'new_refresh_token'
        }

        # Mock refresh_function
        def refresh_function_side_effect():
            store_connector.plugins.toolkit.c.usertoken = newtoken
        store_connector.plugins.toolkit.c.usertoken_refresh = MagicMock(side_effect=refresh_function_side_effect)

        expected_headers = headers.copy()
        expected_headers['Accept'] = 'application/json'

        # Set the response status
        first_response = MagicMock()
        first_response.status_code = response_status
        first_response.text = '{"message": %s, "result": False}' % ERROR_MSG
        second_response = MagicMock()
        second_response.status_code = 201

        request = MagicMock()
        store_connector.OAuth2Session = MagicMock(return_value=request)
        req_method = MagicMock(side_effect=[first_response, second_response])
        setattr(request, method, req_method)

        # Call the function
        if response_status > 399 and response_status < 600 and response_status != 401:
            with self.assertRaises(Exception) as e:
                self.instance._make_request(method, url, headers, data)
                self.assertEquals(ERROR_MSG, e.message)
                store_connector.OAuth2Session.assert_called_once_with(token=usertoken)
                req_method.assert_called_once_with(url, headers=expected_headers, json=data)
        else:
            result = self.instance._make_request(method, url, headers, data)

            # If the first request returns a 401, the request is retried with a new access_token...
            if response_status != 401:
                self.assertEquals(first_response, result)
                req_method.assert_called_once_with(url, headers=expected_headers, json=data)
                store_connector.OAuth2Session.assert_called_once_with(token=usertoken)
                req_method.assert_called_once_with(url, headers=expected_headers, json=data)
            else:
                # Check that the token has been refreshed
                store_connector.plugins.toolkit.c.usertoken_refresh.assert_called_once_with()

                # Check that both tokens has been used
                self.assertEquals(usertoken, store_connector.OAuth2Session.call_args_list[0][1]['token'])
                self.assertEquals(newtoken, store_connector.OAuth2Session.call_args_list[1][1]['token'])

                # Check URL
                self.assertEquals(url, req_method.call_args_list[0][0][0])
                self.assertEquals(url, req_method.call_args_list[1][0][0])

                # Check headers
                self.assertEquals(expected_headers, req_method.call_args_list[0][1]['headers'])
                self.assertEquals(expected_headers, req_method.call_args_list[1][1]['headers'])

                # Check Data
                self.assertEquals(data, req_method.call_args_list[0][1]['json'])
                self.assertEquals(data, req_method.call_args_list[1][1]['json'])

                # Check response
                self.assertEquals(second_response, result)

    def test_make_request_exception(self):
        method = 'get'
        url = 'http://example.com'
        headers = {
            'Content-Type': 'application/json'
        }
        data = 'This is an example test...?'

        request = MagicMock()
        store_connector.OAuth2Session = MagicMock(return_value=request)
        req_method = MagicMock(side_effect=ConnectionError)
        setattr(request, method, req_method)

        # Call the function
        with self.assertRaises(ConnectionError):
            self.instance._make_request(method, url, headers, data)

    @parameterized.expand([
        (True,
         '',
         'provider_name', 'testResource', '1.0', True),
        (True,
         '%s/#/offering?productSpecId=%s' % (BASE_STORE_URL, 'example_id'),
         'provider name',
         'testResource',
         '1.0', False),
        (False,
         '',
         'provider_name',
         'testResource',
         '1.0', False),
        (False,
         '%s/#/offering?productSpecId=%s' % (BASE_STORE_URL, 'id_example'),
         'provider name',
         'testResource',
         '1.0', False),
    ])
    def test_update_acquire_url(self, private, acquire_url, resource_provider, resource_name, resource_version, should_update):
        c = store_connector.plugins.toolkit.c
        c.user = resource_provider
        package_update = MagicMock()
        store_connector.plugins.toolkit.get_action = MagicMock(return_value=package_update)

        # Call the method
        dataset = {
            'private': private,
            'acquire_url': acquire_url
        }
        resource = {
            'name': resource_name,
            'version': resource_version,
            'provider': resource_provider,
            'id': 'example_id'
        }
        expected_dataset = dataset.copy()
#        new_name = resource['name'].replace(' ', '%20')
        expected_dataset['acquire_url'] = '%s/#/offering?productSpecId=%s' % (BASE_STORE_URL, resource['id'])

        # Update Acquire URL
        self.instance._update_acquire_url(dataset, resource)

        # Check that the acquire URL has been updated
        if should_update:
            context = {'model': store_connector.model, 'session': store_connector.model.Session,
                       'user': c.user or c.author, 'auth_user_obj': c.userobj,
                       }
            package_update.assert_called_once_with(context, expected_dataset)
        else:
            self.assertEquals(0, package_update.call_count)

    @parameterized.expand([
        ([], None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Active',
           'name': 'a',
           'href': 'www.imanexample.com',
           'version': 'example_id.0',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'name': 'Location',
                                          'value': '{}/dataset/{}'.format(
                                              BASE_SITE_URL, DATASET['id'])}]}],
         0),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Active',
           'name': 'a',
           'version': '1.0',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': '{}/dataset/{}'.format(
                                             BASE_STORE_URL, DATASET['id'])}]}],
         None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Active',
           'name': 'a',
           'version': '1.0',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': '{}/dataset/{}'.format(
                                             BASE_SITE_URL, DATASET['id'] + 'a')}]}],
         None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Obsolete',
           'name': 'a', 'version': '1.0',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': '{}/dataset/{}'.format(
                                             BASE_SITE_URL, DATASET['id'])}]}],
         None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Active',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'google.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Active',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'apple.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Obsolete',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': '{}/dataset/{}'.format(
                                             BASE_SITE_URL, DATASET['id'])}]}],
         None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Active',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'google.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Active',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'apple.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Active',
           'href': '',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': '{}/dataset/{}'.format(
                                             BASE_STORE_URL, DATASET['id'])}]}],
         None),
        ([{'id': 'example_id',
           'lifecycleStatus': 'Launched',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'google.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Launched',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'Location': 'apple.es'}]},
          {'id': 'example_id',
           'lifecycleStatus': 'Launched',
           'name': 'a',
           'version': '1.0',
           'href': 'www.imanexample.com',
           'productSpecCharacteristic': [{},
                                         {},
                                         {'name': 'Location',
                                          'value': '{}/dataset/{}'.format(
                                              BASE_SITE_URL, DATASET['id'])}]}], 2)

    ])
    def test_get_existing_product(self, current_user_resources, id_correct_resource):
        # Set up the test and its dependencies
        req = MagicMock()
        req.json = MagicMock(return_value=current_user_resources)
        r = [current_user_resources[id_correct_resource]] if id_correct_resource is not None else {}
        self.instance._get_existing_products = MagicMock(
            return_value=r)
        self.instance._update_acquire_url = MagicMock()

        # Get the expected result
        if id_correct_resource is not None:
            expected_resource = {
                'id': current_user_resources[id_correct_resource]['id'],
                'href': current_user_resources[id_correct_resource]['href'],
                'name': current_user_resources[id_correct_resource]['name'],
                'version': current_user_resources[id_correct_resource]['version']
            }
        else:
            expected_resource = None

        # Call the function and check the result
        dataset = DATASET.copy()
        self.assertEquals(expected_resource, self.instance._get_existing_product(dataset))

        # Update Acquire URL method is called (when the dataset is registered as resource in the Store)
        if expected_resource is not None:
            self.instance._update_acquire_url.assert_called_once_with(
                dataset, current_user_resources[id_correct_resource])

    @parameterized.expand([
        ([{'Location': 'EXAMPLEURL',
          'success': True}]),
        ([{'Location': 'EXAMPLEURL',
           'success': True}], 'customer'),
        ([{'Location': 'EXAMPLEURL',
          'success': False}])
    ])
    def test_create_product(self, location, role=''):
        self.instance._upload_image = MagicMock(return_value=location['Location'])
        store_connector.datetime = MagicMock()
        store_connector.datetime.now().isoformat.return_value = '2016-05-03T10:00:00Z'

        c = store_connector.plugins.toolkit.c
        c.user = 'provider name'
        value = 'CKAN API Dataset' if len(role) > 0 else 'CKAN Dataset'

        resource = {
            'productNumber': DATASET['id'],
            'name': DATASET['name'],
            'version': DATASET['version'],
            'description': DATASET['notes'],
            'isBundle': False,
            'brand': c.user,
            'lifecycleStatus': 'Launched',
            'validFor': {
                'startDateTime': '2016-05-03T10:00:00Z'
            },
            'relatedParty': [{
                'id': c.user,
                'href': ('{}/DSPartyManagement/api/partyManagement/v2/individual/{}'.format(BASE_STORE_URL, c.user)),
                'role': 'Owner'
            }],
            'attachment': [{
                'type': 'Picture',
                'url': 'EXAMPLEURL'
            }],
            'bundledProductSpecification': [],
            'productSpecificationRelationship': [],
            'serviceSpecification': [],
            'resourceSpecification': [],
            'productSpecCharacteristic': [{
                'configurable': False,
                'name': 'Media Type',
                'valueType': 'string',
                'productSpecCharacteristicValue': [{
                    "valueType": "string",
                    "default": True,
                    "value": DATASET['type'],
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": ""
                }]
            }, {
                'configurable': False,
                'name': 'Asset Type',
                'valueType': 'string',
                'productSpecCharacteristicValue': [{
                    "valueType": "string",
                    "default": True,
                    "value": value,
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": ""
                }]
            }, {
                'configurable': False,
                'name': 'Location',
                'valueType': 'string',
                'productSpecCharacteristicValue': [{
                    "valueType": "string",
                    "default": True,
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": "",
                    'value': '{}/dataset/{}'.format(BASE_SITE_URL, DATASET['id'])
                }]
            }, {'configurable': False,
                'name': 'License',
                'description': 'Use it and maybe buy me a beer',
                'valueType': 'string',
                'productSpecCharacteristicValue': [{
                    "valueType": "string",
                    "default": True,
                    "value": 'beerware',
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": ""
                }]}
            ]
        }

        expected_resource = {
            'id': '1',
            'href': 'http://example.com/DSProductCatalog/api/product/1',
            'name': resource['name'],
            'version': resource['version'],
            'productNumber': resource['productNumber'],
            'description': resource['description'],
            'isBundle': resource['isBundle'],
            'brand': resource['brand'],
            'lifecycleStatus': resource['lifecycleStatus'],
            'validFor': resource['validFor'],
            'relatedParty': resource['relatedParty'],
            'attachment': resource['attachment'],
            'bundledProductSpecification': resource['bundledProductSpecification'],
            'productSpecificationRelationship': resource['productSpecificationRelationship'],
            'serviceSpecification': resource['serviceSpecification'],
            'resourceSpecification': resource['resourceSpecification'],
            'productSpecCharacteristic': resource['productSpecCharacteristic']
        }
        dataset = DATASET.copy()

        expected_info = {
            'name': expected_resource['name'],
            'version': expected_resource['version'],
            'href': expected_resource['href'],
            'id': expected_resource['id']}

        # self.instance._get_product = MagicMock(return_value=resource)
        req = MagicMock()
        self.instance._update_acquire_url = MagicMock()

        # Call the function and check that we receive the correct result
        req.json.return_value = expected_resource
        dataset['type'] = 'testField'

        self.instance._make_request = MagicMock(return_value=req)

        content_info = {
            'version': '1.7',
            'image_base64': 'IMGB4/png/data',
            'license_title': 'beerware',
            'license_description': 'Use it and maybe buy me a beer',
            'role': role
        }

        self.assertEquals(expected_info, self.instance._create_product(dataset, content_info))

        # Assert that the methods has been called
        headers = {'Content-Type': 'application/json'}
        # self.instance._make_request.assert_called_once

        # Check the requests
        req_args = self.instance._make_request.call_args_list
        exp_call_args = [
            call('post', '{}/DSProductCatalog/api/catalogManagement/v2/productSpecification/'.format(BASE_STORE_URL), headers, resource)]

        if len(role) > 0:
            asset_headers = {
                'Accept': 'application/json',
                'Content-type': 'application/json'
            }

            asset = {
                'contentType': dataset['type'],
                'resourceType': 'CKAN API Dataset',
                'isPublic': False,
                'content': '{}/dataset/{}'.format(BASE_STORE_URL, dataset['id']),
                'metadata': {
                    'role': role
                }
            }

            exp_call_args.insert(0,
                call('post', '{}/charging/api/assetManagement/assets/uploadJob'.format(BASE_STORE_URL), asset_headers, asset))

        self.assertEquals(req_args, exp_call_args)

        # Check that the acquire URL has been updated
        self.instance._update_acquire_url.assert_called_once_with(dataset, expected_resource)

    @parameterized.expand([
        (True,),
        (False,)
    ])
    def test_rollback(self, offering_created):
        # Configure mocks
        self.instance._make_request = MagicMock()
        # Call the function
        self.instance._rollback(OFFERING_INFO_BASE, DATASET, offering_created)

        if offering_created:
            headers = {'Content-Type': 'application/json'}
            self.instance._make_request.assert_called_once_with(
                'patch',
                '{0}/DSProductCatalog/api/catalogManagement/v2/catalog/{1}/productOffering/{2}'.format(
                    BASE_STORE_URL,
                    OFFERING_INFO_BASE['catalog'],
                    DATASET['id']
                ),
                headers, {"lifecycleStatus": "Retired"})

    @parameterized.expand([
        (True, None),
        (False, None),
        (True, [None, Exception(EXCEPTION_MSG)], None, False),
        (False, [None, None, Exception(EXCEPTION_MSG)], None, False),
        (True, [None, None, Exception(EXCEPTION_MSG)], None, False),
        (False, [None, Exception(EXCEPTION_MSG)], None, False)
    ])
    def test_create_offering(self, resource_exists, make_req_side_effect, exception_text=None, offering_created=False):

        # Mock the plugin functions
        offering = {'offering': 1}
        resource = {'resource': 2}
        resource = {
            'href': 'href location',
            'id': 'resource_id',
            'name': 'resource name',
            'version': 'resource version'
        }

        expected_result = BASE_STORE_URL + '/DSProductCatalog/api/catalogManagement/v2/productOffering/:' + resource.get('id')
        
        self.instance._generate_product_info = MagicMock(return_value=resource)
        self.instance._get_offering = MagicMock(return_value=offering)
        self.instance._get_existing_product = MagicMock(return_value=resource if resource_exists else None)
        self.instance._create_product = MagicMock(return_value=resource)
        self.instance._rollback = MagicMock()
        r = MagicMock(side_effect=make_req_side_effect)
        self.instance._make_request = MagicMock(return_value=r)
        # Call the function
        try:
            r.url = expected_result

            result = self.instance.create_offering(DATASET, OFFERING_INFO_BASE)
            # name = OFFERING_INFO_BASE['name'].replace(' ', '%20')
            # Verify that exceptions were not expected
            self.assertIsNone(exception_text)

            self.assertEquals(expected_result, result)

            self.instance._get_existing_product.assert_called_once_with(DATASET)
            if not resource_exists:
                self.instance._create_product.assert_called_once_with(
                    DATASET, OFFERING_INFO_BASE)
            self.instance._get_offering.assert_called_once_with(OFFERING_INFO_BASE, resource)

            def check_make_request_calls(call, method, url, headers, data):
                self.assertEquals(method, call[0][0])
                self.assertEquals(url, call[0][1])
                self.assertEquals(headers, call[0][2])
                self.assertEquals(data, call[0][3])

            call_list = self.instance._make_request.call_args_list
            base_url = BASE_STORE_URL
            headers = {'Content-Type': 'application/json'}
            check_make_request_calls(
                call_list[0],
                'post',
                '%s/DSProductCatalog/api/catalogManagement/v2/catalog/%s/productOffering/' % (
                    base_url, OFFERING_INFO_BASE['catalog']),
                headers,
                offering)

        except store_connector.StoreException as e:
            self.instance._rollback.assert_called_once_with(OFFERING_INFO_BASE, offering_created)
            self.assertEquals(e.message, exception_text)

    @parameterized.expand([
        ([{
            'href': 'http://store.lab.fiware.org/DSProductCatalog/offering/1',
            'lifecycleStatus': 'Active'
        }, {
            'href': 'http://store.lab.fiware.org/DSProductCatalog/offering/2',
            'lifecycleStatus': 'Launched'
        }, {
            'href': 'http://store.lab.fiware.org/DSProductCatalog/offering/3',
            'lifecycleStatus': 'Retired'
        }], [{
            'id': '1',
            'lifecycleStatus': 'Launched',
            'href': 'http://store.lab.fiware.org/DSProductCatalog/product/1'
        }], [
            call('get', 'https://store.example.com:7458/DSProductCatalog/api/catalogManagement/v2/productOffering/?productSpecification.id=1'),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/offering/1', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Launched"}),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/offering/1', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Retired"}),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/offering/2', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Retired"}),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/product/1', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Retired"}),
        ]),
        ([], [{
            'id': '1',
            'lifecycleStatus': 'Active',
            'href': 'http://store.lab.fiware.org/DSProductCatalog/product/1'
        }], [
            call('get', 'https://store.example.com:7458/DSProductCatalog/api/catalogManagement/v2/productOffering/?productSpecification.id=1'),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/product/1', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Launched"}),
            call('patch', 'https://store.example.com:7458/DSProductCatalog/product/1', {'Content-Type': 'application/json'}, {"lifecycleStatus": "Retired"}),
        ])
    ])
    def test_delete_resources(self, offerings, product, calls):
        response = MagicMock()
        response.json.return_value = offerings

        self.instance._make_request = MagicMock(return_value=response)
        self.instance._get_existing_products = MagicMock(return_value=product)

        self.instance.delete_attached_resources('dataset')

        self.instance._get_existing_products.assert_called_once_with('dataset')
        self.assertEquals(calls, self.instance._make_request.call_args_list)

    def test_delete_resources_empty_product(self):
        self.instance._make_request = MagicMock()
        self.instance._get_existing_products = MagicMock(return_value=[])

        self.instance.delete_attached_resources('dataset')

        self.instance._get_existing_products.assert_called_once_with('dataset')
        self.assertEquals(0, self.instance._make_request.call_count)
