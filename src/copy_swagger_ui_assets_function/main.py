# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
import logging
import requests

from typing import Dict
from crhelper import CfnResource

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

helper = CfnResource()

s3 = boto3.resource('s3')

assets = [
    {
        'source': 'https://raw.githubusercontent.com/aws-samples/personalization-apis/main/src/swagger-ui/index.html',
        'target': 'index.html'
    },
    {
        'source': 'https://raw.githubusercontent.com/aws-samples/personalization-apis/main/src/swagger-ui/favicon-32x32.png',
        'target': 'favicon-32x32.png'
    },
    {
        'source': 'https://raw.githubusercontent.com/aws-samples/personalization-apis/main/src/swagger-ui/favicon-16x16.png',
        'target': 'favicon-16x16.png'
    }
]

def copy_assets(event: Dict):
    target_bucket_name = event['ResourceProperties']['TargetBucket']
    logger.info('Copying Swagger UI assets to %s', target_bucket_name)

    bucket = s3.Bucket(target_bucket_name)

    for asset in assets:
        r = requests.get(asset['source'])
        if r.ok:
            logger.info('Saving %s to %s', asset['target'], target_bucket_name)
            content_type = r.headers['Content-Type']
            if asset['target'].endswith('.html'):
                content_type = 'text/html'
            response = bucket.put_object(Key = asset['target'], Body = r.content, ContentType = content_type)
            logger.debug(response)
        else:
            logger.error('Error retrieving asset %s: %s', asset['source'], r.status_code)

    logger.info('Successfully copied static assets to target bucket')

@helper.create
@helper.update
def create_or_update_resource(event, _):
    copy_assets(event)

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
        copy_assets(event)
