# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import os
from typing import Dict
from crhelper import CfnResource
from aws_lambda_powertools import Logger

logger = Logger()

personalize = boto3.client('personalize')
appconfig = boto3.client('appconfig')
helper = CfnResource()

appconfig_application_id = os.environ['AppConfigApplicationId']
appconfig_config_profile_id = os.environ['AppConfigConfigurationProfileId']
appconfig_environment_id = os.environ['AppConfigEnvironmentId']
appconfig_deployment_strategy_id = os.environ['AppConfigDeploymentStrategyId']

recipe_arn_type_mapping = {
    "arn:aws:personalize:::recipe/aws-ecomm-customers-who-viewed-x-also-viewed": "related-items",
    "arn:aws:personalize:::recipe/aws-ecomm-frequently-bought-together": "related-items",
    "arn:aws:personalize:::recipe/aws-ecomm-popular-items-by-purchases": "recommend-items",
    "arn:aws:personalize:::recipe/aws-ecomm-popular-items-by-views": "recommend-items",
    "arn:aws:personalize:::recipe/aws-ecomm-recommended-for-you": "recommend-items",
    "arn:aws:personalize:::recipe/aws-vod-because-you-watched-x": "related-items",
    "arn:aws:personalize:::recipe/aws-vod-more-like-x": "related-items",
    "arn:aws:personalize:::recipe/aws-vod-most-popular": "recommend-items",
    "arn:aws:personalize:::recipe/aws-vod-top-picks": "recommend-items",
    "arn:aws:personalize:::recipe/aws-hrnn": "recommend-items",
    "arn:aws:personalize:::recipe/aws-hrnn-coldstart": "recommend-items",
    "arn:aws:personalize:::recipe/aws-hrnn-metadata": "recommend-items",
    "arn:aws:personalize:::recipe/aws-personalized-ranking": "rerank-items",
    "arn:aws:personalize:::recipe/aws-popularity-count": "recommend-items",
    "arn:aws:personalize:::recipe/aws-similar-items": "related-items",
    "arn:aws:personalize:::recipe/aws-sims": "related-items",
    "arn:aws:personalize:::recipe/aws-user-personalization": "recommend-items"
}

def generate_api_config(dataset_group_names_prop: str) -> Dict:
    """ Generates personalization APIs app config based on recommenders, campaigns, and event trackers for the specified dataset groups

    Arguments:
        dataset_group_names_prop (string) - comma separated list of Personalize dataset group names to check for recommenders, campaigns,
            and event trackers or "all" to check all dataset groups in the current account & region
    """

    # Start with an empty base configuration that implements some general caching.
    config = {
        "version": "2",
        "description": "This configuration was automatically generated based on the active recommenders/campaigns for a supplied list of dataset groups",
        "cacheControl": {
            "autoProvision": True,
            "userSpecified": {
                "maxAge": 10,
                "directives": "private"
            },
            "syntheticUserSpecified": {
                "maxAge": 300,
                "directives": "public"
            },
            "noUserSpecified": {
                "maxAge": 1200,
                "directives": "public"
            }
        },
        "namespaces": {}
    }

    dataset_group_names = [dsg.strip() for dsg in dataset_group_names_prop.split(',')]
    all_dsgs = len(dataset_group_names) == 1 and dataset_group_names[0].lower() == 'all'

    logger.info('Dataset group names: %s', dataset_group_names)
    logger.info('Matching all dataset groups in current region for account: %s', all_dsgs)

    logger.info('Looking up recommenders and matching to dataset group(s)')
    paginator = personalize.get_paginator('list_recommenders')
    for recommender_page in paginator.paginate():
        for recommender in recommender_page['recommenders']:
            dataset_group_name = recommender['datasetGroupArn'].split('/')[-1]

            if all_dsgs or dataset_group_name in dataset_group_names:
                action_type = recipe_arn_type_mapping.get(recommender['recipeArn'])
                if not action_type:
                    # Perhaps a new recipe?
                    logger.error('Unable to determine action type for recipe %s for recommender %s; skipping recommender', recommender['recipeArn'], recommender['recommenderArn'])
                    continue

                variation_name = recommender['recipeArn'].split('/')[-1].replace('aws-', 'personalize-')

                variation_config = (config['namespaces']
                    .setdefault(dataset_group_name, {})
                    .setdefault('recommenders', {})
                    .setdefault(action_type, {})
                    .setdefault(recommender['name'], {})
                    .setdefault('variations', {})
                    .setdefault(variation_name, {})
                )

                variation_config['type'] = 'personalize-recommender'
                variation_config['arn'] = recommender['recommenderArn']

    logger.info('Looking up campaigns and matching to dataset group(s)')
    paginator = personalize.get_paginator('list_campaigns')
    for campaign_page in paginator.paginate():
        for campaign in campaign_page['campaigns']:
            response = personalize.describe_campaign(campaignArn = campaign['campaignArn'])
            sv_arn = response['campaign']['solutionVersionArn']

            response = personalize.describe_solution_version(solutionVersionArn = sv_arn)
            dataset_group_name = response['solutionVersion']['datasetGroupArn'].split('/')[-1]

            if all_dsgs or dataset_group_name in dataset_group_names:
                recipe_arn = response['solutionVersion']['recipeArn']
                action_type = recipe_arn_type_mapping.get(recipe_arn)
                if not action_type:
                    # Perhaps a new recipe?
                    logger.error('Unable to determine action type for recipe %s for campaign %s; skipping campaign', recipe_arn, campaign['campaignArn'])
                    continue

                variation_name = recipe_arn.split('/')[-1].replace('aws-', 'personalize-')

                variation_config = (config['namespaces']
                    .setdefault(dataset_group_name, {})
                    .setdefault('recommenders', {})
                    .setdefault(action_type, {})
                    .setdefault(campaign['name'], {})
                    .setdefault('variations', {})
                    .setdefault(variation_name, {})
                )

                variation_config['type'] = 'personalize-campaign'
                variation_config['arn'] = campaign['campaignArn']

    logger.info('Looking up event trackers and matching to dataset group(s)')
    paginator = personalize.get_paginator('list_event_trackers')
    for event_tracker_page in paginator.paginate():
        for event_tracker in event_tracker_page['eventTrackers']:
            response = personalize.describe_event_tracker(eventTrackerArn = event_tracker['eventTrackerArn'])

            dataset_group_name = response['eventTracker']['datasetGroupArn'].split('/')[-1]
            if all_dsgs or dataset_group_name in dataset_group_names:
                targets = (config['namespaces']
                    .setdefault(dataset_group_name, {})
                    .setdefault('eventTargets', [])
                )

                targets.append({
                    'type': 'personalize-event-tracker',
                    'trackingId': response['eventTracker']['trackingId']
                })

    return config

def create_and_deploy_hosted_config(config: Dict):
    """ Creates and deploys a configuration to AppConfig as a hosted configuration version """

    logger.info('Creating hosted configuration...')
    response = appconfig.create_hosted_configuration_version(
        ApplicationId = appconfig_application_id,
        ConfigurationProfileId = appconfig_config_profile_id,
        Description = 'Generated configuration based on supplied list of dataset groups',
        ContentType = 'application/json',
        Content = json.dumps(config, indent = 4)
    )

    logger.debug(json.dumps(response, indent = 2, default = str))
    config_version = response['VersionNumber']

    logger.info('Starting deployment...')
    response = appconfig.start_deployment(
        ApplicationId = appconfig_application_id,
        EnvironmentId = appconfig_environment_id,
        DeploymentStrategyId = appconfig_deployment_strategy_id,
        ConfigurationProfileId = appconfig_config_profile_id,
        ConfigurationVersion = str(config_version),
        Description = 'Automatic configuration deployment after generating configuration',
        Tags={
            'CreatedBy': 'Personalization-APIs-Solution'
        }
    )
    logger.debug(json.dumps(response, indent = 2, default = str))

def generate_and_deploy_config(dataset_group_names_prop: str):
    if dataset_group_names_prop.strip():
        config = generate_api_config(dataset_group_names_prop)
        create_and_deploy_hosted_config(config)
    else:
        logger.info('Dataset group name(s) not specified; skipping generation of configuration')

@helper.create
def create_resource(event, _):
    generate_and_deploy_config(event['ResourceProperties']['DatasetGroupNames'])

@helper.delete
def delete_resource(event, _):
    """ Delete hosted configuration versions

    This is necessary here since hosted configurations are created outside of CloudFormation
    and therefore need to cleaned up before depedent AppConfig resources can be deleted by
    CloudFormation when the project is deleted.
    """
    logger.info('Deleting all hosted configuration versions for application %s and config profile %s', appconfig_application_id, appconfig_config_profile_id)

    page_count = 0
    while page_count < 10:
        response = appconfig.list_hosted_configuration_versions(
            ApplicationId = appconfig_application_id,
            ConfigurationProfileId = appconfig_config_profile_id,
            MaxResults = 50 # no paginator and max is 50
        )

        if len(response['Items']) == 0:
            break

        for config_version in response['Items']:
            logger.info('Deleting hosted configuration version %s', config_version["VersionNumber"])
            response = appconfig.delete_hosted_configuration_version(
                ApplicationId = appconfig_application_id,
                ConfigurationProfileId = appconfig_config_profile_id,
                VersionNumber = config_version['VersionNumber']
            )

        page_count += 1

def lambda_handler(event, context):
    """ Entry point of function called from either CloudFormation or directly under test
    """
    logger.debug('## ENVIRONMENT VARIABLES')
    logger.debug(os.environ)
    logger.debug('## EVENT')
    logger.debug(event)

    # If the event has a RequestType, we're being called by CFN as custom resource
    if event.get('RequestType'):
        logger.info('Function called from CloudFormation as custom resource')
        helper(event, context)
    else:
        logger.info('Function called outside of CloudFormation')
        # Called function directly (i.e. testing in Lambda console or called directly)
        generate_and_deploy_config(event['ResourceProperties']['DatasetGroupNames'])