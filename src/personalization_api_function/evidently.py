# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json

from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from http import HTTPStatus
from aws_lambda_powertools import Logger, Tracer
from personalization_config import PersonalizationConfig
from personalization_error import ConfigError, ValidationError
from background_tasks import BackgroundTasks

tracer = Tracer()
logger = Logger(child=True)

evidently = boto3.client('evidently')

EXPOSURE_VALUE = 0.0000001
CONVERSION_VALUE = 1.0000001

def _set_simple_json_path(path: str, value: Union[str, float], variation: Dict):
    """ Sets a value in a target dictionary based on a simple dot-notation JSON path """
    path_elements = path.split('.')

    context = variation
    for element in path_elements[:-1]:
        if not context.get(element):
            context[element] = {}
            context = context[element]
        else:
            context = context.get(element)

    context[path_elements[-1]] = value

def _create_event_data(metric_config: Dict[str,str], entity_id: str, value: float) -> Dict:
    event = {}
    _set_simple_json_path(metric_config['entityIdKey'], entity_id, event)
    _set_simple_json_path(metric_config['valueKey'], value, event)
    return event

def create_exposure_event(metric_config: Dict, entity_id: str) -> Dict:
    return {
        'type': 'aws.evidently.custom',
        'data': json.dumps(_create_event_data(metric_config, entity_id, EXPOSURE_VALUE)),
        'timestamp': datetime.now()
    }

def create_conversion_event(metric_config: Dict, entity_id: str, value: float = CONVERSION_VALUE) -> Dict:
    return {
        'type': 'aws.evidently.custom',
        'data': json.dumps(_create_event_data(metric_config, entity_id, value)),
        'timestamp': datetime.now()
    }

@tracer.capture_method
def record_evidently_events(project: str, events: List[Dict]):
    response = evidently.put_project_events(
        project = project,
        events = events
    )

    logger.debug(response)

@tracer.capture_method
def evidently_evaluate_feature(feature: str, experiment_config: Dict, variations: Dict, user_id: str, background: BackgroundTasks) -> Tuple[Dict,Optional[Dict]]:
    try:
        response = evidently.evaluate_feature(
            entityId = user_id,
            project = experiment_config['project'],
            feature = feature
        )

        variation = None
        value = None

        if response['value'].get('stringValue'):
            variation_id = response['value']['stringValue']
            variation = variations.get(variation_id)
            if not variation and variation_id.isdigit():
                try:
                    variation_id, variation = list(variations.items())[int(variation_id)]
                except IndexError:
                    raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'NoMatchedTarget', f'Evaluated feature variation value ({variation_id}) from Evidently is out of index range for configured variations')

            if not variation:
                raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'NoMatchedTarget', f'Evaluated feature variation value ("{variation_id}") from Evidently does not match a configured variation')

        elif response['value'].get('longValue'):
            idx = response['value']['longValue']
            try:
                variation_id, variation = list(variations.items())[int(idx)]
            except IndexError:
                raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'NoMatchedTarget', f'Evaluated feature variation value ({value}) from Evidently is out of index range for configured variations')
        else:
            raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'UnsupportedEvaluationType', f'Evaluated feature variation value type from Evidently is not supported')

        logger.info('Evidently feature "%s" mapped to variation "%s" via Evidently variation "%s"', feature, variation_id, response.get('variation'))

        experiment = None

        if response['reason'] == 'EXPERIMENT_RULE_MATCH':
            experiment = {
                'type': 'evidently',
                'feature': feature,
                'details': json.loads(response['details'])
            }

            if experiment_config.get('metrics'):
                events = []
                for metric_name, metric_config in experiment_config['metrics'].items():
                    if metric_config.get('trackExposures', True):
                        logger.info('Recording variation exposure for Evidently variation "%s" of experiment "%s" for metric "%s"', response.get('variation'), response.get('details'), metric_name)
                        events.append(create_exposure_event(metric_config, user_id))
                    else:
                        logger.info('Variation exposures for Evidently variation "%s" of experiment "%s" for metric "%s" are DISABLED; skipping', response.get('variation'), response.get('details'), metric_name)

                background.submit(record_evidently_events, experiment_config['project'], events)
            else:
                logger.warning('Evidently conversion metric details not defined in recommender configuration; unable to record exposure event for experiment "%s"', response.get('details'))

        return variation, experiment

    except evidently.exceptions.ResourceNotFoundException:
        logger.warning('Evidently project ("%s") and/or feature ("%s") do not exist; defaulting to first configured variation', experiment['project'], feature)
        return next(iter(variations.items()))[1], None

@tracer.capture_method
def process_conversions(namespace: str, namespace_config: Dict, api_event: Dict, config: PersonalizationConfig):
    event_body = api_event.json_body

    conversions = event_body.get('experimentConversions')
    if not conversions:
        logger.debug('API event does not include any experiment conversions')
        return

    if not isinstance(conversions, list):
        raise ValidationError('InvalidExperimentConversions', 'Must be a list')

    user_id = event_body.get('userId')
    if not user_id:
        raise ValidationError('UserIdRequired', 'userId is a required field in payload object')

    evidently_events = {}

    # Make a first pass over the conversions to validate them.
    for idx, conversion in enumerate(conversions):
        recommender = conversion.get('recommender')
        if not recommender:
            raise ValidationError('InvalidExperimentConversions', f'Experiment conversion at index {idx} is missing recommender')

        recommender_config = config.get_recommender_config(namespace, recommender)
        if not recommender_config:
            raise ValidationError('InvalidRecommender', f'Experiment conversion at index {idx} is referencing a recommender that does not exist')

        experiments = recommender_config.get('experiments')
        if not experiments:
            raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'ExperimentsNotFound', f'"experiments" not defined for recommender ("{recommender}")')

        feature = conversion.get('feature')
        if feature:
            experiment = experiments.get(feature)
            if not experiment:
                raise ValidationError('InvalidExperimentFeature', f'Experiment for feature {feature} for conversion at index {idx} is referencing a feature that is not in the configuration')
        elif len(experiments) == 1:
            experiment = next(iter(experiments.items()))[1]
        else:
            raise ValidationError('InvalidExperimentFeature', f'Experiment has multiple features configured but the feature name was not specified at conversion index {idx}')

        if experiment.get('method') == 'evidently':
            if not experiment.get('project'):
                raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'InvalidEvidentlyProject', 'Evidently project is missing from the configuration')

            metric = conversion.get('metric')
            if metric:
                metric_config = experiment.get('metrics').get(metric)
                if not metric_config:
                    raise ValidationError('InvalidExperimentMetric', f'Experiment for feature {feature} for conversion at index {idx} is referencing a metric name {metric} that is not in the configuration')
            elif len(experiment.get('metrics')) == 1:
                metric_config = next(iter(experiment.get('metrics').items()))[1]
            else:
                raise ValidationError('InvalidExperimentMetric', f'Experiment for feature {feature} for conversion at index {idx} is does not specify a metric name')

            event = create_conversion_event(metric_config, user_id, conversion.get('value', CONVERSION_VALUE))
            evidently_events.setdefault(experiment['project'], []).append(event)
        else:
            raise ConfigError(HTTPStatus.INTERNAL_SERVER_ERROR, 'UnsupportedEvaluationMethod', 'Variation evaluation method is not configured/supported')

    # Next send the events for each project to Evidently
    for item in evidently_events.items():
        project = item[0]
        project_events = item[1]

        record_evidently_events(project, project_events)
