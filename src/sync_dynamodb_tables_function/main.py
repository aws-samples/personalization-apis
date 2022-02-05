# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os

from typing import Dict, List
from aws_lambda_powertools import Logger, Tracer

tracer = Tracer()
logger = Logger()

dynamodb = boto3.resource('dynamodb')

primary_key_name = os.environ.get('ItemsTablePrimaryKeyFieldName', 'id')
table_name_prefix = os.environ.get('ItemsTableNamePrefix', 'PersonalizationApiItemMetadata_')

class ResourcePending(Exception):
    pass

@tracer.capture_method
def sync_tables(config: Dict) -> List[str]:
    table_names = []
    namespaces = config.get('namespaces')
    if namespaces:
        for item in namespaces.items():
            table_name = sync_table(item[0], item[1])
            if table_name:
                table_names.append(table_name)
    else:
        for item in config.items():
            table_name = sync_table(item[0], item[1])
            if table_name:
                table_names.append(table_name)

    return table_names

@tracer.capture_method
def sync_table(path: str, ns_config: Dict) -> str:
    metadata_config = ns_config.get('inferenceItemMetadata')
    if not metadata_config:
        return ''

    if metadata_config.get('type') != 'dynamodb':
        logger.info('Inference metadata type is not dynamodb so skipping resource sync/provisioning')
        return ''

    table_name = table_name_prefix + path
    table_status = None

    if metadata_config.get('autoProvision') is not None and metadata_config.get('autoProvision') == False:
        logger.info('Auto provisioning inference item metadata resources for namespace "%s" is disabled; skipping')
        return table_name

    billing_mode = metadata_config.get('billingMode', 'PAY_PER_REQUEST')
    if not billing_mode in ['PAY_PER_REQUEST','PROVISIONED']:
        raise Exception(f'"inferenceItemMetadata.billingMode" ({billing_mode}) for namespace ("{path}") is invalid; must be PAY_PER_REQUEST or PROVISIONED')

    provisioned_throughput = metadata_config.get('provisionedThroughput')
    if billing_mode == 'PROVISIONED' and not provisioned_throughput:
        raise Exception(f'"inferenceItemMetadata.provisionedThroughput" is required for billingMode PROVISIONED but is not specfied for namespace ("{path}") in application configuration')

    try:
        response = dynamodb.meta.client.describe_table(TableName = table_name)

        table_status = response['Table']['TableStatus']

        if response['Table']['BillingModeSummary']['BillingMode'] != billing_mode:
            logger.info('Updating BillingMode for table %s from %s to %s', table_name, response['Table']['BillingModeSummary']['BillingMode'], billing_mode)
            if billing_mode == 'PAY_PER_REQUEST':
                dynamodb.meta.client.update_table(
                    TableName = table_name,
                    BillingMode = billing_mode
                )
            else:
                dynamodb.meta.client.update_table(
                    TableName = table_name,
                    BillingMode = billing_mode,
                    ProvisionedThroughput = {
                        'ReadCapacityUnits': provisioned_throughput['readCapacityUnits'],
                        'WriteCapacityUnits': provisioned_throughput['writeCapacityUnits']
                    }
                )
        elif (billing_mode == 'PROVISIONED' and
                (response['Table']['ProvisionedThroughput']['ReadCapacityUnits'] != provisioned_throughput['readCapacityUnits'] or
                response['Table']['ProvisionedThroughput']['WriteCapacityUnits'] != provisioned_throughput['writeCapacityUnits'])):
            logger.info('Provisioned read and/or write capacity units to not match configuration for table %s; updating table', table_name)
            dynamodb.meta.client.update_table(
                TableName = table_name,
                ProvisionedThroughput = {
                    'ReadCapacityUnits': provisioned_throughput['readCapacityUnits'],
                    'WriteCapacityUnits': provisioned_throughput['writeCapacityUnits']
                }
            )
        else:
            logger.info('Table %s already exists and billing mode (%s) and capacity units match configuration', table_name, billing_mode)

    except dynamodb.meta.client.exceptions.ResourceInUseException:
        raise ResourcePending(f'Table {table_name} is in-use and cannot be updated; status is {table_status}')

    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        logger.info('Table %s does not exist; creating table', table_name)

        create_params = {
            'TableName': table_name,
            'AttributeDefinitions': [
                {
                    'AttributeName': primary_key_name,
                    'AttributeType': 'S',
                }
            ],
            'KeySchema': [
                {
                    'AttributeName': primary_key_name,
                    'KeyType': 'HASH',
                }
            ],
            'BillingMode': billing_mode,
            'Tags': [{
                'Key': 'CreatedBy',
                'Value': 'Personalization-APIs-Solution'
            }]
        }

        logger.debug(create_params)

        if billing_mode == 'PROVISIONED':
            create_params['ProvisionedThroughput'] = {
                'ReadCapacityUnits': provisioned_throughput['readCapacityUnits'],
                'WriteCapacityUnits': provisioned_throughput['writeCapacityUnits']
            }

        response = dynamodb.meta.client.create_table(**create_params)
        table_status = response['TableDescription']['TableStatus']

    if table_status in [ 'CREATING', 'UPDATING' ]:
        logger.info('Table %s is being created/updated', table_name)
        raise ResourcePending(f'Table {table_name} is still being created')

    return table_name

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, _):
    logger.info(event)
    table_names = sync_tables(event)
    return table_names