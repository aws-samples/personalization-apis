# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

""" Amazon SageMaker resolver that invokes an inference endpoint for a SageMaker model """

import boto3
import json

from typing import Dict, List, Union
from http import HTTPStatus
from aws_lambda_powertools import Logger, Tracer
from personalization_error import SageMakerError

tracer = Tracer()
logger = Logger(child=True)

class SageMakerResolver():
    def __init__(
        self,
        sagemaker = boto3.client('sagemaker-runtime')
    ):
        self.sagemaker = sagemaker

    def _invoke_endpoint(self, endpoint_name: str, context: Dict, payload: Dict) -> Dict:
        if context:
            if isinstance(context, str):
                context = json.loads(context)
            payload['context'] = context

        response = self.sagemaker.invoke_endpoint(
            EndpointName = endpoint_name,
            ContentType = 'application/json',
            Accept = 'application/json',
            Body = payload
        )

        logger.debug(response)

        return response.get('Body')

    @tracer.capture_method
    def get_recommend_items(self, recommender_config: Dict, variation_config: Dict, user_id: str, num_results: int = 25, context: Union[str,Dict] = None) -> Dict:
        endpoint_name = variation_config.get('endpointName')
        if not endpoint_name:
            raise SageMakerError(HTTPStatus.NOT_FOUND, 'EndpointNameNotConfigured', 'Endpoint name has not been configured for this namespace and recommender name')

        logger.debug('Invoking SageMaker endpoint %s for recommend-items recommendation type', endpoint_name)

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

        return self._invoke_endpoint(endpoint_name, context, payload)

    @tracer.capture_method
    def get_related_items(self, recommender_config: Dict, variation_config: Dict, item_id: str, num_results: int = 25, user_id: str = None, context: Union[str,Dict] = None) -> Dict:
        endpoint_name = variation_config.get('endpointName')
        if not endpoint_name:
            raise SageMakerError(HTTPStatus.NOT_FOUND, 'EndpointNameNotConfigured', 'Endpoint name has not been configured for this namespace and recommender name')

        logger.debug('Invoking SageMaker endpoint %s for related-items recommendation type', endpoint_name)

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

        return self._invoke_endpoint(endpoint_name, context, payload)

    @tracer.capture_method
    def rerank_items(self, recommender_config: Dict, variation_config: Dict, user_id: str, input_list: List[str], context: Union[str,Dict] = None) -> Dict:
        endpoint_name = variation_config.get('endpointName')
        if not endpoint_name:
            raise SageMakerError(HTTPStatus.NOT_FOUND, 'EndpointNameNotConfigured', 'Endpoint name has not been configured for this namespace and recommender name')

        logger.debug('Invoking SageMaker endpoint %s for rerank-items recommendation type', endpoint_name)

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

        return self._invoke_endpoint(endpoint_name, context, payload)
