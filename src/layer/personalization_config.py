# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import urllib.request
import copy

from typing import Any, Dict
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from aws_lambda_powertools import Logger, Tracer

logger = Logger(child=True)
tracer = Tracer()

LOCAL_DB_FILENAME = 'p13n-item-metadata.db'
LOCAL_DB_GZIP_FILENAME = LOCAL_DB_FILENAME + '.gz'

class PersonalizationConfig(ABC):
    def __init__(self):
        pass

    def get_namespace_config(self, namespace_path: str) -> Dict:
        config = None
        root_config = self.get_config()
        if root_config:
            namespaces = root_config.get('namespaces')
            if namespaces:
                config = self.inherit_config(root_config, namespaces.get(namespace_path))

        return config

    def get_recommender_config(self, namespace_path: str, recommender_path: str, api_action: str = None) -> Dict:
        config = None
        ns_config = self.get_namespace_config(namespace_path)
        if ns_config:
            recommenders = ns_config.get('recommenders')
            if recommenders:
                if api_action:
                    config = recommenders.get(api_action)
                    if config:
                        config = self.inherit_config(ns_config, config.get(recommender_path))
                else:
                    for action_config in recommenders.values():
                        if action_config.get(recommender_path):
                            config = action_config.get[recommender_path]

        return config

    def get_version(self, default: str = None) -> str:
        return self.get_config().get('version', default)

    def inherit_config(self, parent: Dict, config: Dict) -> Dict:
        if parent is not None and config is not None:
            inherited = ['autoContext', 'filters', 'cacheControl', 'inferenceItemMetadata']
            for inherit in inherited:
                if config.get(inherit) is None and parent.get(inherit) is not None:
                    config[inherit] = copy.copy(parent.get(inherit))

        return config

    @abstractmethod
    def get_config(self, max_age: int = 60) -> Dict:
        pass

    @staticmethod
    def get_instance(type: str = 'AppConfig') -> Any:
        """ Creates a config based on the type """
        if type != 'AppConfig':
            raise ValueError('Invalid personalization API config type')
        return AppConfigPersonalizationConfig()

class AppConfigPersonalizationConfig(PersonalizationConfig):
    def __init__(self):
        super().__init__()
        self.config = None
        self.ttl = 0

    def get_config(self, max_age: int = 10) -> Dict:
        if self.config and self.ttl > datetime.now():
            return self.config

        return self._get_from_app_config(max_age)

    @tracer.capture_method(capture_response=False)
    def _get_from_app_config(self, max_age: int = 10) -> Dict:
        logger.debug('Fetching configuration from AppConfig Lambda extension')

        url = f'http://localhost:2772{os.environ["AWS_APPCONFIG_EXTENSION_PREFETCH_LIST"]}'
        resp = urllib.request.urlopen(url).read()
        self.ttl = datetime.now() + timedelta(seconds=max_age)
        self.config = json.loads(resp) if resp else {}
        return self.config
