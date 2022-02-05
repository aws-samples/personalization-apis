#!/bin/sh

# Edge auth resources are optional depending on the configuration of the Personalization API deployment.
#
# When to deploy edge auth:
#   - You are using OAuth2 with Cognito to authenticate your API calls.
# Why deploy edge auth:
#   - To maximize the cache hit rate and reduce latency of serving cached resources.
# Requirements:
#   - Amazon Cognito must be used as the JWT token provider for API authentication.
#   - Edge auth resources must be deployed in the us-east-1 region. This is a Lambda@Edge requirement.
#     However, you can deploy your Personalization APIs in any region where the dependent AWS services
#     (i.e. Personalize) are available.

sam build --use-container --cached --template-file template-edge.yaml && sam deploy --region us-east-1 --config-file samconfig-edge.toml --guided