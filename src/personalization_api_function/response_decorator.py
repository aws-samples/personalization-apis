# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Personalization response decorators
"""

import boto3
import botocore
import os
import time
import math
import dbm
import json
import gzip
import shutil

from typing import Any, Dict, List
from http import HTTPStatus
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from personalization_error import ConfigError, DynamoDbError
from personalization_constants import LOCAL_DB_FILENAME, LOCAL_DB_GZIP_FILENAME
from background_tasks import BackgroundTasks

tracer = Tracer()
logger = Logger(child=True)
metrics = Metrics()

# Should these be in the config?
table_name_prefix = os.environ.get('ItemsTableNamePrefix', 'PersonalizationApiItemMetadata_')
primary_key_name = os.environ.get('ItemsTablePrimaryKeyFieldName', 'id')

PREPARE_CHECK_FREQUENCY = 5 # 5 seconds
DEFAULT_LOCALDB_DOWNLOAD_FREQ = 300 # 5 minutes
class ResponseDecorator(ABC):
    _decorators: Dict[str, Any] = {}
    _last_prepare_check = 0
    _last_localdb_download_attempt = {}

    @abstractmethod
    def decorate(self, response: Dict) -> Dict:
        pass

    def close(self):
        pass

    @staticmethod
    def prepare_datastores(config: Dict, background: BackgroundTasks):
        start = time.time()

        if start - ResponseDecorator._last_prepare_check > PREPARE_CHECK_FREQUENCY:
            bucket = os.environ['StagingBucket']

            prepared_count = 0

            for namespace, namespace_config in config['namespaces'].items():
                metadata_config = namespace_config.get('inferenceItemMetadata')
                if not metadata_config:
                    continue

                type = metadata_config.get('type')

                if type == 'localdb':
                    sync_interval = metadata_config.get('syncInterval', DEFAULT_LOCALDB_DOWNLOAD_FREQ)

                    if start - ResponseDecorator._last_localdb_download_attempt.get(namespace, 0) > sync_interval:
                        ResponseDecorator._last_localdb_download_attempt[namespace] = time.time()
                        background.submit(ResponseDecorator._download_localdb, namespace = namespace, bucket = bucket)
                        prepared_count += 1
                    else:
                        logger.debug('Localdb inference metadata sync check for namespace %s not due yet', namespace)

                elif type == 'dynamodb':
                    ResponseDecorator._decorators[namespace] = DynamoDbResponseDecorator(table_name_prefix + namespace, primary_key_name)
                    prepared_count += 1

            ResponseDecorator._last_prepare_check = prepare_done = time.time()

            if prepared_count > 0:
                logger.info('Prepared %s datastores in %0.2fms', prepared_count, prepare_done - start)

        else:
            logger.debug('Item metadata datastores not due for prepare check')

    @staticmethod
    def get_instance(namespace: str, config: Dict) -> Any:
        """ Creates and returns response decorator based on a namespace configuration """
        namespace_config = config.get_namespace_config(namespace)
        if not namespace_config:
            return None

        metadata_config = namespace_config.get('inferenceItemMetadata')
        if not metadata_config:
            return None

        decorator = ResponseDecorator._decorators.get(namespace)
        if not decorator:
            type = metadata_config.get('type')
            if  type == 'localdb':
                decorator = LocalDbResponseDecorator(namespace)
            elif metadata_config.get('type') == 'dynamodb':
                decorator = DynamoDbResponseDecorator(table_name_prefix + namespace, primary_key_name)
            else:
                raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'UnsupportedInferenceItemMetadataType', 'Inference item metadata type is not supported')

            ResponseDecorator._decorators[namespace] = decorator

        return decorator

    @staticmethod
    def _download_localdb(namespace: str, bucket: str, s3: Any = None):
        if not s3:
            s3 = boto3.client('s3')

        local_dir = f'/tmp/{namespace}'
        if not os.path.isdir(local_dir):
            os.makedirs(local_dir)

        local_file = f'{local_dir}/{LOCAL_DB_FILENAME}'

        key = f'localdbs/{namespace}/{LOCAL_DB_GZIP_FILENAME}'

        logger.info('Downloading s3://%s/%s and uncompressing to %s', bucket, key, local_file)
        try:
            response = s3.get_object(Bucket = bucket, Key = key)
            stream = gzip.GzipFile(None, 'rb', fileobj = response['Body'])
            with open(local_file, 'wb') as out:
                shutil.copyfileobj(stream, out)

            old_decorator = ResponseDecorator._decorators.get(namespace)
            ResponseDecorator._decorators[namespace] = LocalDbResponseDecorator(namespace)
            if old_decorator:
                old_decorator.close()

        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                logger.error('Staged localdb file s3://%s/%s either does not exist or access has been revoked', bucket, key)
            else:
                raise e

class LocalDbResponseDecorator(ResponseDecorator):
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.local_file = f'/tmp/{self.namespace}/{LOCAL_DB_FILENAME}'
        if os.path.isfile(self.local_file):
            self.dbm_file = dbm.open(self.local_file, 'r')
        else:
            self.dbm_file = None

    def __del__(self):
        self.close()

    def close(self):
        try:
            if self.dbm_file:
                self.dbm_file.close()
        except Exception:
            pass
        self.dbm = None

    @tracer.capture_method
    def decorate(self, response: Dict):
        if not self.dbm_file and os.path.isfile(self.local_file):
            self.dbm_file = dbm.open(self.local_file, 'r')

        if self.dbm_file:
            # Create lookup dictionary so results from DDB can be efficiently merged into response.
            lookup: Dict[str, List[int]] = {}
            items_key_name = 'itemList' if 'itemList' in response else 'personalizedRanking'
            for idx,item in enumerate(response[items_key_name]):
                lookup.setdefault(item['itemId'], []).append(idx)

            unique_items = list(lookup.keys())

            def get_item(id):
                s = self.dbm_file.get(id)
                return json.loads(s) if s else s

            for id in unique_items:
                item = get_item(id)
                if item:
                    for idx in lookup[id]:
                        response[items_key_name][idx]['metadata'] = item
        else:
            logger.error('Local DB file %s does not exist on local disk. Has item metadata been uploaded and staged in S3?', self.local_file)

class DynamoDbResponseDecorator(ResponseDecorator):
    MAX_BATCH_SIZE = 50
    __dynamodb = boto3.resource('dynamodb')

    def __init__(self, table_name: str, primary_key_name: str):
        self.table_name = table_name
        self.primary_key_name = primary_key_name

    @tracer.capture_method
    def decorate(self, response: Dict):
        try:
            self._decorate(response)
        except DynamoDbResponseDecorator.__dynamodb.meta.client.exceptions.LimitExceedException as e:
            metrics.add_metric(name="DynamoDBLimitExceed", unit=MetricUnit.Count, value=1)
            raise DynamoDbError(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    e.response['Error']['Code'],
                    e.response['Error']['Message'],
                    e.response['ResponseMetadata']['HTTPStatusCode']
            )
        except botocore.exceptions.ClientError as e:
            raise DynamoDbError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    e.response['Error']['Code'],
                    e.response['Error']['Message'],
                    e.response['ResponseMetadata']['HTTPStatusCode']
            )

    def _decorate(self, response: Dict):
        items_key_name = 'itemList' if 'itemList' in response else 'personalizedRanking'

        # Create lookup dictionary so results from DDB can be efficiently merged into response.
        lookup = {}
        for idx,item in enumerate(response[items_key_name]):
            lookup.setdefault(item['itemId'], []).append(idx)

        unique_items = list(lookup.keys())

        if len(unique_items) > self.MAX_BATCH_SIZE:
            chunk_size = int(math.ceil(len(unique_items) / math.ceil(len(unique_items)/self.MAX_BATCH_SIZE)))

            item_chunks = [unique_items[i:i + chunk_size] for i in range(0, len(unique_items), chunk_size)]

            logger.debug('Launching %d background threads to lookup metadata for %d unique items in chunks of max %d',
                    len(item_chunks), len(unique_items), chunk_size)

            with ThreadPoolExecutor() as executor:
                futures: Future = []
                for item_ids in item_chunks:
                    batch_keys = {
                        self.table_name: {
                            'Keys': [{self.primary_key_name: item_id} for item_id in item_ids]
                        }
                    }

                    futures.append(
                        executor.submit(self._batch_get, None, batch_keys)
                    )

                for future in as_completed(futures):
                    retrieved = future.result()
                    # Decorate each item with a "metadata" field containing info from DDB.
                    for ddb_item in retrieved[self.table_name]:
                        for idx in lookup[ddb_item[self.primary_key_name]]:
                            response[items_key_name][idx]['metadata'] = ddb_item['attributes']
        else:
            batch_keys = {
                self.table_name: {
                    'Keys': [{self.primary_key_name: item_id} for item_id in unique_items]
                }
            }

            retrieved = self._batch_get(DynamoDbResponseDecorator.__dynamodb, batch_keys)
            # Decorate each item with a "metadata" field containing info from DDB.
            for ddb_item in retrieved[self.table_name]:
                for idx in lookup[ddb_item[self.primary_key_name]]:
                    response[items_key_name][idx]['metadata'] = ddb_item['attributes']

    def _batch_get(self, dynamodb, batch_keys: Dict) -> Dict:
        """
        Gets a batch of items from Amazon DynamoDB. Batches can contain keys from
        more than one table.

        When Amazon DynamoDB cannot process all items in a batch, a set of unprocessed
        keys is returned. This function uses an exponential backoff algorithm to retry
        getting the unprocessed keys until all are retrieved or the specified
        number of tries is reached.

        :param dynamodb: DynamoDB resource or None and one will be created (such as in thread)
        :param batch_keys: The set of keys to retrieve. A batch can contain at most 100
                        keys. Otherwise, Amazon DynamoDB returns an error.
        :return: The dictionary of retrieved items grouped under their respective
                table names.
        """
        if not dynamodb:
            dynamodb = boto3.resource('dynamodb')

        tries = 0
        max_tries = 3
        sleep_millis = 250  # Start with 250ms of sleep, then exponentially increase.
        retrieved = {key: [] for key in batch_keys}
        while tries < max_tries:
            response = dynamodb.batch_get_item(RequestItems=batch_keys)
            # Collect any retrieved items and retry unprocessed keys.
            for key in response.get('Responses', []):
                retrieved[key] += response['Responses'][key]

            unprocessed = response['UnprocessedKeys']

            if len(unprocessed) > 0:
                batch_keys = unprocessed
                unprocessed_count = sum([len(batch_key['Keys']) for batch_key in batch_keys.values()])
                logger.warn('%s unprocessed keys returned. Sleeping for %sms, then will retry', unprocessed_count, sleep_millis)

                tries += 1
                if tries < max_tries:
                    logger.info('Sleeping for %sms', sleep_millis)
                    time.sleep(sleep_millis / 1000.0)
                    sleep_millis = min(sleep_millis * 2, 1500)
            else:
                break

        return retrieved
