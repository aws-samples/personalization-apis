from pytest import fixture
from unittest.mock import MagicMock

from layer.personalization_config import AppConfigPersonalizationConfig

@fixture
def config_no_version():
    return {
        "namespaces": {}
    }

@fixture
def config_with_version():
    return {
        "version": "1",
        "namespaces": {}
    }

@fixture
def config_cache_inheritance():
    return {
        "cacheControl": {
            "userSpecified": {
                "maxAge": 10,
                "directives": "private"
            },
        },
        "namespaces": {
            "ns-inherit-root": {
                "recommenders": {
                    "recommend-items": {
                        "recommended-for-you": {
                        }
                    }
                }
            },
            "ns-inherit-1": {
                "cacheControl": {
                    "userSpecified": {
                        "maxAge": 20,
                        "directives": "private"
                    },
                },
                "recommenders": {
                    "recommend-items": {
                        "recommended-for-you": {
                            "cacheControl": {
                                "userSpecified": {
                                    "maxAge": 30,
                                    "directives": "private"
                                }
                            }
                        }
                    },
                    "related-items": {
                        "similar": {
                            "cacheControl": {
                                "userSpecified": {
                                    "maxAge": 40,
                                    "directives": "private"
                                }
                            }
                        }
                    }
                }
            },
            "ns-inherit-2": {
                "recommenders": {
                    "recommend-items": {
                        "recommended-for-you": {
                            "cacheControl": {
                                "userSpecified": {
                                    "maxAge": 60,
                                    "directives": "private"
                                }
                            }
                        }
                    },
                    "related-items": {
                        "similar": {
                        }
                    }
                }
            }
        }
    }

@fixture
def obj():
    obj = AppConfigPersonalizationConfig.__new__(AppConfigPersonalizationConfig)
    return obj

def test_no_version(obj, config_no_version):
    obj.get_config = MagicMock(return_value = config_no_version)
    assert obj.get_version() is None

def test_with_version(obj, config_with_version):
    obj.get_config = MagicMock(return_value = config_with_version)
    assert obj.get_version() == '1'

def test_cache_inheritance(obj, config_cache_inheritance):
    obj.get_config = MagicMock(return_value = config_cache_inheritance)

    ns_config = obj.get_namespace_config('ns-inherit-root')
    assert ns_config['cacheControl']['userSpecified']['maxAge'] == 10

    rec_config = obj.get_recommender_config('ns-inherit-root', 'recommended-for-you', 'recommend-items')
    assert rec_config['cacheControl']['userSpecified']['maxAge'] == 10

    ns_config = obj.get_namespace_config('ns-inherit-1')
    assert ns_config['cacheControl']['userSpecified']['maxAge'] == 20

    rec_config = obj.get_recommender_config('ns-inherit-1', 'recommended-for-you', 'recommend-items')
    assert rec_config['cacheControl']['userSpecified']['maxAge'] == 30
    rec_config = obj.get_recommender_config('ns-inherit-1', 'similar', 'related-items')
    assert rec_config['cacheControl']['userSpecified']['maxAge'] == 40

    ns_config = obj.get_namespace_config('ns-inherit-2')
    assert ns_config['cacheControl']['userSpecified']['maxAge'] == 10

    rec_config = obj.get_recommender_config('ns-inherit-2', 'recommended-for-you', 'recommend-items')
    assert rec_config['cacheControl']['userSpecified']['maxAge'] == 60
    rec_config = obj.get_recommender_config('ns-inherit-2', 'similar', 'related-items')
    assert rec_config['cacheControl']['userSpecified']['maxAge'] == 10
