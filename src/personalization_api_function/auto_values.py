# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pytz

from datetime import datetime
from typing import Any, Dict, List
from aws_lambda_powertools import Logger, Tracer

tracer = Tracer()
logger = Logger(child=True)

def get_season(date: datetime, latitude: float = None) -> int:
    """ Determines season index (0-3) based on datetime and latitude

    Season indeces:
        0 = Spring
        1 = Summer
        2 = Fall
        3 = Winter
    Latitude is used to determine the Northern/Southern hemisphere
    """
    md = date.month * 100 + date.day

    if ((md > 320) and (md < 621)):
        s = 0 # Spring
    elif ((md > 620) and (md < 923)):
        s = 1 # Summer
    elif ((md > 922) and (md < 1223)):
        s = 2 # Fall
    else:
        s = 3 # Winter

    if latitude and latitude < 0:
        if s < 2:
            s += 2
        else:
            s -= 2

    return s

def resolve_auto_values(context_config: Dict, headers: Dict[str,str]) -> Dict[str,Dict[str,Any]]:
    """ Resolves automated context based on the specified config and headers

    Returns a dictionary where the keys are the field names and the values are
    a dict with "values" and "type" fields.
    """
    resolved_values = {}

    if not context_config:
        return resolved_values

    if headers.get('cloudfront-viewer-time-zone'):
        tz = pytz.timezone(headers.get('cloudfront-viewer-time-zone'))
        now = tz.localize(datetime.now())
    else:
        now = datetime.now()

    for field, auto_ctx in context_config.items():
        values = set()

        eval_all = auto_ctx.get('evaluateAll', False)

        for rule in auto_ctx.get('rules'):
            resolved = None

            if rule.get('type') == 'header-value':
                header_value = headers.get(rule.get('header'))
                resolved = _resolve(rule, header_value)
            elif rule.get('type') == 'hour-of-day':
                resolved = _resolve(rule, now.hour)
            elif rule.get('type') == 'day-of-week':
                resolved = _resolve(rule, now.weekday())
            elif rule.get('type') == 'season-of-year':
                season = get_season(now, headers.get('cloudfront-viewer-latitude'))
                resolved = _resolve(rule, season)

            if resolved:
                values.add(resolved)
                if not eval_all:
                    break

        if len(values) > 0:
            resolved_values[field] = {
                'values': list(values)
            }
            if auto_ctx.get('type'):
                resolved_values[field]['type'] = auto_ctx['type']
        elif auto_ctx.get('default'):
            resolved['values'] = [ auto_ctx['default'] ]
            if auto_ctx.get('type'):
                resolved_values[field]['type'] = auto_ctx['type']

    return resolved_values

def _resolve(rule: Dict, value: Any):
    resolved_value = None

    if value is not None:
        if rule.get('valueMappings'):
            for value_mapping in rule.get('valueMappings'):
                operator = value_mapping['operator']
                mapping_value = value_mapping['value']
                map_to = value_mapping['mapTo']

                if operator == 'equals' and value == mapping_value:
                    resolved_value = map_to
                elif operator == 'less-than' and value < mapping_value:
                    resolved_value = map_to
                elif operator == 'greater-than' and value > mapping_value:
                    resolved_value = map_to
                elif operator == 'contains' and str(mapping_value) in str(value):
                    resolved_value = map_to
                elif operator == 'start-with' and str(value).startswith(str(mapping_value)):
                    resolved_value = map_to
                elif operator == 'ends-with' and str(value).endswith(str(mapping_value)):
                    resolved_value = map_to

                if resolved_value:
                    break
        else:
            resolved_value = value

    return resolved_value
