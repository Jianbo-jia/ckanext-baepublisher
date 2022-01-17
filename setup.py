# -*- coding: utf-8 -*-

# Copyright (c) 2014 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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

from setuptools import setup, find_packages
import os


version = '0.5'

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name='ckanext-baepublisher',
    version=version,
    description="CKAN extension allowing users to publish datasets in the FIWARE Business API Ecosystem as offerings in an easy way.",
    long_description=read('README.md'),
    long_description_content_type="text/markdown",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
    ],
    keywords='CKAN FIWARE BAE TM Forum Business API Ecosystem monetization',
    author='Aitor Magan, Francisco de la Vega',
    author_email='fdelavega@conwet.com',
    url='https://github.com/FIWARE-TMForum/ckanext-baepublisher',
    license='AGPLv3+',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    namespace_packages=['ckanext', 'ckanext.baepublisher'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'ckanext-oauth2>=0.4.0',
        'ckanext-privatedatasets>=0.4',
    ],
    tests_require=[
        'parameterized',
    ],
    entry_points='''
        [ckan.plugins]
        baepublisher=ckanext.baepublisher.plugin:StorePublisher
    ''',
)
