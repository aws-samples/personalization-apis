# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Error abstractions
"""

import json
from http import HTTPStatus
from botocore.exceptions import ClientError

class PersonalizationError(Exception):
    def __init__(
        self,
        type: str,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__(error_message)
        self.type = type
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message
        self.sdk_status_code = sdk_status_code

    @classmethod
    def from_client_error(cls, e: ClientError):
        return cls(HTTPStatus.INTERNAL_SERVER_ERROR, e.response['Error']['Code'], e.response['Error']['Message'], e.response['ResponseMetadata']['HTTPStatusCode'])

class ValidationError(PersonalizationError):
    def __init__(
        self,
        error_code: str,
        error_message: str,
    ):
        super().__init__('Validation', HTTPStatus.BAD_REQUEST, error_code, error_message)

class JSONDecodeValidationError(ValidationError):
    def __init__(
        self,
        error_code: str,
        error_message: str
    ):
        super().__init__(error_code, error_message)

    @classmethod
    def from_json_decoder_error(cls, error_code: str, e: json.decoder.JSONDecodeError):
        return cls(error_code, f"{e.msg}: line {e.lineno} column {e.colno} (char {e.pos})")

class ConfigError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('Configuration', status_code, error_code, error_message, sdk_status_code)

class PersonalizeError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('Personalize', status_code, error_code, error_message, sdk_status_code)

    @classmethod
    def from_client_error(cls, e: ClientError):
        error_code = e.response['Error']['Code']
        if error_code == 'ThrottlingException':
            return cls(HTTPStatus.TOO_MANY_REQUESTS, error_code, e.response['Error']['Message'], e.response['ResponseMetadata']['HTTPStatusCode'])

        return cls(HTTPStatus.INTERNAL_SERVER_ERROR, error_code, e.response['Error']['Message'], e.response['ResponseMetadata']['HTTPStatusCode'])

class DynamoDbError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('DynamoDB', status_code, error_code, error_message, sdk_status_code)

class EvidentlyError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('Evidently', status_code, error_code, error_message, sdk_status_code)

class LambdaError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('Function', status_code, error_code, error_message, sdk_status_code)

class SageMakerError(PersonalizationError):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        error_message: str,
        sdk_status_code: int = None
    ):
        super().__init__('SageMaker', status_code, error_code, error_message, sdk_status_code)
