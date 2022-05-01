# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
from pytest import fixture
from unittest.mock import MagicMock

from config_validator_function.openapi import OpenApiGenerator

@fixture
def sample_config():
    with open('samples/config_simple.json') as file:
        return json.loads(file.read())

def test_simple_noauth(sample_config):
    generator = OpenApiGenerator()
    generator._get_openapi_template_filename = MagicMock(return_value = 'src/config_validator_function/openapi_template.json')
    openapi = generator.generate(
        apis_config = sample_config,
        apigw_host = 'https://apigw-host.com',
        cloudfront_host = 'https://cloudfront-host.com',
        auth_scheme = 'NONE')

    assert len(openapi['servers']) == 2
    assert not 'security' in openapi

def test_simple_apikey(sample_config):
    generator = OpenApiGenerator()
    generator._get_openapi_template_filename = MagicMock(return_value = 'src/config_validator_function/openapi_template.json')
    openapi = generator.generate(
        apis_config = sample_config,
        apigw_host = 'https://apigw-host.com',
        cloudfront_host = 'https://cloudfront-host.com',
        auth_scheme = 'ApiKey')

    assert len(openapi['servers']) == 2
    assert len(openapi['security']) == 1
