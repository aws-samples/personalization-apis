# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

""" AWS Lambda response post processor """

import boto3
import json
import codecs

from typing import Dict
from http import HTTPStatus
from aws_lambda_powertools import Logger, Tracer
from personalization_error import LambdaError
from personalization_constants import ACTION_RECOMMEND_ITEMS, ACTION_RELATED_ITEMS, ACTION_RERANK_ITEMS

tracer = Tracer()
logger = Logger(child=True)

PAYLOAD_VERSION = '1.0'

class PostProcessor():
    def __init__(
        self,
        lambda_client = boto3.client('lambda')
    ):
        self.lambda_client = lambda_client

    def _invoke_function(self, arn: str, payload: Dict) -> Dict:
        response = self.lambda_client.invoke(
            FunctionName = arn,
            InvocationType = 'RequestResponse',
            LogType = 'Tail', #'None'|'Tail',
            Payload = codecs.encode(json.dumps(payload))
        )

        logger.debug(response)

        status = response.get('StatusCode', 0)
        if status != HTTPStatus.OK:
            raise LambdaError(status, 'FunctionInvokeError', response.get('FunctionError'))

        return json.load(response.get('Payload'))

    @tracer.capture_method
    def process_recommend_items(self, recommender_path: str, recommender_config: Dict, variation_config: Dict, user_id: str, response: Dict) -> Dict:
        post_process_config = recommender_config.get('responsePostProcessor')
        arn = post_process_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Post process function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking post-proces function %s for recommend-items recommendation type', arn)

        payload = {
            'version': PAYLOAD_VERSION,
            'action': ACTION_RECOMMEND_ITEMS,
            'recommender': {
                'path': recommender_path,
                'config': recommender_config
            },
            'variation': variation_config,
            'userId': user_id,
            'response': response
        }

        return self._invoke_function(arn, payload)

    @tracer.capture_method
    def process_related_items(self, recommender_path: str, recommender_config: Dict, variation_config: Dict, item_id: str, response: Dict) -> Dict:
        post_process_config = recommender_config.get('responsePostProcessor')
        arn = post_process_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Post process function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking function %s for related-items recommendation type', arn)

        payload = {
            'version': PAYLOAD_VERSION,
            'action': ACTION_RELATED_ITEMS,
            'recommender': {
                'path': recommender_path,
                'config': recommender_config
            },
            'variation': variation_config,
            'itemId': item_id,
            'response': response
        }

        return self._invoke_function(arn, payload)

    @tracer.capture_method
    def process_rerank_items(self, recommender_path: str, recommender_config: Dict, variation_config: Dict, user_id: str, response: Dict) -> Dict:
        post_process_config = recommender_config.get('responsePostProcessor')
        arn = post_process_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Post process function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking function %s for rerank-items recommendation type', arn)

        payload = {
            'version': PAYLOAD_VERSION,
            'action': ACTION_RERANK_ITEMS,
            'recommender': {
                'path': recommender_path,
                'config': recommender_config
            },
            'variation': variation_config,
            'userId': user_id,
            'response': response
        }

        return self._invoke_function(arn, payload)
