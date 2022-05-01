# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
import json
import logging

from crhelper import CfnResource

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

helper = CfnResource()

function_arn = os.environ['ConfigValidatorFunctionArn']
apigw_host = os.environ['ApiGatewayHost']
cloudfront_host = os.environ['CloudFrontHost']

lambda_client = boto3.client('lambda')

fields_to_keep = [
  'FunctionName',
  'Role',
  'Handler',
  'Description',
  'Timeout',
  'MemorySize',
  'VpcConfig',
  'Environment',
  'Runtime',
  'DeadLetterConfig',
  'KMSKeyArn',
  'TracingConfig',
  'RevisionId',
  'Layers',
  'FileSystemConfigs',
  'ImageConfig',
  'EphemeralStorage'
]

def update_function():
    logger.info('Updating function configuration: %s', function_arn)
    response = lambda_client.get_function_configuration(FunctionName = function_arn)
    logger.debug(response)

    fields_to_drop = []
    for key in response.keys():
      if not key in fields_to_keep:
        fields_to_drop.append(key)

    for key in fields_to_drop:
        response.pop(key)

    if 'Layers' in response:
        # Convert from list of dictionaries to list of ARNs.
        arns = []
        for layer in response['Layers']:
            arns.append(layer['Arn'])

        response['Layers'] = arns

    env = response.setdefault('Environment', {})
    env_vars = env.setdefault('Variables', {})
    env_vars['ApiGatewayHost'] = apigw_host
    env_vars['CloudFrontHost'] = cloudfront_host

    logger.debug('Calling UpdateFunctionConfiguration with payload %s', response)

    response = lambda_client.update_function_configuration(**response)
    logger.debug(response)

@helper.create
@helper.update
def create_or_update_resource(event, _):
    update_function()

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
        update_function()
