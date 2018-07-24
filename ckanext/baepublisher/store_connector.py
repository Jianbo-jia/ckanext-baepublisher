# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2018 Future Internet Consulting and Development Solutions S.L.

# This file is part of CKAN BAE Publisher Extension.

# CKAN BAE Publisher Extension is free software: you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# CKAN BAE Publisher Extension is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with CKAN BAE Publisher Extension.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from datetime import datetime
from decimal import Decimal
import logging
import os
import re
from unicodedata import normalize
from urlparse import urlparse

import ckan.model as model
import ckan.plugins as plugins
from requests_oauthlib import OAuth2Session

log = logging.getLogger(__name__)
WHITESPACE_RE = re.compile(r'\s+')
REPEATED_DOTS_RE = re.compile(r'\.{2,}')


class StoreException(Exception):
    pass


# http get https://biz-ecosystem.conwet.com/#/api/offering/resources/
class StoreConnector(object):

    def __init__(self, config):
        self.site_url = self._get_url(config, 'ckan.site_url')
        self.store_url = self._get_url(config, 'ckan.baepublisher.store_url')

        # Check that an store_url has been provided
        if not len(self.store_url):
            raise StoreException('A store URL for the baepublisher has not been provided')

        self.verify_https = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT', 'false').strip().lower() in ('', 'false', '0', 'off')

    def _get_url(self, config, config_property):
        env_name = config_property.upper().replace('.', '_')
        url = os.environ.get(env_name, '').strip()

        if url == '':
            url = config.get(config_property, '')

        url = url[:-1] if url.endswith('/') else url
        return url

    def validate_version(self, version):
        version = re.sub(WHITESPACE_RE, '', version) if version else ''
        if not version:
            version = '1.0'
        if version.endswith('.'):
            version += '0'
        version = re.sub(REPEATED_DOTS_RE, '.', version)
        if version.startswith('.'):
            version = "1" + version

        return version

    def _get_dataset_url(self, dataset):
        return '%s/dataset/%s' % (self.site_url, dataset['id'])

    def _upload_image(self, title, image):
        # Request to upload the attachment
        name = 'image_{}.png'.format(title)
        headers = {'Accept': 'application/json',
                   'Content-type': 'application/json'}
        body = {'contentType': 'image/png',
                'isPublic': True,
                'content': {
                    'name': name,
                    'data': image}
                }
        url = self._make_request(
            'post',
            '{}/charging/api/assetManagement/assets/uploadJob'.format(
                self.store_url),
            headers,
            body
        ).headers.get('Location')
        return url

    def _get_product(self, product, content_info):
        c = plugins.toolkit.c
        type_ = 'CKAN Dataset'

        if len(content_info['role']) > 0:
            type_ = 'CKAN API Dataset'
            # If there is a role defined it is needed to register the asset
            body = {
                'contentType': product['type'],
                'resourceType': 'CKAN API Dataset',
                'isPublic': False,
                'content': '{}/dataset/{}'.format(self.site_url, product['id']),
                'metadata': {
                    'role': content_info['role']
                }
            }
            headers = {
                'Accept': 'application/json',
                'Content-type': 'application/json'
            }

            self._make_request(
                'post',
                '{}/charging/api/assetManagement/assets/uploadJob'.format(self.store_url),
                headers,
                body
            )

        resource = {}
        resource['productNumber'] = product['id']
        resource['version'] = self.validate_version(product['version'])
        resource['name'] = product['title']
        resource['description'] = product['notes']
        resource['isBundle'] = False
        resource['brand'] = c.user  # Name of the author
        resource['lifecycleStatus'] = 'Launched'
        resource['validFor'] = {
            'startDateTime': datetime.now().isoformat()
        }
        resource['relatedParty'] = [{
            'id': c.user,
            'href': (
                '%s/DSPartyManagement/api/partyManagement/v2/individual/%s' % (
                    self.store_url,
                    c.user)
            ),
            'role': 'Owner'
        }]
        resource['attachment'] = [{
            'type': 'Picture',
            'url': self._upload_image(
                product['title'],
                content_info['image_base64']
            )
        }]
        resource['bundledProductSpecification'] = []
        resource['productSpecificationRelationship'] = []
        resource['serviceSpecification'] = []
        resource['resourceSpecification'] = []
        resource['productSpecCharacteristic'] = [{
            'configurable': False,
            'name': 'Media Type',
            'valueType': 'string',
            'productSpecCharacteristicValue': [{
                "valueType": "string",
                "default": True,
                "value": product['type'],
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
                "value": type_,
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
                "value": '{}/dataset/{}'.format(self.site_url, product['id']),
                "unitOfMeasure": "",
                "valueFrom": "",
                "valueTo": ""
            }]
        }]
        if content_info['license_title'] or content_info['license_description']:
            resource['productSpecCharacteristic'].append({
                'configurable': False,
                'name': 'License',
                'description': content_info['license_description'],
                'valueType': 'string',
                'productSpecCharacteristicValue': [{
                    "valueType": "string",
                    "default": True,
                    "value": content_info['license_title'],
                    "unitOfMeasure": "",
                    "valueFrom": "",
                    "valueTo": ""
                }]
            })

        return resource

    def _get_offering(self, offering_info, product):
        offering = {
            'name': offering_info['name'],
            'version': offering_info['version'],
            'description': offering_info['description'],
            'lifecycleStatus': 'Launched',
            'productSpecification': product,
            'category': offering_info['categories'],
        }
        # Set price
        if 'price' not in offering_info or offering_info['price'] == 0.0:
            offering['productOfferingPrice'] = []
        else:
            price = Decimal(offering_info['price'])
            offering['productOfferingPrice'] = [{
                'name': 'One time fee',
                'description': 'One time fee of {} EUR'.format(
                    offering_info['price']),
                'priceType': 'one time',
                'price': {
                    'taxIncludedAmount': offering_info['price'],
                    'dutyFreeAmount': str(
                        price - (
                            price * Decimal(0.2))),
                    'taxRate': '20',
                    'currencyCode': 'EUR'
                }
            }]

        return offering

    def _make_request(self, method, url, headers={}, data=None):
        def _get_headers_and_make_request(method, url, headers, data):
            # Include access token in the request
            usertoken = plugins.toolkit.c.usertoken
            final_headers = headers.copy()
            # Receive the content in JSON to parse the errors easily
            final_headers['Accept'] = 'application/json'
            # OAuth2Session
            oauth_request = OAuth2Session(token=usertoken)

            req_method = getattr(oauth_request, method)
            req = req_method(url, headers=final_headers, json=data, verify=self.verify_https)

            return req

        req = _get_headers_and_make_request(method, url, headers, data)

        # When a 401 status code is got,
        # we should refresh the token and retry the request.
        if req.status_code == 401:
            log.info(
                '%s(%s): returned 401. Token expired? Request will be retried with a refreshed token' % (method, url)
            )
            plugins.toolkit.c.usertoken_refresh()
            # Update the header 'Authorization'
            req = _get_headers_and_make_request(method, url, headers, data)

        log.info('%s(%s): %s %s' % (method, url, req.status_code, req.text))

        status_code_first_digit = req.status_code / 100
        invalid_first_digits = [4, 5]

        if status_code_first_digit in invalid_first_digits:
            result = req.json()
            error_msg = result['error']
            raise Exception(error_msg)

        return req

    def _update_acquire_url(self, dataset, resource):
        # Set needed variables
        c = plugins.toolkit.c
        tk = plugins.toolkit
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'auth_user_obj': c.userobj,
                   }

        if dataset['private']:
            resource_url = '%s/#/offering?productSpecId=%s' % (
                self.store_url,
                resource['id'])

            if dataset.get('acquire_url', '') != resource_url:
                dataset['acquire_url'] = resource_url
                tk.get_action('package_update')(context, dataset)
                log.info('Acquire URL updated correctly to %s' % resource_url)

    def _generate_product_info(self, product):
        return {
            'id': product.get('id'),
            'href': product.get('href'),
            'name': product.get('name'),
            'version': product.get('version')
        }

    def _get_product_url(self, characteristics):
        for x in characteristics:
            if x.get('name') == 'Location':
                return x['productSpecCharacteristicValue'][0].get('value')
        return ''

    def _get_existing_products(self, dataset):
        c = plugins.toolkit.c
        dataset_url = self._get_dataset_url(dataset)

        req = self._make_request(
            'get',
            '%s/DSProductCatalog/api/catalogManagement/v2/productSpecification/?relatedParty.id=%s' % (self.store_url, c.user)
        )
        products = req.json()

        def _valid_products_filter(product):
            return 'productSpecCharacteristic' in product and self._get_product_url(product['productSpecCharacteristic']) == dataset_url
        return filter(_valid_products_filter, products)

    def _get_existing_product(self, product):
        valid_products = self._get_existing_products(product)

        if len(valid_products) > 0:
            resource = valid_products.pop(0)
            self._update_acquire_url(product, resource)
            return self._generate_product_info(resource)
        else:
            return None

    def _create_product(self, product, content_info):
        # Create the resource
        resource = self._get_product(product, content_info)
        headers = {'Content-Type': 'application/json'}
        resp = self._make_request(
            'post',
            '%s/DSProductCatalog/api/catalogManagement/v2/productSpecification/' % self.store_url,
            headers,
            resource
        )

        resp_body = resp.json()
        self._update_acquire_url(product, resp_body)

        # Return the resource
        return self._generate_product_info(resp_body)

    def _retire_catalog_element(self, url):
        headers = {'Content-Type': 'application/json'}
        eff_url = self.store_url + urlparse(url).path
        self._make_request(
            'patch', eff_url, headers, {'lifecycleStatus': 'Retired'})

    def _launch_catalog_element(self, url):
        headers = {'Content-Type': 'application/json'}
        eff_url = self.store_url + urlparse(url).path
        self._make_request(
            'patch', eff_url, headers, {'lifecycleStatus': 'Launched'})

    def _rollback(self, offering_info, resource, offering_created):
        try:
            # Delete the offering only if it was created
            if offering_created:
                self._retire_catalog_element('{0}/DSProductCatalog/api/catalogManagement/v2/catalog/{1}/productOffering/{2}'.format(
                    self.store_url,
                    offering_info['catalog'],
                    resource['id'])
                )

        except Exception as e:
            log.warn('Rollback failed %s' % e)

    def _normalize_catalog_url(self, url):
        result_url = url
        if '(' in url:
            result_url = url.split('(')[0][:-1]

        return result_url

    def delete_attached_resources(self, dataset):
        """
        Method to delete all the attached store resources to a dataset. In particular, the method searches for a
        product specification containing the dataset, and the offerings that include the product. Then changes the
        status off these elements to Retired
        This method is triggered when the dataset is going to be deleted

        :param dataset:
        :type dataset: dict
        """

        try:
            products = self._get_existing_products(dataset)
        except Exception:
            # An exeption accessing the BAE should not be propagated to avoid exeption on non published datasets
            return

        if len(products) > 0:
            product = products[0]
            # Search the offerings that include the product
            response = self._make_request('get', '{0}/DSProductCatalog/api/catalogManagement/v2/productOffering/?productSpecification.id={1}'.format(
                self.store_url,
                product['id']))

            # Set the offerings as retired
            active_statuses = ['active', 'launched']
            for offering in response.json():
                if offering['lifecycleStatus'].lower() in active_statuses:

                    if offering['lifecycleStatus'].lower() == 'active':
                        self._launch_catalog_element(self._normalize_catalog_url(offering['href']))

                    self._retire_catalog_element(self._normalize_catalog_url(offering['href']))

            # Set the product as retired
            if product['lifecycleStatus'].lower() in active_statuses:
                if product['lifecycleStatus'].lower() == 'active':
                        self._launch_catalog_element(self._normalize_catalog_url(product['href']))

                self._retire_catalog_element(self._normalize_catalog_url(product['href']))

    def create_offering(self, dataset, offering_info):
        """
        Method to create an offering in the store that will contain the given dataset.
        The method will check if there is a resource in the Store that contains the
        dataset. If so, this resource will be used to create the offering. Otherwise
        a new resource will be created.
        Once that the resource is ready, a new offering will be created and the resource
        will be bounded.

        :param dataset: The dataset that will be include in the offering
        :type dataset: dict

        :param offering_info: A dict that contains additional info for the offering: name,
            description, license, offering version, price, image
        :type offering_info: dict

        :returns: The URL of the offering that contains the dataset
        :rtype: string

        :raises StoreException: When the store cannot be connected or when the Store
            returns some errors
        """

        log.debug('Creating Offering %s' % offering_info['name'])
        offering_created = False

        log.debug('Dataset: ')
        log.debug(dataset)

        # Make the request to the server
        headers = {'Content-Type': 'application/json'}
        try:
            # Get the resource. If it does not exist, it will be created
            resource = self._get_existing_product(dataset)
            if resource is None:
                resource = self._create_product(dataset, offering_info)

            offering = self._get_offering(offering_info, resource)
            # Create the offering
            resp = self._make_request(
                'post',
                '{0}/DSProductCatalog/api/catalogManagement/v2/catalog/{1}/productOffering/'.format(
                    self.store_url,
                    offering_info['catalog']),
                headers, offering
            )
            offering_created = True

            # Return offering URL
#            name = offering_info['name'].replace(' ', '%20')
            return resp.url

        except Exception as e:
            log.warn(e)
            self._rollback(offering_info, resource, offering_created)
            raise StoreException(e.message)
