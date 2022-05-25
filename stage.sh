#!/bin/bash

# Staging script for copying deployment resources to an S3 bucket.
#
# Example usage:
# ./stage.sh INPUT_TEMPLATE S3_BUCKET [OPTIONAL_S3_PATH/]
#
# The INPUT_TEMPLATE is the SAM template to use as input into the build process and
# S3_BUCKET/OPTIONAL_S3_PATH is where all resources and templates will be uploaded.
# If you don't specify the OPTIONAL_S3_PATH, it will be uploaded to the root of the bucket.
#

set -e

INPUT_TEMPLATE=$1
BUCKET=$2
# Path with trailing / (if specified)
S3PATH=$3

echo "=============================================="
echo "Executing the script with following arguments:"
echo "=============================================="
echo "INPUT_TEMPLATE = ${INPUT_TEMPLATE}"
echo "BUCKET = ${BUCKET}"
echo "S3PATH = ${S3PATH}"
echo "=============================================="
########################################################################################################################################

if [ -z "$INPUT_TEMPLATE" ] || [ -z "$BUCKET" ]; then
    echo "Usage: $0 INPUT_TEMPLATE BUCKET [S3PATH]"
    echo "  where INPUT_TEMPLATE is the input template filename, BUCKET is the S3 bucket to upload resources to, and S3PATH is optional path but if specified must have a trailing '/'"
    exit 1
fi

if [ ! -f "$INPUT_TEMPLATE" ]; then
    echo "Input template file $INPUT_TEMPLATE does not exist."
fi

BUCKET_LOCATION="$(aws s3api get-bucket-location --bucket ${BUCKET}|grep ":"|cut -d\" -f4)"
if [ -z "$BUCKET_LOCATION" ]; then
    BUCKET_DOMAIN="s3.amazonaws.com"
    BUCKET_LOCATION="us-east-1"
else
    BUCKET_DOMAIN="s3-${BUCKET_LOCATION}.amazonaws.com"
fi

if [ $(uname) == "Darwin" ]; then
    USE_CONTAINER="--use-container"
else
    USE_CONTAINER=""
fi

echo "Building project artifacts"
sam build --template-file $INPUT_TEMPLATE $USE_CONTAINER

cd .aws-sam/build

echo "Packaging and uploading project artifacts to s3://${BUCKET}/${S3PATH}"
if [ "$S3PATH" == "" ]; then
    sam package --force-upload --output-template-file packaged.yaml --s3-bucket ${BUCKET}
else
    sam package --force-upload --output-template-file packaged.yaml --s3-bucket ${BUCKET} --s3-prefix ${S3PATH%/}
fi

echo "Copying packaged CloudFormation template to s3://${BUCKET}/${S3PATH}template.yaml"
aws s3 cp packaged.yaml s3://${BUCKET}/${S3PATH}template.yaml

cd -

echo "For CloudFormation: https://${BUCKET_DOMAIN}/${BUCKET}/${S3PATH}template.yaml"
echo "Launch CloudFormation stack: https://console.aws.amazon.com/cloudformation/home?region=${BUCKET_LOCATION}#/stacks/create/review?templateURL=https://${BUCKET_DOMAIN}/${BUCKET}/${S3PATH}template.yaml&stackName=personalization-apis"