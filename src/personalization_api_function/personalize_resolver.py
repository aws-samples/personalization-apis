# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

""" Amazon Personalize resolver that calls Personalize campaigns or recommenders """

import json
import boto3

from typing import Dict, List, Union
from http import HTTPStatus
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from personalization_error import PersonalizeError

tracer = Tracer()
logger = Logger(child=True)
metrics = Metrics()

class PersonalizeResolver():
    def __init__(
        self,
        personalize = boto3.client('personalize-runtime')
    ):
        self.personalize_runtime = personalize

    @tracer.capture_method
    def get_recommend_items(
            self,
            variation_config: Dict,
            arn: str,
            user_id: str,
            num_results: int = 25,
            filter_arn: str = None,
            filter_values: Union[str,Dict] = None,
            context: Union[str,Dict] = None,
            include_metadata: bool = True
        ) -> Dict:

        if not arn:
            raise PersonalizeError(HTTPStatus.NOT_FOUND, 'RecommenderArnNotConfigured', 'Personalize recommender/campaign ARN has not been configured for this namespace and recommender name')

        params = {
            'userId': user_id,
            'numResults': num_results
        }

        is_recommender = arn.split(':')[5].startswith('recommender/')
        if is_recommender:
            params['recommenderArn'] = arn
        else:
            params['campaignArn'] = arn

        if filter_arn:
            params['filterArn'] = filter_arn
            if filter_values:
                if isinstance(filter_values, str):
                    filter_values = json.loads(filter_values)
                params['filterValues'] = filter_values

        if context:
            if isinstance(context, str):
                context = json.loads(context)
            params['context'] = context

        metadata_config = variation_config.get('inferenceItemMetadata')
        if include_metadata and metadata_config and metadata_config.get('type') == 'personalize':
            item_columns = metadata_config.get('itemColumns')
            params['metadataColumns'] = {
                'ITEMS': item_columns
            }

        logger.debug('Calling personalize.get_recommendations() with arguments: %s', params)

        try:
            response = self.personalize_runtime.get_recommendations(**params)
            logger.debug(response)
            del response['ResponseMetadata']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                metrics.add_dimension(name="Arn", value=arn)
                metrics.add_metric(name="PersonalizeInferenceThrottledRequests", unit=MetricUnit.Count, value=1)
            raise PersonalizeError.from_client_error(e)

        return response

    @tracer.capture_method
    def get_related_items(
            self,
            variation_config: Dict,
            arn: str,
            item_id: str,
            num_results: int = 25,
            filter_arn: str = None,
            filter_values: Union[str,Dict] = None,
            user_id: str = None,
            context: Union[str,Dict] = None,
            include_metadata: bool = True
        ) -> Dict:

        if not arn:
            raise PersonalizeError(HTTPStatus.NOT_FOUND, 'RecommenderArnNotConfigured', 'Personalize recommender/campaign ARN has not been configured for this namespace and recommender name')

        params = {
            'itemId': item_id,
            'numResults': num_results
        }

        is_recommender = arn.split(':')[5].startswith('recommender/')
        if is_recommender:
            params['recommenderArn'] = arn
        else:
            params['campaignArn'] = arn

        if user_id:
            params['userId'] = user_id

        if filter_arn:
            params['filterArn'] = filter_arn
            if filter_values:
                if isinstance(filter_values, str):
                    filter_values = json.loads(filter_values)
                params['filterValues'] = filter_values

        if context:
            if isinstance(context, str):
                context = json.loads(context)
            params['context'] = context

        metadata_config = variation_config.get('inferenceItemMetadata')
        if include_metadata and metadata_config and metadata_config.get('type') == 'personalize':
            item_columns = metadata_config.get('itemColumns')
            params['metadataColumns'] = {
                'ITEMS': item_columns
            }

        logger.debug('Calling personalize.get_recommendations() with arguments: %s', params)

        try:
            response = self.personalize_runtime.get_recommendations(**params)
            logger.debug(response)
            del response['ResponseMetadata']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                metrics.add_dimension(name="Arn", value=arn)
                metrics.add_metric(name="PersonalizeInferenceThrottledRequests", unit=MetricUnit.Count, value=1)

            raise PersonalizeError.from_client_error(e)

        return response

    @tracer.capture_method
    def rerank_items(
            self,
            variation_config: Dict,
            arn: str,
            user_id: str,
            input_list: List[str],
            filter_arn: str = None,
            filter_values: Union[str,Dict] = None,
            context: Union[str,Dict] = None,
            include_metadata: bool = True
        ) -> Dict:

        if not arn:
            raise PersonalizeError(HTTPStatus.NOT_FOUND, 'RecommenderArnNotConfigured', 'Personalize recommender/campaign ARN has not been configured for this namespace and recommender name')

        params = {
            'userId': user_id,
            'inputList': input_list
        }

        is_recommender = arn.split(':')[5].startswith('recommender/')
        if is_recommender:
            params['recommenderArn'] = arn
        else:
            params['campaignArn'] = arn

        if filter_arn:
            params['filterArn'] = filter_arn
            if filter_values:
                if isinstance(filter_values, str):
                    filter_values = json.loads(filter_values)
                params['filterValues'] = filter_values

        if context:
            if isinstance(context, str):
                context = json.loads(context)
            params['context'] = context

        metadata_config = variation_config.get('inferenceItemMetadata')
        if include_metadata and metadata_config and metadata_config.get('type') == 'personalize':
            item_columns = metadata_config.get('itemColumns')
            params['metadataColumns'] = {
                'ITEMS': item_columns
            }

        logger.debug('Calling personalize.get_personalized_ranking() with arguments: %s', params)

        try:
            response = self.personalize_runtime.get_personalized_ranking(**params)
            logger.debug(response)
            del response['ResponseMetadata']
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                metrics.add_dimension(name="Arn", value=arn)
                metrics.add_metric(name="PersonalizeInferenceThrottledRequests", unit=MetricUnit.Count, value=1)
            raise PersonalizeError.from_client_error(e)

        return response
