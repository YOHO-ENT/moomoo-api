#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 YOHO-ENT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from os.path import dirname, join
import sys

from setuptools import (
    find_packages,
    setup,
)

is_py2 = sys.version_info[0] == 2

with open(join(dirname(__file__), 'moomoo/VERSION.txt'), 'rb') as f:
    version = f.read().decode('ascii').strip()

with open("README.md", "r", encoding='utf-8') as fh:
    long_desc = fh.read()

install_requires = ["pandas",
                    "simplejson",
                    "protobuf>=3.5.1,==3.*",
                    "PyCryptodome",
                    ]

if is_py2:
    install_requires.append("selectors2")

setup(
    name='moomoo_api',
    version=version,
    description='Unofficial YOHO-ENT maintained fork of the moomoo quantitative trading API',
    long_description=long_desc,
    long_description_content_type="text/markdown",
    classifiers=[],
    keywords='Moomoo Stock Quant Trading API Unofficial Fork',
    author='YOHO-ENT',
    author_email='',
    url='https://github.com/YOHO-ENT/moomoo-api',
    project_urls={
        'Documentation': 'https://openapi.moomoo.com/moomoo-api-doc/',
        'Source': 'https://github.com/YOHO-ENT/moomoo-api',
        'Security': 'https://github.com/YOHO-ENT/moomoo-api/security/advisories',
    },
    license='Apache License 2.0',
    packages=find_packages(exclude=[]),
    package_data={
        'moomoo': ['VERSION.txt'],
        'moomoo.common.pb': ['*.proto'],
        'moomoo.examples.account_web': ['static/*.html', 'static/*.css', 'static/*.js'],
        'moomoo.quote': ['*.html'],
        'moomoo.tools': ['*.json', '*.template', '*.txt'],
    },
    exclude_package_data={
        'moomoo.common': ['conn_key*.txt', '*.pem', '*.key'],
        '': ['*.pem', '*.key'],
    },
    include_package_data=True,
    install_requires=install_requires
)
