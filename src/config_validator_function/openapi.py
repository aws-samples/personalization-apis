# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json

from typing import Dict
from aws_lambda_powertools import Logger

logger = Logger(child=True)

OPENAPI_TEMPLATE_FILE = 'openapi_template.json'

# From template.yaml for AuthenticationScheme template parameter
AUTH_SCHEME_OAUTH2 = 'OAuth2-Cognito'
AUTH_SCHEME_API_KEY = 'ApiKey'
AUTH_SCHEME_NONE = 'None'

action_name_map = {
    "recommend-items": "Recommend Items",
    "related-items": "Related Items",
    "rerank-items": "Rerank Items"
}

class OpenApiGenerator:
    def _get_openapi_template_filename(self) -> str:
        return OPENAPI_TEMPLATE_FILE

    def _get_openapi_template(self) -> Dict:
        shell_filename = self._get_openapi_template_filename()
        logger.info('Loading openapi shell from %s', shell_filename)
        with open(shell_filename) as file:
            return json.loads(file.read())

    def generate(self, apis_config: Dict, apigw_host: str, cloudfront_host: str, auth_scheme: str) -> Dict:
        openapi = self._get_openapi_template()

        if "title" in apis_config:
            openapi["info"]["title"] = apis_config["title"]
        if "description" in apis_config:
            openapi["info"]["description"] = apis_config["description"]
        if "version" in apis_config:
            openapi["info"]["version"] = apis_config["version"]

        if cloudfront_host:
            openapi["servers"].append({ "url": cloudfront_host })
        openapi["servers"].append({ "url": apigw_host })

        if auth_scheme == AUTH_SCHEME_API_KEY:
            openapi["security"] = [ { "ApiKeyAuth": [] } ]
            openapi["components"]["securitySchemes"] = {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                }
            }
        elif auth_scheme == AUTH_SCHEME_OAUTH2:
            openapi["security"] = [ { "BearerAuth": [] } ]
            openapi["components"]["securitySchemes"] = {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }#,
                #"OAuth2Auth": {
                #    "type": "oauth2",
                #    "flows": {
                #        "authorizationCode": {
                #            "authorizationUrl": "https://mydomain.auth.us-east-1.amazoncognito.com/oauth2/authorize",
                #            "tokenUrl": "https://mydomain.auth.us-east-1.amazoncognito.com/oauth2/token",
                #            "refreshUrl": "https://mydomain.auth.us-east-1.amazoncognito.com/oauth2/token"
                #        }
                #    }
                #}
            }
        else:
            openapi.pop("security", None)

        tags = []
        paths = {}

        for ns_name, ns_value in apis_config["namespaces"].items():
            if "recommenders" in ns_value:
                for action, recs in ns_value["recommenders"].items():
                    for rec_name, rec_value in recs.items():

                        tag = { "name": f"{ns_value.get('name', ns_name)}: {action_name_map[action]}" }
                        if rec_value.get('description'):
                            tag['description'] = rec_value['description']

                        if not [t for t in tags if t.get('name') == tag["name"] ]:
                            tags.append(tag)

                        if action == "recommend-items":
                            path = f"/{action}/{ns_name}/{rec_name}/{{user_id}}"
                            paths[path] = {
                                "get": {
                                    "tags": [ tag["name"] ],
                                    "description": rec_value.get("description", f"Recommend items for a user for the {ns_name} namespace"),
                                    "parameters": [
                                        { "$ref": "#/components/parameters/userIdPath" },
                                        { "$ref": "#/components/parameters/numResults" },
                                        { "$ref": "#/components/parameters/filter" },
                                        { "$ref": "#/components/parameters/filterValues" },
                                        { "$ref": "#/components/parameters/context" },
                                        { "$ref": "#/components/parameters/decorateItems" },
                                        { "$ref": "#/components/parameters/syntheticUser" },
                                        { "$ref": "#/components/parameters/feature" }
                                    ],
                                    "responses": {
                                        "200": {
                                            "description": "Successful",
                                            "content": {
                                                "application/json": {
                                                    "schema": {
                                                        "$ref": "#/components/schemas/RecommendationResponse"
                                                    }
                                                }
                                            },
                                            "headers": {
                                                "Age": {
                                                    "schema": {
                                                        "type": "integer"
                                                    },
                                                    "description": "Contains the time in seconds the object was in a proxy cache"
                                                },
                                                "ETag": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "Cache-Control": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "HTTP caching control directive"
                                                },
                                                "Apigw-Requestid": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon API Gateway request identifier"
                                                },
                                                "X-Cache": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "X-Amz-Cf-Pop": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront POP that request/response was routed through"
                                                },
                                                "X-Amz-Cf-Id": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront identifier"
                                                },
                                                "X-Personalization-Config-Version": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Personalization APIs configuration version"
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            if auth_scheme == AUTH_SCHEME_API_KEY:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "API Key is invalid"
                                }
                            elif auth_scheme == AUTH_SCHEME_OAUTH2:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "Authorization is invalid"
                                }

                        elif action == "related-items":
                            path = f"/{action}/{ns_name}/{rec_name}/{{item_id}}"
                            paths[path] = {
                                "get": {
                                    "tags": [ tag["name"] ],
                                    "description": rec_value.get("description", f"Recommend related items for an item for the {ns_name} namespace"),
                                    "parameters": [
                                        { "$ref": "#/components/parameters/itemIdPath" },
                                        { "$ref": "#/components/parameters/userIdQuery" },
                                        { "$ref": "#/components/parameters/numResults" },
                                        { "$ref": "#/components/parameters/filter" },
                                        { "$ref": "#/components/parameters/filterValues" },
                                        { "$ref": "#/components/parameters/context" },
                                        { "$ref": "#/components/parameters/decorateItems" },
                                        { "$ref": "#/components/parameters/syntheticUser" },
                                        { "$ref": "#/components/parameters/feature" }
                                    ],
                                    "responses": {
                                        "200": {
                                            "description": "Successful",
                                            "content": {
                                                "application/json": {
                                                    "schema": {
                                                        "$ref": "#/components/schemas/RecommendationResponse"
                                                    }
                                                }
                                            },
                                            "headers": {
                                                "Age": {
                                                    "schema": {
                                                        "type": "integer"
                                                    },
                                                    "description": "Contains the time in seconds the object was in a proxy cache"
                                                },
                                                "ETag": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "Cache-Control": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "HTTP caching control directive"
                                                },
                                                "Apigw-Requestid": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon API Gateway request identifier"
                                                },
                                                "X-Cache": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "X-Amz-Cf-Pop": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront POP that request/response was routed through"
                                                },
                                                "X-Amz-Cf-Id": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront identifier"
                                                },
                                                "X-Personalization-Config-Version": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Personalization APIs configuration version"
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            if auth_scheme == AUTH_SCHEME_API_KEY:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "API Key is invalid"
                                }
                            elif auth_scheme == AUTH_SCHEME_OAUTH2:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "Authorization is invalid"
                                }

                        elif action == "rerank-items":
                            path = f"/{action}/{ns_name}/{rec_name}/{{user_id}}/{{item_ids}}"
                            paths[path] = {
                                "get": {
                                    "tags": [ tag["name"] ],
                                    "description": rec_value.get("description", f"Rerank a list of items for a user for the {ns_name} namespace"),
                                    "parameters": [
                                        { "$ref": "#/components/parameters/userIdPath" },
                                        { "$ref": "#/components/parameters/itemIdsPath" },
                                        { "$ref": "#/components/parameters/filter" },
                                        { "$ref": "#/components/parameters/filterValues" },
                                        { "$ref": "#/components/parameters/context" },
                                        { "$ref": "#/components/parameters/decorateItems" },
                                        { "$ref": "#/components/parameters/syntheticUser" },
                                        { "$ref": "#/components/parameters/feature" }
                                    ],
                                    "responses": {
                                        "200": {
                                            "description": "Successful",
                                            "content": {
                                                "application/json": {
                                                    "schema": {
                                                        "$ref": "#/components/schemas/RerankResponse"
                                                    }
                                                }
                                            },
                                            "headers": {
                                                "Age": {
                                                    "schema": {
                                                        "type": "integer"
                                                    },
                                                    "description": "Contains the time in seconds the object was in a proxy cache"
                                                },
                                                "ETag": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "Cache-Control": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "HTTP caching control directive"
                                                },
                                                "Apigw-Requestid": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon API Gateway request identifier"
                                                },
                                                "X-Cache": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Uniquely identifies the response/resource"
                                                },
                                                "X-Amz-Cf-Pop": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront POP that request/response was routed through"
                                                },
                                                "X-Amz-Cf-Id": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Amazon CloudFront identifier"
                                                },
                                                "X-Personalization-Config-Version": {
                                                    "schema": {
                                                        "type": "string"
                                                    },
                                                    "description": "Personalization APIs configuration version"
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            if auth_scheme == AUTH_SCHEME_API_KEY:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "API Key is invalid"
                                }
                            elif auth_scheme == AUTH_SCHEME_OAUTH2:
                                paths[path]["get"]["responses"]["403"] = {
                                    "description": "Authorization is invalid"
                                }

                            path = f"/{action}/{ns_name}/{rec_name}/{{user_id}}"
                            paths[path] = {
                                "post": {
                                    "tags": [ tag["name"] ],
                                    "description": rec_value.get("description", f"Rerank a list items for a user for {ns_name}"),
                                    "parameters": [
                                        { "$ref": "#/components/parameters/userIdPath" },
                                    ],
                                    "requestBody": {
                                        "description": "List of item IDs to rerank for `user_id`",
                                        "content": {
                                            "application/json": {
                                                "schema": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "string"
                                                    }
                                                }
                                            }
                                        },
                                        "required": True
                                    },
                                    "responses": {
                                        "200": {
                                            "description": "Successful",
                                            "content": {
                                                "application/json": {
                                                    "schema": {
                                                        "$ref": "#/components/schemas/RerankResponse"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            if auth_scheme == AUTH_SCHEME_API_KEY:
                                paths[path]["post"]["responses"]["403"] = {
                                    "description": "API Key is invalid"
                                }
                            elif auth_scheme == AUTH_SCHEME_OAUTH2:
                                paths[path]["post"]["responses"]["403"] = {
                                    "description": "Authorization is invalid"
                                }

            if "eventTargets" in ns_value:
                tag = { "name": f"{ns_value.get('name', ns_name)}: Events" }
                tags.append(tag)

                path = f"/events/{ns_name}"
                paths[path] = {
                    "post": {
                        "tags": [ tag["name"] ],
                        "requestBody": {
                            "description": "Send events to one or more configured event targets",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/EventsRequest"
                                    }
                                }
                            },
                            "required": True
                        },
                        "responses": {
                            "200": {
                                "description": "Successful"
                            }
                        }
                    }
                }

        openapi["tags"] = tags
        openapi["paths"] = paths

        return openapi