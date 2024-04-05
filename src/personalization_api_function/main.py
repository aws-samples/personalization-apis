# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Lambda function that provides real-time personalization API functionality between public endpoints and recommenders

This file contains the logic that performs and delegates the core processing for real-time
recommendation requests as well as receiving events/interactions.
"""

import os
import time
import json
import traceback
import urllib.request
import botocore
import urllib
import zlib

from typing import Dict, List, Tuple, Union
from http import HTTPStatus
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler.api_gateway import ApiGatewayResolver, ProxyEventType, CORSConfig, Response
from personalization_config import PersonalizationConfig
from personalization_constants import ACTION_RECOMMEND_ITEMS, ACTION_RELATED_ITEMS, ACTION_RERANK_ITEMS
from response_decorator import ResponseDecorator
from personalize_resolver import PersonalizeResolver
from lambda_resolver import LambdaResolver
from sagemaker_resolver import SageMakerResolver
from response_post_process import PostProcessor
from personalization_error import ConfigError, PersonalizationError, ValidationError, JSONDecodeValidationError
from evidently import evidently_evaluate_feature, process_conversions
from event_targets import process_targets
from auto_values import resolve_auto_values
from background_tasks import BackgroundTasks
from util import CompatEncoder

PERSONALIZE_GET_RECS_MAX_NUM_RESULTS = 500

tracer = Tracer()
logger = Logger()
metrics = Metrics()

cors_config = CORSConfig(max_age=500)
api_type = os.environ.get('ApiType', 'REST')
compress_responses = False  # Local compression
if api_type == 'HTTP':
    app = ApiGatewayResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2, cors=cors_config)
    compress_responses = True
elif api_type == 'ALB':
    app = ApiGatewayResolver(proxy_type=ProxyEventType.ALBEvent, cors=cors_config)
    compress_responses = True
else:
    app = ApiGatewayResolver(cors=cors_config)
    # Compression is off-loaded to API Gateway for REST API

config = PersonalizationConfig.get_instance()
region = os.environ['AWS_REGION']
personalize_resolver = PersonalizeResolver()
lambda_resolver = LambdaResolver()
sagemaker_resolver = SageMakerResolver()
post_processor = PostProcessor()

with BackgroundTasks() as background:
    logger.info('Cold start prepare datastores')
    ResponseDecorator.prepare_datastores(config.get_config(), background)

def generate_etag(max_age: int) -> str:
    """ Creates and returns a simple ETag header value that combines a checksum of the request with the current time and max_age.

    The ETag response header value is passed in subsequent requests in the If-None-Match header to check if the cached
    resource is still valid. The logic for determining of an ETag value is still valid for caching is implemented in
    the is_resource_not_modified() function.
    """
    path = app.current_event.path
    if 'rawQueryString' in app.current_event.raw_event:
        query_string = app.current_event.get('rawQueryString', '')
    else:
        query_string_params = app.current_event.query_string_parameters
        if query_string_params:
            query_string = urllib.parse.urlencode(query_string_params)
        else:
            query_string = ''
    checksum = zlib.adler32(f'{path}?{query_string}'.encode())
    millis = round(time.time() * 1000)
    return f'{checksum}-{millis}-{max_age}'

def is_resource_not_modified() -> bool:
    """ Determines whether the resource for the current request has been modified by checking the If-None-Match request header """
    # For the ETag/If-None-Match logic to yeild the most benefit, we need to implement a more intelligent
    # algorithm here. For example, if campaign/recommender hasn't been updated or no new events have been received
    # for the user, then we can return a 304 more often and more confidently.
    if_none_match = app.current_event.get_header_value(name = 'If-None-Match', default_value='') or None
    if not if_none_match:
        return False

    etag_elements = if_none_match.split('-')
    if len(etag_elements) < 2:
        return False
    expires = int(etag_elements[-2]) + (int(etag_elements[-1]) * 1000)
    return expires > (time.time() * 1000)

def set_cache_headers(config: Dict, headers: Dict, user_id: str, user_is_synthetic: bool = False):
    """ Sets the caching related response headers based on the current configuration and request state.

    The cacheControl directives in the configuration file control how caching is done for requests
    that include a user, include a synthetic user, and do not include a user. The idea is that you
    would cache responses more aggressively that did not include a user or for synthetic users and
    less aggressively for specific users.
    """
    if not config.get('cacheControl'):
        return

    control_type = 'noUserSpecified'
    if user_id:
        control_type = 'syntheticUserSpecified' if user_is_synthetic else 'userSpecified'

    cache_control = config['cacheControl'].get(control_type)

    if cache_control:
        max_age = cache_control.get('maxAge')
        directives = cache_control.get('directives')
        if max_age:
            headers['ETag'] = generate_etag(max_age)
            if not directives:
                headers['Cache-Control'] = f'max-age={max_age}'
            elif 'max-age=' not in directives:
                headers['Cache-Control'] = f'{directives},max-age={max_age}'
        elif directives:
            headers['Cache-Control'] = directives

@tracer.capture_method
def evaluate_variations(rec_config: Dict, user_id: str, background: BackgroundTasks) -> Tuple:
    """ Evaluates the variations configured for a recommender to determine appropriate one to use for the request.

    If there are multiple variations configured for the recommender and AWS CloudWatch Evidently is configured as
    the evaluator, Evidently will determine the variation to use for the user. Otherwise, the first variation is used.
    """
    variations = rec_config.get('variations')
    if not variations or len(variations) == 0:
        raise ConfigError(HTTPStatus.NOT_FOUND, 'NoVariationsConfigured', 'Recommender does not have any variations configured')

    experiments = rec_config.get('experiments')
    if not experiments or len(variations) == 1 or not user_id:
        return config.inherit_config(rec_config, next(iter(variations.items()))[1]), None

    feature = str(app.current_event.get_query_string_value(name="feature", default_value="")) or None
    if feature:
        experiment = experiments.get(feature)
        if not experiment:
            raise ValidationError('InvalidExperimentFeature', f'Experiment for feature {feature} is referencing an experiment that is not in configuration')
    else:
        feature, experiment = next(iter(experiments.items()))

    if experiment.get('method') == 'evidently':
        variation, experiment = evidently_evaluate_feature(feature, experiment, variations, user_id, background)
        variation = config.inherit_config(rec_config, variation)
        return variation, experiment
    else:
        raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'UnsupportedEvaluationMethod', 'Variation evaluation method is not configured/supported')

def resolve_context(variation_config: Dict) -> Union[str, Dict]:
    """ Resolves automated context for the caller as configured for the recommender.

    Automated context can be used to derive contextual field values based on intrinsic data in the
    request. For example, device type and location information of the user can be derived from
    CloudFront headers and time-based constructs such weekday, weekend, time of day, and seasonality
    can be derived from the time of the request and the user's time zone.
    """
    context = str(app.current_event.get_query_string_value(name="context", default_value="")) or None

    auto_context_config = variation_config.get('autoContext')
    if auto_context_config:
        auto_context = resolve_auto_values(auto_context_config, app.current_event.headers)
        if auto_context:
            if not context:
                context = {}
            elif type(context) == str:
                try:
                    context = json.loads(context)
                except json.decoder.JSONDecodeError:
                    raise ValidationError('InvalidContextParameter', 'Parameter "context" is not valid JSON')

            for field, resolved in auto_context.items():
                if not field in context:
                    context[field] = str(resolved['values'][0])

    return context

def resolve_filter_parameters(variation_config: Dict, user_id: str) -> Tuple:
    """ Resolves automated filter values for the caller as configured in the recommender.

    Automated filter values can be used to derive dynamic filter variable values based on intrinsic data
    in the request. For example, device type and location information of the user can be derived from
    CloudFront headers and time-based constructs such weekday, weekend, time of day, and seasonality
    can be derived from the time of the request and the user's time zone.
    """
    filter_name = str(app.current_event.get_query_string_value(name="filter", default_value="")) or None
    filter_values = str(app.current_event.get_query_string_value(name="filterValues", default_value="")) or None

    filter_arn = None
    if filter_name:
        filter_arn = f'arn:aws:personalize:{region}:{app.current_event.request_context.account_id}:filter/{filter_name}'
    elif variation_config.get('filters'):
        for filter in variation_config['filters']:
            condition = filter.get('condition')
            if not condition or (user_id and condition == 'user-required'):
                filter_arn = filter.get('arn')
                break
    else:
        filter_values = None

    if filter_arn and variation_config.get('filter') and variation_config['filter'].get('autoDynamicFilterValues'):
        filter_auto_values = resolve_auto_values(variation_config['filter']['autoDynamicFilterValues'], app.current_event.headers)
        if filter_auto_values:
            if not filter_values:
                filter_values = {}
            elif type(filter_values) == str:
                try:
                    filter_values = json.loads(filter_values)
                except json.decoder.JSONDecodeError:
                    raise ValidationError('InvalidFilterParameter', 'Parameter "filterValues" is not valid JSON')

            for parameter, resolved in filter_auto_values.items():
                if not parameter in filter_values:
                    if resolved.get('type') == 'string':
                        filter_values[parameter] = ','.join(f'\\"{val}\\"' for val in resolved['values'])
                    else:
                        filter_values[parameter] = str(resolved['values'][0])

    return filter_arn, filter_values

def try_decorate_items() -> bool:
    """ Returns whether the caller wants to have returned items decorated with metadata (default is to decorate)"""
    return app.current_event.get_query_string_value(name='decorateItems', default_value='1').lower() in ['1','yes','true']

@tracer.capture_method
def post_decorate_items(namespace: str, response: Dict):
    """ Decorates items in the response with item metadata from the recommender or that is stored in a low-latency datastore
    """
    if try_decorate_items():
        decorator = ResponseDecorator.get_instance(namespace, config)
        if decorator:
            decorator.decorate(response)

@app.get("/recommend-items/<namespace>/<recommender>/<user_id>", cors=True, compress=compress_responses)
@tracer.capture_method(capture_response=False)
def get_recommend_items(namespace: str, recommender: str, user_id: str) -> Response:
    """ API entry point for getting recommended items for a given user """
    tracer.put_annotation(key = 'EntryPoint', value = 'recommend-items')
    tracer.put_annotation(key = 'Namespace', value = namespace)
    tracer.put_annotation(key = 'Recommender', value = recommender)

    if is_resource_not_modified():
        return Response(status_code=HTTPStatus.NOT_MODIFIED,
                        content_type="text/plain",
                        body='Not mofified'
        )

    with BackgroundTasks() as background:
        logger.debug('Conditionally refreshing datastores in the backgound')
        ResponseDecorator.prepare_datastores(config.get_config(), background)

        rec_config = config.get_recommender_config(namespace, recommender, ACTION_RECOMMEND_ITEMS)
        if not rec_config:
            raise ConfigError(HTTPStatus.NOT_FOUND, 'RecommenderNotConfigured', 'Recommender not configured for this namespace and recommender path')

        variation, experiment = evaluate_variations(rec_config, user_id, background)

        inference_num_results = num_results = int(app.current_event.get_query_string_value(name="numResults", default_value="25"))
        context = resolve_context(variation)

        post_process_config = rec_config.get('responsePostProcessor')
        if post_process_config and post_process_config.get('lookAheadMultiplier'):
            inference_num_results *= post_process_config['lookAheadMultiplier']
            if post_process_config.get('lookAheadMaximumValue'):
                inference_num_results = min(inference_num_results, post_process_config['lookAheadMaximumValue'])

        if variation.get('type') in ['personalize-campaign', 'personalize-recommender']:
            arn = variation.get('arn')
            filter_arn, filter_values = resolve_filter_parameters(variation, user_id)
            inference_num_results = min(inference_num_results, PERSONALIZE_GET_RECS_MAX_NUM_RESULTS)

            response = personalize_resolver.get_recommend_items(
                    variation_config = variation,
                    arn = arn,
                    user_id = user_id,
                    num_results = inference_num_results,
                    filter_arn = filter_arn,
                    filter_values = filter_values,
                    context = context,
                    include_metadata = try_decorate_items()
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'sagemaker':
            response = sagemaker_resolver.get_recommend_items(
                    recommender,
                    rec_config,
                    variation,
                    user_id = user_id,
                    num_results = inference_num_results,
                    context = context
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'lambda':
            response = lambda_resolver.get_recommend_items(
                    recommender,
                    rec_config,
                    variation,
                    user_id = user_id,
                    num_results = inference_num_results,
                    context = context
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'http':
            url = variation['url'].format(**app.current_event.query_string_parameters)
            response = json.loads(urllib.request.urlopen(url).read())

        if response and experiment:
            response['matchedExperiment'] = experiment

        if post_process_config:
            response = post_processor.process_recommend_items(recommender, rec_config, variation, user_id, response)

        if len(response.get('itemList')) > num_results:
            response['itemList'] = response['itemList'][:num_results]

        headers = {}
        if config.get_version():
            headers['X-Personalization-Config-Version'] = config.get_version()

        synthetic_user = app.current_event.get_query_string_value(name="syntheticUser", default_value="0").lower() in ['1','yes','true']
        set_cache_headers(variation, headers, user_id, synthetic_user)

        return Response(status_code=HTTPStatus.OK,
                        content_type="application/json",
                        body=json.dumps(response, cls=CompatEncoder),
                        headers=headers
        )

@app.get("/related-items/<namespace>/<recommender>/<item_id>", cors=True, compress=compress_responses)
@tracer.capture_method(capture_response=False)
def get_related_items(namespace: str, recommender: str, item_id: str) -> Response:
    """ API entry point for getting related items for a given item """
    tracer.put_annotation(key = 'EntryPoint', value = 'related-items')
    tracer.put_annotation(key = 'Namespace', value = namespace)
    tracer.put_annotation(key = 'Recommender', value = recommender)

    if is_resource_not_modified():
        return Response(status_code=HTTPStatus.NOT_MODIFIED,
                        content_type="text/plain",
                        body='Not mofified'
        )

    with BackgroundTasks() as background:
        logger.debug('Conditionally refreshing datastores in the backgound')
        ResponseDecorator.prepare_datastores(config.get_config(), background)

        rec_config = config.get_recommender_config(namespace, recommender, ACTION_RELATED_ITEMS)
        if not rec_config:
            raise ConfigError(HTTPStatus.NOT_FOUND, 'RecommenderNotConfigured', 'Recommender not configured for this namespace and recommender path')

        user_id = str(app.current_event.get_query_string_value(name="userId", default_value="")) or None

        variation, experiment = evaluate_variations(rec_config, user_id, background)

        inference_num_results = num_results = int(app.current_event.get_query_string_value(name="numResults", default_value="25"))
        context = resolve_context(variation)

        post_process_config = rec_config.get('responsePostProcessor')
        if post_process_config and post_process_config.get('lookAheadMultiplier'):
            inference_num_results *= post_process_config['lookAheadMultiplier']
            if post_process_config.get('lookAheadMaximumValue'):
                inference_num_results = min(inference_num_results, post_process_config['lookAheadMaximumValue'])

        if variation.get('type') in ['personalize-campaign', 'personalize-recommender']:
            arn = variation.get('arn')
            filter_arn, filter_values = resolve_filter_parameters(variation, user_id)
            inference_num_results = min(inference_num_results, PERSONALIZE_GET_RECS_MAX_NUM_RESULTS)

            response =  personalize_resolver.get_related_items(
                    variation_config = variation,
                    arn = arn,
                    item_id = item_id,
                    num_results = inference_num_results,
                    filter_arn = filter_arn,
                    filter_values = filter_values,
                    user_id = user_id,
                    context = context,
                    include_metadata = try_decorate_items()
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'sagemaker':
            response = sagemaker_resolver.get_related_items(
                    recommender,
                    rec_config,
                    variation,
                    item_id = item_id,
                    num_results = inference_num_results,
                    user_id = user_id,
                    context = context
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'lambda':
            response = lambda_resolver.get_related_items(
                    recommender,
                    rec_config,
                    variation,
                    item_id = item_id,
                    num_results = inference_num_results,
                    user_id = user_id,
                    context = context
            )

            post_decorate_items(namespace, response)
        elif variation.get('type') == 'http':
            url = variation['url'].format(**app.current_event.query_string_parameters)
            response = json.loads(urllib.request.urlopen(url).read())

        if response and experiment:
            response['matchedExperiment'] = experiment

        if post_process_config:
            response = post_processor.process_related_items(recommender, rec_config, variation, item_id, response)

        if len(response.get('itemList')) > num_results:
            response['itemList'] = response['itemList'][:num_results]

        headers = {}
        if config.get_version():
            headers['X-Personalization-Config-Version'] = config.get_version()

        synthetic_user = app.current_event.get_query_string_value(name="syntheticUser", default_value="0").lower() in ['1','yes','true']
        set_cache_headers(variation, headers, user_id, synthetic_user)

        return Response(status_code=HTTPStatus.OK,
                        content_type="application/json",
                        body=json.dumps(response, cls=CompatEncoder),
                        headers=headers
        )

def _rerank_items(namespace: str, recommender: str, user_id: str, item_ids: List[str], background: BackgroundTasks) -> Tuple[Response, Dict]:
    rec_config = config.get_recommender_config(namespace, recommender, ACTION_RERANK_ITEMS)
    if not rec_config:
        raise ConfigError(HTTPStatus.NOT_FOUND, 'RecommenderNotConfigured', 'Recommender not configured for this namespace and recommender path')

    variation, experiment = evaluate_variations(rec_config, user_id, background)
    context = resolve_context(variation)

    if variation.get('type') in ['personalize-campaign', 'personalize-recommender']:
        arn = variation.get('arn')
        filter_arn, filter_values = resolve_filter_parameters(variation, user_id)

        response = personalize_resolver.rerank_items(
                variation_config = variation,
                arn = arn,
                user_id = user_id,
                input_list = item_ids,
                filter_arn = filter_arn,
                filter_values = filter_values,
                context = context,
                include_metadata = try_decorate_items()
        )

        post_decorate_items(namespace, response)
    elif variation.get('type') == 'sagemaker':
        response = sagemaker_resolver.rerank_items(
                recommender,
                rec_config,
                variation,
                user_id = user_id,
                input_list = item_ids,
                context = context
        )

        post_decorate_items(namespace, response)
    elif variation.get('type') == 'lambda':
        response = lambda_resolver.rerank_items(
                recommender,
                rec_config,
                variation,
                user_id = user_id,
                input_list = item_ids,
                context = context
        )

        post_decorate_items(namespace, response)
    elif variation.get('type') == 'http':
        url = variation['url'].format(**app.current_event.query_string_parameters)
        response = json.loads(urllib.request.urlopen(url).read())

    if response and experiment:
        response['matchedExperiment'] = experiment

    post_process_config = rec_config.get('responsePostProcessor')
    if post_process_config:
        response = post_processor.process_rerank_items(recommender, rec_config, variation, user_id, response)

    return response, variation

@app.get("/rerank-items/<namespace>/<recommender>/<user_id>/<item_ids>", cors=True, compress=compress_responses)
@tracer.capture_method(capture_response=False)
def get_rerank_items(namespace: str, recommender: str, user_id: str, item_ids: str) -> Response:
    """ API entry point for reranking a list of items for a given user """
    tracer.put_annotation(key = 'EntryPoint', value = 'rerank-items')
    tracer.put_annotation(key = 'Namespace', value = namespace)
    tracer.put_annotation(key = 'Recommender', value = recommender)

    if is_resource_not_modified():
        return Response(status_code=HTTPStatus.NOT_MODIFIED,
                        content_type="text/plain",
                        body='Not mofified'
        )

    with BackgroundTasks() as background:
        logger.debug('Conditionally refreshing datastores in the backgound')
        ResponseDecorator.prepare_datastores(config.get_config(), background)

        input_list = item_ids.split(',')
        response, variation = _rerank_items(namespace, recommender, user_id, input_list, background)

        headers = {}
        if config.get_version():
            headers['X-Personalization-Config-Version'] = config.get_version()

        synthetic_user = app.current_event.get_query_string_value(name="syntheticUser", default_value="0").lower() in ['1','yes','true']
        set_cache_headers(variation, headers, user_id, synthetic_user)

        return Response(status_code=HTTPStatus.OK,
                        content_type="application/json",
                        body=json.dumps(response, cls=CompatEncoder),
                        headers=headers
        )

@app.post("/rerank-items/<namespace>/<recommender>/<user_id>", cors=True, compress=compress_responses)
@tracer.capture_method(capture_response=False)
def post_rerank_items(namespace: str, recommender: str, user_id: str) -> Response:
    """ API entry point for reranking a list of items for a given user """
    tracer.put_annotation(key = 'EntryPoint', value = 'rerank-items')
    tracer.put_annotation(key = 'Namespace', value = namespace)
    tracer.put_annotation(key = 'Recommender', value = recommender)

    with BackgroundTasks() as background:
        logger.debug('Conditionally refreshing datastores in the backgound')
        ResponseDecorator.prepare_datastores(config.get_config(), background)

        try:
            input_list = app.current_event.json_body
        except json.decoder.JSONDecodeError as e:
            raise JSONDecodeValidationError.from_json_decoder_error('InvalidJSONRequestPayload', e)

        if not isinstance(input_list, list):
            raise ValidationError('InvalidRequestPayload', 'Request body must be valid JSON (array of item IDs)')

        response,_ = _rerank_items(namespace, recommender, user_id, input_list)

        # No cache for you.
        headers = { 'Cache-Control': 'no-store' }
        if config.get_version():
            headers['X-Personalization-Config-Version'] = config.get_version()

        return Response(status_code=HTTPStatus.OK,
                        content_type="application/json",
                        body=json.dumps(response, cls=CompatEncoder),
                        headers=headers
        )

@app.post("/events/<namespace>", cors=True)
@tracer.capture_method(capture_response=False)
def post_put_events(namespace: str) -> Response:
    """ API entry point for incrementally sending events/interactions back to recommenders """
    tracer.put_annotation(key = 'EntryPoint', value = 'events')
    tracer.put_annotation(key = 'Namespace', value = namespace)

    ns_config = config.get_namespace_config(namespace)
    if not ns_config:
        raise ConfigError(HTTPStatus.NOT_FOUND, 'NamespaceNotFound', 'Namespace configuration not found for this namespace path')

    process_targets(namespace, ns_config, app.current_event)
    process_conversions(namespace, ns_config, app.current_event, config)

    # No cache for you.
    headers = { 'Cache-Control': 'no-store' }
    if config.get_version():
        headers['X-Personalization-Config-Version'] = config.get_version()

    return Response(status_code = HTTPStatus.OK,
                    content_type = 'text/plain',
                    body = '',
                    headers = headers)

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_HTTP)
@tracer.capture_lambda_handler(capture_response=False)
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event, context):
    """ Main function entry point that delegates to request router """
    try:
        return app.resolve(event, context)
    except PersonalizationError as e:
        logger.exception(e)
        return {
            'statusCode': e.status_code,
            'headers': {
                "Content-Type" : "application/json"
            },
            'body': json.dumps({
                'type': e.type,
                'code': e.error_code,
                'message': e.error_message
            })
        }
    except botocore.exceptions.ParamValidationError as e:
        logger.exception(e)
        return {
            'statusCode': HTTPStatus.BAD_REQUEST,
            'headers': {
                "Content-Type" : "application/json"
            },
            'body': json.dumps({
                'type': 'Validation',
                'code': 'ValidationError',
                'message': str(e)
            })
        }
    except Exception as e:
        logger.exception(e)
        formatted_lines = traceback.format_exc().splitlines()
        return {
            'statusCode': HTTPStatus.INTERNAL_SERVER_ERROR,
            'headers': {
                "Content-Type" : "application/json"
            },
            'body': json.dumps({
                'type': 'Unhandled',
                'code': 'InternalError',
                'message': str(e),
                'details': formatted_lines
            }, indent = 2)
        }
