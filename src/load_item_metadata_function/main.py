# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import jsonlines
import os
import copy
import urllib
import json
import dbm
import gzip

from typing import Tuple
from io import TextIOWrapper, RawIOBase
from decimal import Decimal
from boto3.dynamodb.conditions import Attr
from aws_lambda_powertools import Logger, Tracer
from personalization_config import PersonalizationConfig
from personalization_constants import LOCAL_DB_FILENAME, LOCAL_DB_GZIP_FILENAME

tracer = Tracer()
logger = Logger()

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
config = PersonalizationConfig.get_instance()
primary_key_name = os.environ.get('ItemsTablePrimaryKeyFieldName', 'id')
table_name_prefix = os.environ.get('ItemsTableNamePrefix', 'PersonalizationApiItemMetadata_')

class StreamingBodyIO(RawIOBase):
    """Wrap a boto StreamingBody in the IOBase API."""
    def __init__(self, body):
        self.body = body

    def readable(self):
        return True

    def read(self, n: int = -1):
        n = None if n < 0 else n
        return self.body.read(n)

@tracer.capture_method
def bulk_load_datastore(bucket: str, key: str, namespace: str):
    ns_config = config.get_namespace_config(namespace)
    if not ns_config:
        raise Exception(f'Namespace ("{namespace}") in S3 object key ("{key}") not found in solution configuration')

    metadata_config = ns_config.get('inferenceItemMetadata')
    if not metadata_config:
        raise Exception(f'Namespace ("{namespace}") is missing inferenceItemMetadata configuration')

    type = metadata_config.get('type')
    if type == 'dynamodb':
        table_name, timestamp = bulk_write_ddb_table(bucket, key, namespace)
        purge_obsolete_ddb_items(table_name, timestamp)
    elif type == 'localdb':
        build_dbm_file(bucket, key, namespace)

def build_dbm_file(bucket: str, key: str, namespace: str):
    logger.info('Downloading object from S3')
    response = s3.get_object(Bucket = bucket, Key = key)

    if key.endswith('.gz') or key.endswith('.gzip'):
        stream = gzip.GzipFile(None, 'rb', fileobj = response['Body'])
    else:
        stream = StreamingBodyIO(response['Body'])

    lines_read = 0

    logger.info('Building local DBM file')
    with dbm.open(f'/tmp/{LOCAL_DB_FILENAME}', 'c') as db:
        reader = jsonlines.Reader(TextIOWrapper(stream))
        for item in reader:
            lines_read += 1
            if not primary_key_name in item:
                raise KeyError(f'Item ({lines_read}) is missing required field "{primary_key_name}"')

            id = item.pop(primary_key_name)
            db[id] = json.dumps(item, default=str)

    logger.info('Gzipping local DBM file')
    with open(f'/tmp/{LOCAL_DB_FILENAME}', 'rb') as src, gzip.open(f'/tmp/{LOCAL_DB_GZIP_FILENAME}', 'wb') as dst:
        dst.writelines(src)

    output_key = f'localdbs/{namespace}/{LOCAL_DB_GZIP_FILENAME}'

    logger.info('Uploading DBM file to S3')
    response = s3.upload_file(f'/tmp/{LOCAL_DB_GZIP_FILENAME}', bucket, output_key)

def bulk_write_ddb_table(bucket: str, key: str, namespace: str) -> Tuple[str, str]:
    table_name = table_name_prefix + namespace

    logger.info('Downloading object from S3')
    response = s3.get_object(Bucket = bucket, Key = key)

    # Use the last modified date from the file as each record's version/timestamp in the metadata table.
    last_modified = response['LastModified']
    timestamp = '{:%Y-%m-%dT%H:%M:%S}.{:03d}'.format(last_modified, int(last_modified.microsecond/1000))

    if key.endswith('.gz') or key.endswith('.gzip'):
        stream = gzip.GzipFile(None, 'rb', fileobj = response['Body'])
    else:
        stream = StreamingBodyIO(response['Body'])

    logger.info('Loading items into table %s', table_name)
    table = dynamodb.Table(table_name)

    lines_read = 0

    with table.batch_writer() as batch:
        reader = jsonlines.Reader(TextIOWrapper(stream))

        for item in reader:
            lines_read += 1
            if not primary_key_name in item:
                raise KeyError(f'Item ({lines_read}) is missing required field "{primary_key_name}"')

            attribs = copy.copy(item)
            attribs.pop(primary_key_name)
            ddb_item = {
                primary_key_name: item[primary_key_name],
                'version': timestamp,
                'put_via': 'bulk',
                'attributes': attribs
            }
            batch.put_item(Item=json.loads(json.dumps(ddb_item), parse_float=Decimal))

    logger.info('Items loaded: %d', lines_read)

    return table_name, timestamp

@tracer.capture_method
def purge_obsolete_ddb_items(table_name: str, timestamp: str):
    logger.info('Purging items from table with a version prior to %s', timestamp)
    table = dynamodb.Table(table_name)

    scan_kwargs = {
        'FilterExpression': Attr('version').lt(timestamp),
        'ProjectionExpression': primary_key_name
    }

    with table.batch_writer() as batch:
        deleted = 0
        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs['ExclusiveStartKey'] = start_key
            response = table.scan(**scan_kwargs)
            for item in response.get('Items', []):
                batch.delete_item(Key = item)
                deleted += 1

            start_key = response.get('LastEvaluatedKey', None)
            done = start_key is None

        logger.info('Purged %d items with a version prior to %s', deleted, timestamp)

@tracer.capture_method
def process_event_record(record):
    bucket = record['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(record['s3']['object']['key'])

    # Key format should be "import/[namespace]/file.jsonl[.gz|.gzip]"
    path_bits = key.split('/')

    if path_bits[0] != 'import':
        raise Exception('Key does not start with expected folder ("import/"); ignoring event record')

    if len(path_bits) < 3:
        logger.warn('Key does not conform to expected path (not enough elements in path); ignoring event record')
        return

    if record['s3']['object']['size'] == 0:
        logger.warn('Object is empty (size is zero); ignoring event record')
        return

    namespace = path_bits[1]
    bulk_load_datastore(bucket, key, namespace)

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event, _):
    if event.get('Records'):
        for record in event['Records']:
            if record.get('s3'):
                try:
                    process_event_record(record)
                except Exception as e:
                    logger.exception(e)
            else:
                logger.error('Event Record does not appear to be for an S3 event; missing "s3" details')
    else:
        logger.error('Invalid/unsupported event; missing "Records"')