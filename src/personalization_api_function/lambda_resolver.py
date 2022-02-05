# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

""" AWS Lambda resolver that invokes a Lambda function to retrieve recommendations """

import boto3
import json

from typing import Dict, List, Union
from http import HTTPStatus
from aws_lambda_powertools import Logger, Tracer
from personalization_error import LambdaError

tracer = Tracer()
logger = Logger(child=True)

class LambdaResolver():
    def __init__(
        self,
        lambda_client = boto3.client('lambda')
    ):
        self.lambda_client = lambda_client

    def _invoke_function(self, arn: str, context: Dict, payload: Dict) -> Dict:
        if context:
            if isinstance(context, str):
                context = json.loads(context)
            payload['context'] = context

        response = self.lambda_client.invoke(
            FunctionName = arn,
            InvocationType = 'RequestResponse',
            LogType = 'Tail', #'None'|'Tail',
            Payload = payload
        )

        logger.debug(response)

        status = response.get('StatusCode', 0)
        if status != HTTPStatus.OK:
            raise LambdaError(status, 'FunctionInvokeError', response.get('FunctionError'))

        return response.get('Payload')

    @tracer.capture_method
    def get_recommend_items(self, recommender_config: Dict, variation_config: Dict, user_id: str, num_results: int = 25, context: Union[str,Dict] = None) -> Dict:
        arn = variation_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking function %s for recommend-items recommendation type', arn)

        payload = {
            'version': '1.0',
            'action': 'recommend-items',
            'recommender': {
                'path': recommender_config['path']
            },
            'variation': variation_config,
            'userId': user_id,
            'numResults': num_results
        }

        return self._invoke_function(arn, context, payload)

    @tracer.capture_method
    def get_related_items(self, recommender_config: Dict, variation_config: Dict, item_id: str, num_results: int = 25, user_id: str = None, context: Union[str,Dict] = None) -> Dict:
        arn = variation_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking function %s for related-items recommendation type', arn)

        payload = {
            'version': '1.0',
            'action': 'related-items',
            'recommender': {
                'path': recommender_config['path']
            },
            'variation': variation_config,
            'itemId': item_id,
            'userId': (user_id if user_id else ''),
            'numResults': num_results
        }

        return self._invoke_function(arn, context, payload)

    @tracer.capture_method
    def rerank_items(self, recommender_config: Dict, variation_config: Dict, user_id: str, input_list: List[str], context: Union[str,Dict] = None) -> Dict:
        arn = variation_config.get('arn')
        if not arn:
            raise LambdaError(HTTPStatus.NOT_FOUND, 'FunctionArnNotConfigured', 'Function ARN has not been configured for this namespace and recommender name')

        logger.debug('Invoking function %s for rerank-items recommendation type', arn)

        payload = {
            'version': '1.0',
            'action': 'rerank-items',
            'recommender': {
                'path': recommender_config['path']
            },
            'variation': variation_config,
            'userId': user_id,
            'itemList': input_list
        }

        return self._invoke_function(arn, context, payload)
