#!/bin/bash

# Utility script to deploy application to the Serverless Application Repository.

set -e

# Bucket must have policy to allow SAR access.
# See https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-template-publishing-applications.html
BUCKET=$1
REGION=$2

if [ "$BUCKET" == "" ] || [ "$REGION" == "" ]; then
    echo "Usage: $0 BUCKET REGION"
    echo "  where BUCKET is the S3 bucket to deploy packaged resources for SAR and REGION is the AWS region where to publish the application"
    exit 1
fi

echo "Building application"
sam build --use-container --cached

cd .aws-sam/build
echo "Packaging application"
sam package --template-file template.yaml --output-template-file packaged.yaml --s3-bucket $BUCKET
echo "Publishing application to the SAR"
sam publish --template packaged.yaml --region $REGION
cd -