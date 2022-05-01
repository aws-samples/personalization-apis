# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import jsonschema
import os
import base64

from typing import List
from aws_lambda_powertools import Logger, Tracer
from openapi import OpenApiGenerator

tracer = Tracer()
logger = Logger()

staging_bucket = os.environ['StagingBucket']
openapi_output_key = 'openapi/openapi.json'

apigw_host = os.environ['ApiGatewayHost']
cloudfront_host = os.environ['CloudFrontHost']
api_auth_scheme = os.environ['AuthenticationScheme']

s3 = boto3.resource('s3')
event_bridge = boto3.client('events')

'''
Event structure:
{
    "applicationId": "The application Id of the configuration profile being validated",
    "configurationProfileId": "The configuration profile Id of the configuration profile being validated",
    "configurationVersion": "The configuration version of the configuration profile being validated",
    "content": "Base64EncodedByteString",
    "uri": "The uri of the configuration (e.g. 'hosted')"
}
'''

SCHEMA_FILE = 'personalization_apis_config_schema.json'

logger.info('Loading schema from %s', SCHEMA_FILE)
with open(SCHEMA_FILE) as file:
    schema = json.loads(file.read())

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, _):
    # Step 1: validate configuration against the JSON Schema
    personalization_config = json.loads(base64.b64decode(event['content']))

    try:
        jsonschema.validate(instance = personalization_config, schema = schema)
    except jsonschema.exceptions.ValidationError as e:
        # Log all details of the exception
        logger.exception(e)
        # Return a user-friendly error message
        raise Exception(e.message)

    # Step 2: do some logical validation against the configuration

    errors: List[str] = []
    # TODO
    if errors:
        raise ValueError('; '.join(errors))

    # Step 3: generate an updated OpenAPI spec file and save to the staging bucket.
    openapi_generator = OpenApiGenerator()
    openapi_spec = openapi_generator.generate(
        apis_config = personalization_config,
        apigw_host = apigw_host,
        cloudfront_host = cloudfront_host,
        auth_scheme = api_auth_scheme
    )

    openapi_uri = None
    if 'paths' in openapi_spec and len(openapi_spec['paths']) > 0:
        object = s3.Object(staging_bucket, openapi_output_key)
        result = object.put(Body=json.dumps(openapi_spec, indent = 4))
        logger.debug(result)
        openapi_uri = f's3://{staging_bucket}/{openapi_output_key}'

    # Step 4: post an event to EventBridge to trigger the resource synchronization step functions state machine.

    # Set the decoded config into event so that it's accessible as JSON in targets (i.e., step function state machine).
    event['content'] = personalization_config
    if openapi_uri:
        event['openApiSpecUri'] = openapi_uri

    region = os.environ['AWS_REGION']
    account_id = boto3.client('sts').get_caller_identity()['Account']
    resource = f'arn::appconfig:{region}:{account_id}:application/{event["applicationId"]}/configurationprofile/{event["configurationProfileId"]}'

    event_bridge.put_events(
        Entries=[
            {
                'Source': 'personalization.apis',
                'Resources': [ resource ],
                'DetailType': 'PersonalizationApisConfigurationChange',
                'Detail': json.dumps(event)
            }
        ]
    )
