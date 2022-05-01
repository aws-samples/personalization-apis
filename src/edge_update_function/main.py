# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import io
import json
import boto3
import logging
import zipfile

from urllib.request import urlopen
from crhelper import CfnResource

logger = logging.getLogger()
logger.setLevel(logging.INFO)

helper = CfnResource()
lambda_client = boto3.client('lambda')

def update_function(event):
    user_pool_id = event['ResourceProperties']['UserPoolId']
    cognito_region = event['ResourceProperties']['CognitoRegion']
    source_url = event['ResourceProperties'].get('SourceUrl')
    edge_function_arn = event['ResourceProperties']['EdgeFunctionArn']
    function_filename = event['ResourceProperties'].get('FunctionFilename', 'index.js')

    logger.info("Downloading well-known jwks.json from Cognito")
    jwks_url = f'https://cognito-idp.{cognito_region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json'
    with urlopen(jwks_url) as http_response:
        jwks = str(http_response.read())

    jwks = jwks.replace('b\'{', '{')
    jwks = jwks.replace('}\'', '}')
    logger.debug(json.dumps(jwks, indent = 2, default = str))

    if not source_url:
        logger.info('SourceUrl not specified so determining code location from Lambda for "Templated" alias')
        # The "Templated" alias is created when the edge auth function is deployed and represents the original
        # version of the function that is templated with replacement variables.
        response = lambda_client.get_function(
            FunctionName = f'{edge_function_arn}:Templated'
        )

        source_url = response['Code']['Location']

    logger.info("Building updated function zip archive")
    js = None
    with urlopen(source_url) as zip_resp:
        with zipfile.ZipFile(io.BytesIO(zip_resp.read())) as zin:
            with zipfile.ZipFile('/tmp/edge-code.zip', 'w') as zout:
                zout.comment = zin.comment
                for item in zin.infolist():
                    if item.filename == function_filename:
                        js = io.TextIOWrapper(io.BytesIO(zin.read(item.filename))).read()
                    else:
                        zout.writestr(item, zin.read(item.filename))

    if not js:
        raise Exception(f'Function code archive does not contain the file "{function_filename}"')

    js = js.replace('##JWKS##', jwks)
    js = js.replace('##USERPOOLID##', user_pool_id)
    js = js.replace('##COGNITOREGION##', cognito_region)

    logger.info('Writing updated js file %s to archive', function_filename)
    with zipfile.ZipFile('/tmp/edge-code.zip', mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(function_filename, js)

    # Load file into memory
    with open('/tmp/edge-code.zip', 'rb') as file_data:
        bytes_content = file_data.read()

    logger.info('Updating lambda function with updated code archive')
    response = lambda_client.update_function_code(
        FunctionName = edge_function_arn,
        ZipFile = bytes_content
    )

    logger.debug(response)

@helper.create
@helper.update
def create_or_update_resource(event, _):
    update_function(event)

def lambda_handler(event, context):
    logger.info(os.environ)
    logger.info(json.dumps(event, indent = 2, default = str))

    # If the event has a RequestType, we're being called by CFN as custom resource
    if event.get('RequestType'):
        logger.info('Function called from CloudFormation as custom resource')
        helper(event, context)
    else:
        logger.info('Function called outside of CloudFormation')
        # Call function directly (i.e. testing in Lambda console or called directly)
        update_function(event)
