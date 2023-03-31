# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

'''
This is a very simple function that provides a sample of how a custom
recommender can be implemented using a Lambda function. A real custom
recommender would make the appropriate calls to a custom model or
rule-based approach to item recommendations.

To wire up a custom recommender, add the recommender as a "lambda"
type with the Lambda function ARN like the following.

{
  "namespaces": {
    "my-namespace": {
      "recommenders": {
        "recommend-items": {
          "lambda-recs": {
            "variations": {
              "lambda-rfy": {
                "type": "lambda",
                "arn": "arn:aws:lambda:us-east-1:999999999999:function:My-Custom-Function"
              }
            }
          }
        }
      }
    }
  }
}

You will also need to modify the IAM role for the PersonalizationHttpApiFunction or
PersonalizationRestApiFunction function (PersonalizationApiExecutionRole) to add a policy
that allows "lambda:InvokeFunction" for the same function ARN in the configuration.

{
    "Action": [
        "lambda:InvokeFunction"
    ],
    "Effect": "Allow",
    "Resource": "arn:aws:lambda:us-east-1:999999999999:function:My-Custom-Function"
}
'''

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, _):
  logger.info(json.dumps(event, indent=2, default=str))

  recs_to_generate = event.get('numResults', 10)

  recs = []
  for i in range(recs_to_generate):
    recs.append({'itemId': f'item-{i+1}'})

  return { 'itemList': recs }