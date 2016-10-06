# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid

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

import ckan.model as model
import ckan.plugins as plugins
import json
import logging
import re
import requests

from unicodedata import normalize
from decimal import Decimal
from requests_oauthlib import OAuth2Session

log = logging.getLogger(__name__)


def slugify(text, delim=' '):
    """Generates an slightly worse ASCII-only slug."""
    _punct_re = re.compile(r'[\t !"#$%&\'()*/<=>?@\[\\\]`{|},.:]+')
    result = []
    for word in _punct_re.split(text):
        word = normalize('NFKD', word).encode('ascii', 'ignore')
        word = word.decode('utf-8')
        if word:
            result.append(word)

    return delim.join(result)


class StoreException(Exception):
    pass


# http get https://biz-ecosystem.conwet.com/#/api/offering/resources/ 
class StoreConnector(object):

    def __init__(self, config):
        self.site_url = self._get_url(config, 'ckan.site_url')
        self.store_url = self._get_url(config, 'ckan.storepublisher.store_url')

    def _get_url(self, config, config_property):
        url = config.get(config_property, '')
        url = url[:-1] if url.endswith('/') else url
        return url

    def _get_dataset_url(self, dataset):
        return '%s/dataset/%s' % (self.site_url, dataset['id'])

    def _upload_image(title, image):
        # Request to upload the attachment
        name = 'image_{}'.format(title)
        headers = {'Accept': 'application/json'}
        body = {
            'contentType': 'image/png', # Double check this fields.
            'isPublic': True,
            'content': {
                'name': name,
                'data': image
            }
        }
        url = _make_request('post', '{}/charging/api/assetManagement/assets/uploadJob'.format(self.store_url), headers, body).headers.get('Location')
        return url

    def _get_product(self, product, content_info):
        c = plugins.toolkit.c
        resource = {}
        resource['productNumber'] = product['id']
        resource['version'] = product['version']
        resource['name'] = product['title']
        resource['description'] = product['notes']
        resource['isBundle'] = False
        resource['brand'] = c.user  # Name of the author
        resource['lifecycleStatus'] = 'Launched'
        resource['validFor'] = {}
        resource['relatedParty'] = [{
            'id': c.user,
            'href': ('%s/DSPartyManagement/api/partyManagement/v2/individual/%s' % (self.store_url, c.user)),
            'role': 'Owner'
        }]

        resource['attachment'] = [{
            'type': 'Picture',
            'url': _upload_image(product['title'], content_info['image_base64'])
        }]
        resource['bundleProductSpecification'] = []
        resource['productSpecificationRelationShip'] = []
        resource['serviceSpecification'] = []
        resource['resourceSpecification'] = []
        resource['productSpecCharacteristic'] = [{
            'configurable': False,
            'name': 'Media Type',
            'value': product['type']
        },
        {
            'configurable': False,
            'name': 'Asset Type',
            'value': 'CKAN Dataset'
        },
        {
            'configurable': False,
            'name': 'Location',
            'value': '{}/dataset/{}'.format(self.site_url, product['id'])
        }]
        return resource

    def _get_offering(self, offering_info, product):
        offering = {}
        offering['name'] = offering_info['name']
        offering['version'] = offering_info['version']
        offering['lifecycleStatus'] = 'Launched'
        offering['productSpecification'] = {
            'id': product['id'],
            'href': product['href'],
            'version': product['version'],
            'name': product['name']
        }

        offering['category'] = offering_info['tags']
        # Set price
        if 'price' not in offering_info or offering_info['price'] == 0.0:
            offering['productOfferingPrice'] = []
        else:
            price = Decimal(offering_info['price'])
            offering['productOfferingPrice'] = [{
                'name': 'One time fee',
                'description': 'One time fee of {} EUR'.format(offering_info['price']),
                'priceType': 'one time',
                'price': {
                    'taxIncludedAmount': offering_info['price'],
                    'dutyFreeAmount': str(price - (price * Decimal(0.2))), # Price - 20%
                    'taxRate': '20',
                    'currencyCode': 'EUR'  
                }
            }]

        # Set license
        # This will be changed
        ######################################################################

        #if offering_info['license_title'] or offering_info['license_description']:
        #    offering['offering_info']['legal'] = {
        #        'title': offering_info['license_title'],
        #        'text': offering_info['license_description']
        #    }

        #######################################################################

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
            req = req_method(url, headers=final_headers, data=data)

            return req

        req = _get_headers_and_make_request(method, url, headers, data)

        # When a 401 status code is got, we should refresh the token and retry the request.
        if req.status_code == 401:
            log.info('%s(%s): returned 401. Token expired? Request will be retried with a refresehd token' % (method, url))
            plugins.toolkit.c.usertoken_refresh()
            # Update the header 'Authorization'
            req = _get_headers_and_make_request(method, url, headers, data)

        log.info('%s(%s): %s %s' % (method, url, req.status_code, req.text))

        status_code_first_digit = req.status_code / 100
        invalid_first_digits = [4, 5]

        if status_code_first_digit in invalid_first_digits:
            result = req.json()
            error_msg = result['message']
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
            user_nickname = c.user
            name = resource['name'].replace(' ', '%20')
            resource_url = '%s/search/resource/%s/%s/%s' % (self.store_url, user_nickname,
                                                            name, resource['version'])

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

    def _get_product_url(products):
        for x in products:
            if x.get('name') == 'Location':
                return x.get('value')
        return ''
    
    def _get_existing_products(self, dataset):
        dataset_url = self._get_dataset_url(dataset)
        req = self._make_request('get', '%s/DSProductCatalog/api/catalogManagement/v2//productSpecification/' % self.store_url)
        products = req.json()

        def _valid_products_filter(product):
            return product.get('lifecycleStatus') == 'Lanched' or product.get('lifecycleStatus') == 'Active' and _get_product_url(product['productSpecCharacteristic']) == dataset_url

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
        self._make_request('post', '%s/DSProductCatalog/api/catalogManagement/v2//productSpecification/' % self.store_url,
                           headers, json.dumps(resource))

        self._update_acquire_url(product, resource)

        # Return the resource
        return self._generate_product_info(resource)

    def _rollback(self, offering_info, offering_created):

        user_nickname = plugins.toolkit.c.user

        try:
            # Delete the offering only if it was created
            if offering_created:
                self._make_request('delete', '%s/api/offering/offerings/%s/%s/%s' % (self.store_url,
                                   user_nickname, offering_info['name'], offering_info['version']))
        except Exception as e:
            log.warn('Rollback failed %s' % e)

    def create_offering(self, dataset, offering_info):
        '''
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
        '''

        user_nickname = plugins.toolkit.c.user

        log.info('Creating Offering %s' % offering_info['name'])
        offering_created = False

        log.info('Dataset: ')
        log.info(dataset)
        log.info('Offering_info: ')
        log.info(offering_info)

        # Make the request to the server
        headers = {'Content-Type': 'application/json'}
        try:
            # Get the resource. If it does not exist, it will be created
            resource = self._get_existing_product(dataset)
            if resource is None:
                content_info = {'image_base64': offering_info['image_base64']}
                resource = self._create_product(dataset, content_info)

            offering = self._get_offering(offering_info, resource)
            offering_name = offering_info['name']
            offering_version = offering_info['version']

            # Create the offering
            resp = self._make_request('post', '%s/DSProductCatalog/api/catalogManagement/v2/productOffering/'.format(self.store_url),
                               headers, json.dumps(offering))
            offering_created = True

            # Return offering URL
            name = offering_info['name'].replace(' ', '%20')
            return _get_url(resp.headers.get('Location'))

        except Exception as e:
            log.warn(e)
            self._rollback(offering_info, offering_created)
            raise StoreException(e.message)
