#!/bin/bash

# Define stack names
SSM_STACK_NAME="SummarizationSSM"
S3_STACK_NAME="SummarizationS3"

# Define parameters
BUCKET_NAME="cs-helper"
RAW_PREFIX="RawFiles/"
PROCESSED_PREFIX="ProcessedFiles/"

# Deploy SSM Parameter Store
echo "Deploying SSM Parameter Store..."
aws cloudformation deploy \
  --stack-name $SSM_STACK_NAME \
  --template-file templates/ssm.template.yaml \
  --parameter-overrides \
    BucketName=$BUCKET_NAME \
    RawPrefix=$RAW_PREFIX \
    ProcessedPrefix=$PROCESSED_PREFIX \
  --capabilities CAPABILITY_NAMED_IAM

# Deploy S3 Bucket
echo "Deploying S3 Bucket..."
aws cloudformation deploy \
  --stack-name $S3_STACK_NAME \
  --template-file templates/s3.template.yaml \
  --parameter-overrides \
    BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_NAMED_IAM

echo "Deployment complete!"
