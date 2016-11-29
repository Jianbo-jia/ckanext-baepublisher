# -*- coding: utf-8 -*-

# Copyright (c) 2014 CoNWeT Lab., Universidad Politécnica de Madrid

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
import ckanext.storepublisher.controllers.ui_controller as controller
import base64
import os
import unittest
import requests

from mock import patch
from mock import MagicMock
from nose_parameterized import parameterized


MISSING_ERROR = 'This field is required to publish the offering'

__dir__ = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(__dir__, '../assets/logo-ckan.png')

with open(filepath, 'rb') as f:
    LOGO_CKAN_B64 = base64.b64encode(f.read())


class UIControllerTest(unittest.TestCase):

    def setUp(self):

        controller.plugins.toolkit = MagicMock()
        self._toolkit = controller.plugins.toolkit
        controller.plugins.toolkit.NotAuthorized = self._toolkit.NotAuthorized

        self._request = controller.request
        controller.request = MagicMock()

        self._helpers = controller.helpers
        controller.helpers = MagicMock()

        self._base64 = controller.base64
        controller.base64 = MagicMock()

        self._StoreConnector = controller.StoreConnector
        self._store_connector_instance = MagicMock(store_url='localhost')
        controller.StoreConnector = MagicMock(return_value=self._store_connector_instance)

        # Create the plugin
        self.instanceController = controller.PublishControllerUI()

    def tearDown(self):
        controller.StoreConnector = self._StoreConnector

    class MockResponse:
        def __init__(self, json_data, status_code, dic):
            self.json_data = json_data
            self.status_code = status_code
            self.called_Raise = False
            self.dic = dic

        def __getitem__(self, item):
            return self.dic[item]

        def __contains__(self, key):
            return key in self.dic
            
        def json(self):
            return self.json_data
        
        def raise_for_status(self):
            self.called_Raise = True
            if self.status_code != 200:
                raise Exception
            else:
                return self.status_code

        def get(self, field, default=''):
            if field in self.dic:
                return self.dic[field]
            else:
                return default
            
        def getall(self, field):
            if 'categories' in self.dic:
                return self.dic['categories']
            else:
                return []
    
    @parameterized.expand([
        # Incorrect parameter
        ('offering', MockResponse({}, 403, []), {'lifecycleStatus': 'Launched'}),
        ('', MockResponse({}, 403, []), {'lifecycleStatus': 'Launched'}),
        # Valid entries
        ('category', MockResponse({'id': '1'}, 200, []), {'lifecycleStatus': 'Launched'}),
        ('catalog', MockResponse({'id': '1'}, 200, []),
         {'lifecycleStatus': 'Launched', 'relatedParty.id': 'eugenio'})
    ])
    def test_get_content(self, content, resp, filters):
        requests.get = MagicMock(return_value=resp)
        controller.plugins.toolkit.c.user = 'eugenio'
        controller.plugins.toolkit.c.errors = {}

        r = self.instanceController._get_content(content)
        
        requests.get.assert_called_once_with(
            '{0}/DSProductCatalog/api/catalogManagement/v2/{1}'.format(
                self._store_connector_instance.store_url, content),
            params=filters)

        if content == 'category' or content == 'catalog':
            self.assertEquals(r, {'id': '1'})
            self.assertEquals(controller.plugins.toolkit.c.errors, {})
        else:
            self.assertEquals(controller.plugins.toolkit.c.errors[content], ['{} couldnt be loaded'.format(content)])
            self.assertEquals(self.instanceController._get_content(content), {})
            self.assertTrue(resp.called_Raise)
        
    @parameterized.expand([
        # (False, False, {},),
        # # Test missing fields and wrong version
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id'})),
        (True, False, MockResponse({}, 200, {'version': '1.0',
                                             'pkg_id': 'package_id'})),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'pkg_id': 'package_id'})),
        (True, False, MockResponse({}, 200, {'pkg_id': 'package_id'})),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0.'})),
        # Test invalid prices
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'price': 'a'})),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'price': '5.a'})),
        # Test open offerings (open offerings must not contain private datasets)
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'open': ''})),
        (True, True, MockResponse({}, 200, {'name': 'a',
                                            'version': '1.0',
                                            'pkg_id': 'package_id',
                                            'open': ''})),
        # Public datastets cannot be offering in paid offerings
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'price': '1.0'})),
        (True, True, MockResponse({}, 200, {'name': 'a',
                                            'version': '1.0',
                                            'pkg_id': 'package_id',
                                            'price': '1.0'})),
        # 'image_upload' == '' happens when the user has not selected a file, so the default one must be used
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'image_upload': ''})),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'image_upload': MagicMock()})),
        # If 'update_acquire_url' is in the request content, the acquire_url should be updated
        # only when the offering has been published correctly
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'update_acquire_url': ''})),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id'}),
         controller.StoreException('Impossible to connect with the Store')),
        (True, False, MockResponse({}, 200, {'name': 'a',
                                             'version': '1.0',
                                             'pkg_id': 'package_id',
                                             'update_acquire_url': ''}),
         controller.StoreException('Impossible to connect with the Store')),
        # Requests with the fields not tested above
        # Test without tags
        (True, True, MockResponse({}, 200, {'name': 'a',
                                            'version': '1.0',
                                            'pkg_id': 'package_id',
                                            'description':
                                            '',
                                            'license_title': 'cc',
                                            'license_description': 'Desc',
                                            'price': '1.1',
                                            'categories': [],
                                            'catalogs': '51'})),
        # Request will all the fields
        (True, True, MockResponse({}, 200, {'name': 'A B C D',
                                            'version': '1.0',
                                            'pkg_id': 'package_id',
                                            'description': 'Example Description',
                                            'license_title': 'cc',
                                            'license_description': 'Desc',
                                            'categories': ['1', '5', '14'],
                                            'price': '1.1',
                                            'image_upload': MagicMock(),
                                            'update_acquire_url': '',
                                            'catalogs': '51'}))
    ])
    def test_publish(self, allowed, private, post_content, create_offering_res='http://some_url.com'):

        errors = {}
        current_package = {'categories': [{'name': 'Programacion'},
                                          {'name': 'java'}],
                           'private': private,
                           'acquire_url': 'http://example.com'}
        package_show = MagicMock(return_value=current_package)
        package_update = MagicMock()
        categories = [{'name': 'Programacion', 'isRoot': True, 'id': '1',
                       'parentId': '1',
                       'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/1:(1.0)'},
                      {'name': 'java', 'isRoot': False, 'id': '5',
                       'parentId': '1',
                       'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/5:(1.0)'},
                      {'name': 'haskell', 'isRoot': False, 'id': '14',
                       'parentId': '1',
                       'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/14:(1.0)'}]
        catalog = [{'id': '51',
                    'name': 'catalog1'}]

        self.instanceController._get_content = MagicMock(side_effect=[categories, catalog])

        def _get_action_side_effect(action):
            if action == 'package_show':
                return package_show
            else:
                return package_update

        tkString = 'Offering <a href="{0}" target="_blank">{1}</a> published correctly.'.format(create_offering_res, post_content.get('name', ''))
        
        controller.plugins.toolkit.get_action = MagicMock(side_effect=_get_action_side_effect)
        controller.plugins.toolkit.check_access = MagicMock(
            side_effect=self._toolkit.NotAuthorized if allowed is False else None)
        controller.plugins.toolkit._ = self._toolkit._
        controller.plugins.toolkit._.return_value = tkString
        controller.request.GET = []
        controller.request.POST = post_content
        self._store_connector_instance.create_offering = MagicMock(
            side_effect=[create_offering_res])
        self._store_connector_instance.validate_version = MagicMock(return_value='1.0')
        user = controller.plugins.toolkit.c.user
        pkg_id = post_content.get('pkg_id')
        # pkg_id = 'dhjus2-fdsjwdf-fq-dsjager'

        expected_context = {'model': controller.model,
                            'session': controller.model.Session,
                            'user': controller.plugins.toolkit.c.user,
                            'auth_user_obj': controller.plugins.toolkit.c.userobj}

        # Call the function
        self.instanceController.publish(pkg_id, post_content.dic)
        
        # Check that the check_access function has been called
        controller.plugins.toolkit.check_access.assert_called_once_with(
            'package_update', expected_context, {'id': pkg_id})

        # Check that the abort function is called properly
        if not allowed:
            controller.plugins.toolkit.abort.assert_called_once_with(
                401, 'User %s not authorized to publish %s' % (user, pkg_id))
        else:

            # Get the list of tags
            if post_content.get('categories') == [] or 'categories' not in post_content:
                tags = []
            else:
                tags = [
                    {'id': '14',
                     'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/14:(1.0)'},
                    {'id': '5',
                     'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/5:(1.0)'},
                    {'id': '1',
                     'href': 'http://localhost:8000/DSProductCatalog/api/catalogManagement/v2/category/1:(1.0)'}]

            # Get catalog
            catalog = post_content.get('catalogs')
    
            # Calculate errors
            if 'name' not in post_content:
                errors['Name'] = [MISSING_ERROR]

            if 'pkg_id' not in post_content:
                errors['Pkg_id'] = [MISSING_ERROR]

            price = post_content.get('price', '')
            if price != '':
                try:
                    real_price = float(post_content['price'])
                    if real_price > 0 and not private:
                        errors['Price'] = ['You cannot set a price to a dataset that is public since everyone can access it']
                except Exception:
                    errors['Price'] = ['"%s" is not a valid number' % price]
            else:
                real_price = 0.0

            if 'open' in post_content and private:
                errors['Open'] = ['Private Datasets cannot be offered as Open Offerings']

            if errors:
                # If the parameters are invalid, the function create_offering must not be called
                self.assertEquals(0, self._store_connector_instance.create_offering.call_count)
            else:

                # Default image should be used if the users has not uploaded a image
                image_field = post_content.get('image_upload', '')
                if image_field != '':
                    controller.base64.b64encode.assert_called_once_with(image_field.file.read.return_value)
                    expected_image = controller.base64.b64encode.return_value
                else:
                    self.assertEquals(0, controller.base64.b64encode.call_count)
                    expected_image = LOGO_CKAN_B64

                expected_data = {
                    'name': post_content['name'],
                    'pkg_id': post_content['pkg_id'],
                    'version': post_content['version'] if 'version' in post_content else '1.0',
                    'description': post_content.get('description', ''),
                    'license_title': post_content.get('license_title', ''),
                    'license_description': post_content.get('license_description', ''),
                    'is_open': 'open' in post_content,
                    'categories': tags,
                    'catalog': catalog,
                    'price': real_price,
                    'image_base64': expected_image
                }

                self._store_connector_instance.create_offering.assert_called_once_with(current_package, expected_data)

                if isinstance(create_offering_res, Exception):
                    errors['Store'] = [create_offering_res.message]
                    # The package should not be updated if the create_offering returns an error
                    # even if 'update_acquire_url' is present in the request content.
                    self.assertEquals(0, package_update.call_count)

                else:
                    controller.helpers.flash_success.assert_called_once_with(
                        tkString,
                        allow_html=True)
                    controller.plugins.toolkit._.assert_called_once_with(tkString)

        self.assertEquals(errors, controller.plugins.toolkit.c.errors)

        controller.plugins.toolkit.render('package/publish.html')
