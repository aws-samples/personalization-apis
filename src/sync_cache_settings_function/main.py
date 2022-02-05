# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import os
from typing import Dict, List, Tuple
from jsonpath_ng import parse
from aws_lambda_powertools import Logger, Tracer

tracer = Tracer()
logger = Logger()

apigw = boto3.client('apigateway')
cloudfront = boto3.client('cloudfront')

REST_API_ID = os.environ['RestApiId']
REST_API_STAGE = os.environ['RestApiStage']
CLOUD_FRONT_CACHE_POLICY_ID = os.environ['CloudFrontCachePolicyId']
CLOUD_FRONT_ORIGIN_REQUEST_POLICY_ID = os.environ['CloudFrontOriginRequestPolicyId']

APIGW_ROOT_PATHS = {
    'recommend-items': '/~1recommend-items~1{namespace}~1{recommender}~1{userId}/GET',
    'related-items': '/~1related-items~1{namespace}~1{recommender}~1{itemId}/GET',
    'rerank-items': '/~1rerank-items~1{namespace}~1{recommender}~1{userId}~1{itemIds}/GET'
}

@tracer.capture_method
def update_apigw_rest_stage_caching(personalization_config: Dict, cache_headers: List[str]):
    # Get current stage settings to determine cache cluster settings.
    response = apigw.get_stage(
        restApiId=REST_API_ID,
        stageName=REST_API_STAGE
    )

    cache_cluster_current_enabled = response['cacheClusterEnabled']
    cache_cluster_size = response['cacheClusterSize']
    cache_cluster_status = response['cacheClusterStatus']

    logger.info('Current APIGW cache cluster settings: enabled = %s, size = %s, status = %s',
        cache_cluster_current_enabled, cache_cluster_size, cache_cluster_status)

    ttls = {
        'recommend-items': None,
        'related-items': None,
        'rerank-items': None
    }

    # Seed TTLs with the minimal value across root cache control
    jsonpath_expr = parse('$.cacheControl..maxAge')
    max_ages = [match.value for match in jsonpath_expr.find(personalization_config)]
    logger.info('Max ages for root cacheControl: %s', max_ages)
    if max_ages:
        for item in ttls.items():
            ttls[item[0]] = min(max_ages)

    logger.debug('TTLs after applying root cacheControl: %s', ttls)

    for type in ttls.keys():
        jsonpath_expr = parse(f'$..recommenders.{type}')
        recommenders = [match.value for match in jsonpath_expr.find(personalization_config)]

        for recommender in recommenders:
            jsonpath_expr = parse('$..cacheControl')
            cache_controls = [match.value for match in jsonpath_expr.find(recommender)]
            logger.debug('cacheControls for recommender %s/%s: %s', type, recommender.keys(), cache_controls)

            for cache_control in cache_controls:
                jsonpath_expr = parse('$..maxAge')
                max_ages = [match.value for match in jsonpath_expr.find(cache_control)]
                if max_ages:
                    for item in ttls.items():
                        min_age = min(max_ages)
                        ttls[type] = min_age if not ttls[type] else min(min_age, ttls[type])

    patch = []

    cache_cluster_enabled = False

    for item in ttls.items():
        type = item[0]
        ttl = item[1]

        if ttl and ttl > 0:
            cache_cluster_enabled = True
            patch.extend([{
                'op': 'replace',
                'path': f'{APIGW_ROOT_PATHS[type]}/caching/enabled',
                'value': 'true'
            },{
                'op': 'replace',
                'path': f'{APIGW_ROOT_PATHS[type]}/caching/ttlInSeconds',
                'value': f'{ttl}'
            }])
        else:
            patch.append({
                'op': 'replace',
                'path': f'{APIGW_ROOT_PATHS[type]}/caching/enabled',
                'value': 'false'
            })

    patch.append({
        'op': 'replace',
        'path': '/cacheClusterEnabled',
        'value': ('true' if cache_cluster_enabled else 'false')
    })

    if not cache_cluster_enabled and cache_cluster_current_enabled:
        logger.info('Stage caching is NOT configured for any methods but cache cluster is currently enabled for stage; disabling cache cluster')

    if cache_cluster_enabled and not cache_cluster_size:
        logger.info('Stage caching is configured for one or more methods but cache cluster is currently not enabled for stage; enabling cache cluster')
        patch.append({
            'op': 'replace',
            'path': '/cacheClusterSize',
            'value': '1.6'
        })

    logger.debug('APIGW patchOperations: %s', patch)

    response = apigw.update_stage(
        restApiId=REST_API_ID,
        stageName=REST_API_STAGE,
        patchOperations=patch
    )

    logger.debug(json.dumps(response, indent=2, default=str))

    response = apigw.get_resources(
        restApiId=REST_API_ID,
        limit = 500
    )

    paths_to_match = [
        '/recommend-items/{namespace}/{recommender}/{userId}',
        '/related-items/{namespace}/{recommender}/{itemId}',
        '/rerank-items/{namespace}/{recommender}/{userId}/{itemIds}'
    ]
    resource_ids = []
    for item in response['items']:
        methods = item.get('resourceMethods')
        if not methods or not methods.get('GET'):
            continue

        if item['path'] in paths_to_match:
            resource_ids.append(item['id'])

    for resource_id in resource_ids:
        response = apigw.get_integration(
            restApiId=REST_API_ID,
            resourceId=resource_id,
            httpMethod='GET'
        )

        cache_keys = []
        patch = []

        for cache_key in response['cacheKeyParameters']:
            if not cache_key.startswith('method.request.header.'):
                cache_keys.append(cache_key)

        for cache_header in cache_headers:
            cache_keys.append(f'method.request.header.{cache_header}')

        apigw.update_integration(
            restApiId=REST_API_ID,
            resourceId=resource_id,
            httpMethod='GET',
            patchOperations=[
                {
                    'op': 'add'|'remove'|'replace'|'move'|'copy'|'test',
                    'path': 'string',
                    'value': 'string',
                    'from': 'string'
                },
            ]
        )

@tracer.capture_method
def determine_required_cloudfront_headers(personalization_config: Dict) -> Tuple[List, List]:
    jsonpath_expr = parse('$..autoContext..rules[*].header')
    auto_context_headers = [match.value for match in jsonpath_expr.find(personalization_config)]
    origin_request_headers = set(i.lower() for i in auto_context_headers)
    cache_headers = set(origin_request_headers)

    jsonpath_expr = parse('$..autoContext..rules[*].type')
    auto_context_types = [match.value for match in jsonpath_expr.find(personalization_config)]
    for type in auto_context_types:
        if type == 'season-of-year':
            # Latitude needed for North/South hemisphere. However, due to high variability in
            # the latitude header value, do NOT include in cache headers to keep cache hit rate reasonable.
            origin_request_headers.add('CloudFront-Viewer-Latitude'.lower())

        if type in [ 'hour-of-day', 'day-of-week', 'season-of-year' ]:
            origin_request_headers.add('CloudFront-Viewer-Time-Zone'.lower())
            cache_headers.add('CloudFront-Viewer-Time-Zone'.lower())

    # For CORS
    origin_request_headers.add('origin')
    origin_request_headers.add('access-control-request-headers')
    origin_request_headers.add('access-control-request-method')

    logger.info('Origin request headers: %s', origin_request_headers)
    logger.info('Cache headers: %s', cache_headers)

    return list(origin_request_headers), list(cache_headers)

@tracer.capture_method
def update_cloudfront_origin_request_policy(origin_request_headers: List[str]):
    response = cloudfront.get_origin_request_policy(Id = CLOUD_FRONT_ORIGIN_REQUEST_POLICY_ID)

    logger.debug(json.dumps(response, indent = 2, default=str))

    policy_config = response['OriginRequestPolicy']['OriginRequestPolicyConfig']

    update_required = False

    if len(origin_request_headers) > 0:
        update_required = (policy_config['HeadersConfig']['HeaderBehavior'] != 'whitelist' or
                not policy_config['HeadersConfig'].get('Headers') or
                not policy_config['HeadersConfig']['Headers'].get('Items') or
                sorted(policy_config['HeadersConfig']['Headers']['Items'], key=str.lower) != sorted(origin_request_headers, key=str.lower))

        policy_config['HeadersConfig']['HeaderBehavior'] = 'whitelist'
        policy_config['HeadersConfig']['Headers'] = {
            'Quantity': len(origin_request_headers),
            'Items': origin_request_headers
        }
    else:
        update_required = policy_config['HeadersConfig']['HeaderBehavior'] != 'none'
        policy_config['HeadersConfig']['HeaderBehavior'] = 'none'
        policy_config['HeadersConfig'].pop('Headers', None)

    if update_required:
        logger.info('Updating CloudFront origin request policy %s', CLOUD_FRONT_ORIGIN_REQUEST_POLICY_ID)

        cloudfront.update_origin_request_policy(
            Id = CLOUD_FRONT_ORIGIN_REQUEST_POLICY_ID,
            IfMatch = response['ETag'],
            OriginRequestPolicyConfig = policy_config
        )
    else:
        logger.info('Update of CloudFront origin request policy not required')

@tracer.capture_method
def update_cloudfront_cache_policy(personalization_config: Dict, cache_headers: List[str]):
    jsonpath_expr = parse('$..cacheControl.*')
    cache_controls = [match.value for match in jsonpath_expr.find(personalization_config)]
    logger.debug('cacheControl configs: %s', cache_controls)

    min_age = max_age = None

    # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html#ExpirationDownloadDist
    for cache_control in cache_controls:
        if isinstance(cache_control, dict):
            age = cache_control['maxAge']
            min_age = age if not min_age else min(min_age, age)
            max_age = age if not max_age else max(max_age, age)

    logger.info('maxAge minimum = %s; maxAge maximum = %s', min_age, max_age)

    response = cloudfront.get_cache_policy(Id = CLOUD_FRONT_CACHE_POLICY_ID)

    logger.debug(json.dumps(response, indent = 2, default=str))

    policy_config = response['CachePolicy']['CachePolicyConfig']

    update_required = False

    if len(cache_headers) > 0:
        update_required = (policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['HeaderBehavior'] != 'whitelist' or
                not policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig'].get('Headers') or
                not policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['Headers'].get('Items') or
                sorted(policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['Headers']['Items'], key=str.lower) != sorted(cache_headers, key=str.lower))

        policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['HeaderBehavior'] = 'whitelist'
        policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['Headers'] = {
            'Quantity': len(cache_headers),
            'Items': cache_headers
        }
    else:
        update_required = policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['HeaderBehavior'] != 'none'
        policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig']['HeaderBehavior'] = 'none'
        policy_config['ParametersInCacheKeyAndForwardedToOrigin']['HeadersConfig'].pop('Headers', None)

    update_required = update_required or policy_config['MinTTL'] != min_age or policy_config['MaxTTL'] != max_age

    policy_config['MinTTL'] = min_age
    policy_config['DefaultTTL'] = min_age
    policy_config['MaxTTL'] = max_age

    if update_required:
        logger.info('Updating CloudFront cache policy %s', CLOUD_FRONT_CACHE_POLICY_ID)

        cloudfront.update_cache_policy(
            Id = CLOUD_FRONT_CACHE_POLICY_ID,
            IfMatch = response['ETag'],
            CachePolicyConfig = policy_config
        )
    else:
        logger.info('Update of CloudFront cache policy is not required')

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, _):
    # The "event" is the configuration (passed as input to step function)
    logger.info(event)

    # Check the autoProvision flag on all cacheControl objects to make sure auto-provisioning is not disabled.
    jsonpath_expr = parse('$..cacheControl[*].autoProvision')
    auto_provision = [match.value for match in jsonpath_expr.find(event)]
    logger.debug('cacheControl.autoProvision values: %s', auto_provision)
    if len(auto_provision) == 0 or not False in auto_provision:
        origin_request_headers, cache_headers = determine_required_cloudfront_headers(event)

        if REST_API_ID and REST_API_STAGE:
            update_apigw_rest_stage_caching(event, cache_headers)
            pass
        else:
            # This can be the case when a dedicated CloudFront distribution is being used for caching.
            logger.info('REST API ID and/or stage name are not specified; skipping REST API sync')

        if CLOUD_FRONT_CACHE_POLICY_ID and CLOUD_FRONT_ORIGIN_REQUEST_POLICY_ID:
            update_cloudfront_origin_request_policy(origin_request_headers)
            update_cloudfront_cache_policy(event, cache_headers)
        else:
            # This can be the case when an API Gateway Edge endpoint type is being used (API Gateway manages its own CloudFront distribution)
            logger.info('CloudFront cache policy ID and/or origin request policy ID are not specified; skipping')
    else:
        logger.info('Auto provisioning of caching related resources is disabled for at least one cacheControl configuration; skipping CloudFront/API Gateway sync')
