# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
This custom resource function is responsible for updating the environment
variables for the ConfigValidatorFunction with the generated values for
the API Gateway host/URL and CloudFront host/URL. A custom resource had
to be used to workaround dependency recursion in the CloudFormation template.
"""

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

def update_function():
    """ Updates the configuration validator function's environment variables"""
    logger.info('Updating function configuration: %s', function_arn)

    logger.info('Getting current function configuration/environment variables')
    response = lambda_client.get_function_configuration(FunctionName = function_arn)
    logger.debug(response)

    env = response.get('Environment', {})
    env_vars = env.setdefault('Variables', {})
    env_vars['ApiGatewayHost'] = apigw_host
    env_vars['CloudFrontHost'] = cloudfront_host

    logger.info('Updating function environment variables')
    logger.debug(env)
    response = lambda_client.update_function_configuration(
        FunctionName = function_arn,
        Environment = env
    )
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
