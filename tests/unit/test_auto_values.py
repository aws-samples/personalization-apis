# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from datetime import datetime
from pytest import fixture
from unittest import mock

from personalization_api_function.auto_values import get_season, resolve_auto_values

@fixture
def headers_desktop_only():
    return {
        "cloudfront-is-desktop-viewer": "true",
        "cloudfront-is-mobile-viewer": "false",
        "cloudfront-is-smarttv-viewer": "false",
        "cloudfront-is-tablet-viewer": "false",
    }

@fixture
def headers_mobile_and_tablet():
    return {
        "cloudfront-is-desktop-viewer": "false",
        "cloudfront-is-mobile-viewer": "true",
        "cloudfront-is-smarttv-viewer": "false",
        "cloudfront-is-tablet-viewer": "true",
    }

@fixture
def headers_location():
    return {
        "cloudfront-viewer-city": "San Francisco",
        "cloudfront-viewer-country-region": "CA",
        "cloudfront-viewer-latitude": "38.45490",
        "cloudfront-viewer-longitude": "-122.25640",
        "cloudfront-viewer-metro-code": "807"
    }

@fixture
def auto_context_device_type():
    return {
        "autoContext": {
            "deviceType": {
                "type": "string",
                "default": "Desktop",
                "evaluateAll": True,
                "rules": [
                    {
                        "type": "header-value",
                        "header": "cloudfront-is-desktop-viewer",
                        "valueMappings": [
                            {
                                "operator": "equals",
                                "value": "true",
                                "mapTo": "Desktop"
                            }
                        ]
                    },
                    {
                        "type": "header-value",
                        "header": "cloudfront-is-mobile-viewer",
                        "valueMappings": [
                            {
                                "operator": "equals",
                                "value": "true",
                                "mapTo": "Phone"
                            }
                        ]
                    },
                    {
                        "type": "header-value",
                        "header": "cloudfront-is-smarttv-viewer",
                        "valueMappings": [
                            {
                                "operator": "equals",
                                "value": "true",
                                "mapTo": "TV"
                            }
                        ]
                    },
                    {
                        "type": "header-value",
                        "header": "cloudfront-is-tablet-viewer",
                        "valueMappings": [
                            {
                                "operator": "equals",
                                "value": "true",
                                "mapTo": "Tablet"
                            }
                        ]
                    }
                ]
            }
        }
    }

@fixture
def auto_context_location():
    return {
        "autoContext": {
            "city": {
                "type": "string",
                "rules": [
                    {
                        "type": "header-value",
                        "header": "cloudfront-viewer-city"
                    }
                ]
            },
            "region": {
                "type": "string",
                "rules": [
                    {
                        "type": "header-value",
                        "header": "cloudfront-viewer-country-region"
                    }
                ]
            },
            "metroCode": {
                "type": "string",
                "rules": [
                    {
                        "type": "header-value",
                        "header": "cloudfront-viewer-metro-code"
                    }
                ]
            }
        }
    }

@fixture
def auto_context_time_of_day():
    return {
        "autoContext": {
            "timeOfDay": {
                "type": "string",
                "evaluateAll": False,
                "rules": [
                    {
                        "type": "hour-of-day",
                        "valueMappings": [
                            {
                                "operator": "less-than",
                                "value": 4,
                                "mapTo": "Night"
                            },
                            {
                                "operator": "less-than",
                                "value": 11,
                                "mapTo": "Morning"
                            },
                            {
                                "operator": "less-than",
                                "value": 18,
                                "mapTo": "Afternoon"
                            },
                            {
                                "operator": "less-than",
                                "value": 22,
                                "mapTo": "Evening"
                            },
                            {
                                "operator": "greater-than",
                                "value": 21,
                                "mapTo": "Night"
                            }
                        ]
                    }
                ]
            }
        }
    }

@fixture
def auto_context_day_of_week():
    return {
        "autoContext": {
            "dayOfWeek": {
                "type": "string",
                "evaluateAll": False,
                "rules": [
                    {
                        "type": "day-of-week",
                        "valueMappings": [
                            {
                                "operator": "equals",
                                "value": 0,
                                "mapTo": "Monday"
                            },
                            {
                                "operator": "equals",
                                "value": 1,
                                "mapTo": "Tuesday"
                            },
                            {
                                "operator": "equals",
                                "value": 2,
                                "mapTo": "Wednesday"
                            },
                            {
                                "operator": "equals",
                                "value": 3,
                                "mapTo": "Thursday"
                            },
                            {
                                "operator": "equals",
                                "value": 4,
                                "mapTo": "Friday"
                            },
                            {
                                "operator": "equals",
                                "value": 5,
                                "mapTo": "Saturday"
                            },
                            {
                                "operator": "equals",
                                "value": 6,
                                "mapTo": "Sunday"
                            }
                        ]
                    }
                ]
            }
        }
    }

def test_season_northern_hemi_spring():
    dt = datetime(2022, 4, 1)
    season = get_season(dt, 38.0)
    assert season == 0

def test_season_northern_hemi_summer():
    dt = datetime(2022, 7, 1)
    season = get_season(dt, 38.0)
    assert season == 1

def test_season_northern_hemi_fall():
    dt = datetime(2022, 10, 1)
    season = get_season(dt, 38.0)
    assert season == 2

def test_season_northern_hemi_winter():
    dt = datetime(2022, 1, 1)
    season = get_season(dt, 38.0)
    assert season == 3

def test_season_southern_hemi_spring():
    dt = datetime(2022, 4, 1)
    season = get_season(dt, -38.0)
    assert season == 2

def test_season_southern_hemi_summer():
    dt = datetime(2022, 7, 1)
    season = get_season(dt, -38.0)
    assert season == 3

def test_season_southern_hemi_fall():
    dt = datetime(2022, 10, 1)
    season = get_season(dt, -38.0)
    assert season == 0

def test_season_southern_hemi_winter():
    dt = datetime(2022, 1, 1)
    season = get_season(dt, -38.0)
    assert season == 1

def test_device_type_desktop(headers_desktop_only, auto_context_device_type):
    resolved = resolve_auto_values(auto_context_device_type['autoContext'], headers_desktop_only)

    assert resolved.get('deviceType')
    assert type(resolved['deviceType']) is dict
    assert resolved['deviceType'].get('values')
    assert len(resolved['deviceType']['values']) == 1
    assert resolved['deviceType']['values'][0] == 'Desktop'

def test_device_type_phone_and_tablet(headers_mobile_and_tablet, auto_context_device_type):
    resolved = resolve_auto_values(auto_context_device_type['autoContext'], headers_mobile_and_tablet)

    assert resolved.get('deviceType')
    assert type(resolved['deviceType']) is dict
    assert resolved['deviceType'].get('values')
    assert len(resolved['deviceType']['values']) == 2
    assert 'Phone' in resolved['deviceType']['values']
    assert 'Tablet' in resolved['deviceType']['values']

def test_location(headers_location, auto_context_location):
    resolved = resolve_auto_values(auto_context_location['autoContext'], headers_location)

    assert resolved.get('city')
    assert type(resolved['city']) is dict
    assert resolved['city'].get('values')
    assert len(resolved['city']['values']) == 1
    assert 'San Francisco' in resolved['city']['values']

    assert resolved.get('region')
    assert type(resolved['region']) is dict
    assert resolved['region'].get('values')
    assert len(resolved['region']['values']) == 1
    assert 'CA' in resolved['region']['values']

    assert resolved.get('metroCode')
    assert type(resolved['metroCode']) is dict
    assert resolved['metroCode'].get('values')
    assert len(resolved['metroCode']['values']) == 1
    assert '807' in resolved['metroCode']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_time_of_day_morning(mock_datetime, auto_context_time_of_day, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 19, 8)
    resolved = resolve_auto_values(auto_context_time_of_day['autoContext'], headers_location)

    assert resolved.get('timeOfDay')
    assert type(resolved['timeOfDay']) is dict
    assert resolved['timeOfDay'].get('values')
    assert len(resolved['timeOfDay']['values']) == 1
    assert 'Morning' in resolved['timeOfDay']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_time_of_day_afternoon(mock_datetime, auto_context_time_of_day, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 19, 12)
    resolved = resolve_auto_values(auto_context_time_of_day['autoContext'], headers_location)

    assert resolved.get('timeOfDay')
    assert type(resolved['timeOfDay']) is dict
    assert resolved['timeOfDay'].get('values')
    assert len(resolved['timeOfDay']['values']) == 1
    assert 'Afternoon' in resolved['timeOfDay']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_time_of_day_evening(mock_datetime, auto_context_time_of_day, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 19, 19)
    resolved = resolve_auto_values(auto_context_time_of_day['autoContext'], headers_location)

    assert resolved.get('timeOfDay')
    assert type(resolved['timeOfDay']) is dict
    assert resolved['timeOfDay'].get('values')
    assert len(resolved['timeOfDay']['values']) == 1
    assert 'Evening' in resolved['timeOfDay']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_monday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 21)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Monday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_monday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 21)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Monday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_tuesday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 22)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Tuesday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_wednesday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 23)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Wednesday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_thursday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 24)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Thursday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_friday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 25)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Friday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_saturday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 26)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Saturday' in resolved['dayOfWeek']['values']

@mock.patch('personalization_api_function.auto_values.datetime', wraps=datetime)
def test_day_of_week_sunday(mock_datetime, auto_context_day_of_week, headers_location):
    mock_datetime.now.return_value = datetime(2022, 2, 27)
    resolved = resolve_auto_values(auto_context_day_of_week['autoContext'], headers_location)

    assert resolved.get('dayOfWeek')
    assert type(resolved['dayOfWeek']) is dict
    assert resolved['dayOfWeek'].get('values')
    assert len(resolved['dayOfWeek']['values']) == 1
    assert 'Sunday' in resolved['dayOfWeek']['values']
