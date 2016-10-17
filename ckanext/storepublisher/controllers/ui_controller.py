# -*- coding: utf-8 -*-

# Copyright (c) 2014-2015 CoNWeT Lab., Universidad Politécnica de Madrid

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

import base64
import ckan.lib.base as base
import ckan.lib.helpers as helpers
import ckan.model as model
import ckan.plugins as plugins
import logging
import os
import requests
import re

from ckanext.storepublisher.store_connector import StoreConnector, StoreException
from ckan.common import request
from pylons import config

log = logging.getLogger(__name__)

__dir__ = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(__dir__, '../assets/logo-ckan.png')

with open(filepath, 'rb') as f:
    LOGO_CKAN_B64 = base64.b64encode(f.read())


class PublishControllerUI(base.BaseController):

    def __init__(self, name=None):
        self._store_connector = StoreConnector(config)
        self.store_url = self._store_connector.store_url

    def _sort_categories(self, categories):
        listOfTags = []
        catRelatives = {}
        tagSorted = sorted(categories, key=lambda x: int(x['id']))

        if not len(tagSorted):
            return listOfTags
        listOfTags.append(tagSorted[0])
        catRelatives[tagSorted[0]['id']] = {'href': tagSorted[0]['href'],
                                            'id': tagSorted[0]['id']}
        tagSorted.pop(0)

        # Im sorry for this double loop, ill try to optimize this
        for tag in tagSorted:
            if tag['isRoot']:
                listOfTags.append(tag)
                catRelatives[tag['id']] = {'href': tag['href'],
                                           'id': tag['id']}
                continue
            for item in listOfTags:
                if tag['parentId'] == item['id']:
                    listOfTags.insert(listOfTags.index(item) + 1, tag)
                    catRelatives[tag['id']] = {'href': tag['href'],
                                               'id': tag['id'],
                                               'parentId':  tag.get('parentId', '')}
                    break
        return listOfTags, catRelatives

    # This function is intended to make get requests to the api
    def _get_Content(self, content):
        c = plugins.toolkit.c
        filters = {
            'lifecycleStatus': 'Launched'
        }
        if content == 'catalog':
            filters['relatedParty.id'] = c.user
        response = requests.get(
            '{0}/DSProductCatalog/api/catalogManagement/v2/{1}'.format(
                self.store_url, content), params=filters)
        # Checking that the request finished successfully
        try:
            response.raise_for_status()
        except Exception:
            log.warn('{} couldnt be loaded'.format(content))
            c.errors['{}'.format(
                content)] = ['{} couldnt be loaded'.format(content)]
        return response.json()

    def publish(self, id, offering_info=None, errors=None):

        c = plugins.toolkit.c
        tk = plugins.toolkit
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'auth_user_obj': c.userobj,
                   }

        # Check that the user is able to update the dataset.
        # Otherwise, he/she won't be able to publish the offering
        try:
            tk.check_access('package_update', context, {'id': id})
        except tk.NotAuthorized:
            log.warn(
                'User %s not authorized to publish %s in the FIWARE Store' % (
                    c.user, id))
            tk.abort(
                401, tk._('User %s not authorized to publish %s') % (
                    c.user, id))

        # Get the dataset and set template variables
        # It's assumed that the user can view a package if he/she can update it

        # endpoint tags http://siteurl:porturl/catalogManagement/category

        dataset = tk.get_action('package_show')(context, {'id': id})

        c.pkg_dict = dataset
        c.errors = {}

        # Get tags in the expected format of the form select field
        def _getList(param):
            requiredFields = ['id', 'name']
            result = []
            for i in param:
                result.append({x: i[x] for x in requiredFields})
            for elem in result:
                elem['text'] = elem.pop('name')
                elem['value'] = elem.pop('id')
            return result

        def _validateVersion(version):
            ver = version
            if not ver:
                ver = '1.0'
            if re.search(r'\.$', ver) is not None:
                ver += '0'
            if re.search(r'\.{2,}', ver) is not None:
                ver = re.sub(r'\.{2,}', r'\.', ver)
            if re.search(r'^\.', ver) is not None:
                ver = "1" + ver
            return ver

        listOfTags, catRelatives = self._sort_categories(self._get_Content('category'))
        listOfCatalogs = self._get_Content('catalog')

        c.offering = {
            'categories': _getList(listOfTags),
            'catalogs': _getList(listOfCatalogs)
        }
        # when the data is provided
        if request.POST:
            offering_info = {}
            offering_info['pkg_id'] = request.POST.get('pkg_id', '')
            offering_info['name'] = request.POST.get('name', '')
            offering_info['description'] = request.POST.get('description', '')
            offering_info['license_title'] = request.POST.get(
                'license_title', '')
            offering_info['license_description'] = request.POST.get(
                'license_description', '')
            offering_info['version'] = _validateVersion(
                request.POST.get('version', ''))
            offering_info['is_open'] = 'open' in request.POST
            categories = request.POST.getall('categories')
            tempList = []

            # Insert all parents in the set until there are no more new parents
            for cat in categories:
                tempList.append(catRelatives[cat])
                tempCat = catRelatives[cat]
                while 'parentId' in tempCat and tempCat['parentId']:
                    tempList.append(catRelatives[tempCat['parentId']])
                    tempCat = catRelatives[tempCat['parentId']]

            for cat in tempList:
                if 'parentId' in cat:
                    del cat['parentId']

            offering_info['categories'] = tempList

            offering_info['catalog'] = request.POST.get('catalogs')
            # Read image
            # 'image_upload' == '' if the user has not set a file
            image_field = request.POST.get('image_upload', '')

            if image_field != '':
                offering_info['image_base64'] = base64.b64encode(
                    image_field.file.read())
            else:
                offering_info['image_base64'] = LOGO_CKAN_B64

            # Convert price into float (it's given as string)
            price = request.POST.get('price', '')
            if price == '':
                offering_info['price'] = 0.0
            else:
                try:
                    offering_info['price'] = float(price)
                except Exception:
                    offering_info['price'] = price
                    log.warn('%r is not a valid price' % price)
                    c.errors['Price'] = ['"%s" is not a valid number' % price]

            # Set offering. In this way, we recover the values introduced previosly
            # and the user does not have to introduce them again
            c.offering = offering_info

            # Check that all the required fields are provided
            required_fields = ['pkg_id', 'name', 'version']
            for field in required_fields:
                if not offering_info[field]:
                    log.warn('Field %r was not provided' % field)
                    c.errors[field.capitalize()] = ['This filed is required to publish the offering']

            # Private datasets cannot be offered as open offerings
            if dataset['private'] is True and offering_info['is_open']:
                log.warn(
                    'User tried to create an open offering for a private dataset')
                c.errors['Open'] = ['Private Datasets cannot be offered as Open Offerings']

            # Public datasets cannot be offered with price
            if ('price' in offering_info and dataset['private'] is False and
                    offering_info['price'] != 0.0 and 'Price' not in c.errors):
                log.warn(
                    'User tried to create a paid offering for a public dataset')
                c.errors['Price'] = ['You cannot set a price to a dataset that is public since everyone can access it']

            if not c.errors:
                try:
                    offering_url = self._store_connector.create_offering(
                        dataset, offering_info)
                    helpers.flash_success(
                        tk._(
                            'Offering <a href="%s" target="_blank">%s</a> published correctly.' % (
                                offering_url, offering_info['name'])),
                        allow_html=True)

                    # FIX: When a redirection is performed, the success message is not shown
                    # response.status_int = 302
                    # response.location = '/dataset/%s' % id
                except StoreException as e:
                    c.errors['Store'] = [e.message]

        return tk.render('package/publish.html')
