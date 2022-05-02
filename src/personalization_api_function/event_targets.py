# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json

from copy import copy
from typing import Dict
from datetime import datetime
from http import HTTPStatus
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, Future, wait
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from personalization_error import ConfigError, PersonalizeError
from auto_values import resolve_auto_values

logger = Logger(child=True)
tracer = Tracer()
metrics = Metrics()

PERSONALIZE_EVENT_TRACKER = 'personalize-event-tracker'
KINESIS_STREAM = 'kinesis-stream'
KINESIS_FIREHOSE = 'kinesis-firehose'

class EventTarget(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def put_events(self, config, api_event):
        pass

    def apply_auto_context(self, namespace_config: Dict, event_body: Dict, headers: Dict[str,str]):
        auto_context = resolve_auto_values(namespace_config.get('autoContext'), headers)
        if auto_context:
            for event in event_body.get('eventList'):
                if event.get('properties'):
                    properties = json.loads(event.get('properties'))
                else:
                    properties = {}

                for field, resolved in auto_context.items():
                    if not field in properties:
                        if resolved.get('type') == 'string':
                            properties[field] = '|'.join(resolved['values'])
                        else:
                            properties[field] = str(resolved['values'][0])

                event['properties'] = json.dumps(properties)

class PersonalizeEventTracker(EventTarget):
    _personalize_events = boto3.client('personalize-events')

    def __init__(self, trackingId: str):
        self.trackingId = trackingId

    @tracer.capture_method
    def put_events(self, namespace: str, namespace_config: Dict, api_event: Dict, event_body: Dict):
        if event_body.get('experimentConversions'):
            # The "experimentConversion" key is a custom extension supported only by this solution.
            # We need to remove this key before calling PutEvents for Personalize. Otherwise the API
            # call will fail for parameter validation. Make a copy of the event before removing the
            # key so that other event targets will still process the complete original event.
            event_body = copy(event_body)
            del event_body['experimentConversions']

        event_body['trackingId'] = self.trackingId

        self.apply_auto_context(namespace_config, event_body, api_event.headers)

        logger.debug('Calling put_events on Personalize event tracker %s', self.trackingId)

        try:
            response = PersonalizeEventTracker._personalize_events.put_events(**event_body)
            logger.debug(response)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                metrics.add_dimension(name="TrackingId", value=self.trackingId)
                metrics.add_metric(name="PersonalizeEventTrackerThrottle", unit=MetricUnit.Count, value=1)
            raise PersonalizeError.from_client_error(e)

class KinesisStream(EventTarget):
    _kinesis = boto3.client('kinesis')

    def __init__(self, stream_name: str):
        self.stream_name = stream_name

    @tracer.capture_method
    def put_events(self, namespace: str, namespace_config: Dict, api_event: Dict, event_body: Dict):
        self.apply_auto_context(namespace_config, event_body, api_event.headers)

        data = {
            'namespace': namespace,
            'path': api_event.path,
            'headers': api_event.headers,
            'queryStringParameters': api_event.query_string_parameters,
            'body': event_body
        }

        logger.debug('Calling put_record on stream %s', self.stream_name)
        response = KinesisStream._kinesis.put_record(
            StreamName = self.stream_name,
            Data = json.dumps(data),
            PartitionKey = event_body['sessionId']
        )

        logger.debug(response)

class KinesisFirehose(EventTarget):
    _firehose = boto3.client('firehose')

    def __init__(self, stream_name: str):
        self.stream_name = stream_name

    @tracer.capture_method
    def put_events(self, namespace: str, namespace_config: Dict, api_event: Dict, event_body: Dict):
        self.apply_auto_context(namespace_config, event_body, api_event.headers)

        data = {
            'namespace': namespace,
            'path': api_event.path,
            'headers': api_event.headers,
            'queryStringParameters': api_event.query_string_parameters,
            'body': event_body
        }

        logger.debug('Calling put_record on Firehose %s', self.stream_name)
        response = KinesisFirehose._firehose.put_record(
            DeliveryStreamName = self.stream_name,
            Record = {
                'Data': json.dumps(data)
            }
        )

        logger.debug(response)

@tracer.capture_method
def process_targets(namespace: str, namespace_config: Dict, api_event: Dict):
    config_targets = namespace_config.get('eventTargets')
    if not config_targets:
        raise ConfigError(HTTPStatus.NOT_FOUND, 'NamespaceEventTargetsNotFound', 'No event targets are defined for this namespace path')

    event_body = api_event.json_body

    # Set sentAt if omitted from any of the events.
    if event_body.get('eventList'):
        for event in event_body['eventList']:
            if not 'sentAt' in event:
                event['sentAt'] = int(datetime.now().timestamp())

    targets: EventTarget = []

    for config_target in config_targets:
        type = config_target.get('type')

        if type == PERSONALIZE_EVENT_TRACKER:
            if event_body.get('eventList'):
                targets.append(PersonalizeEventTracker(config_target['trackingId']))
            else:
                logger.warning('API event does not have any events ("eventList" missing or empty); skipping Personalize event tracker')
        elif type == KINESIS_STREAM:
            targets.append(KinesisStream(stream_name = config_target['streamName']))
        elif type == KINESIS_FIREHOSE:
            targets.append(KinesisFirehose(stream_name = config_target['streamName']))
        else:
            raise ConfigError(f'Event target type {type} is unsupported')

    if len(targets) == 1:
        logger.debug('Just one event target %s; executing synchronously', config_targets[0])
        targets[0].put_events(namespace, namespace_config, api_event, event_body)
    else:
        logger.debug('%s event targets; executing concurrently', len(targets))
        with ThreadPoolExecutor() as executor:
            futures: Future = []
            for target in targets:
                futures.append(executor.submit(target.put_events, namespace, namespace_config, api_event, event_body))

            logger.debug('Waiting for event targets to finish processing')
            wait(futures)
            logger.debug('All event targets completed processing')

            # Propagate any exceptions
            for future in futures:
                future.result()