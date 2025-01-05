import boto3
import json
import os
from configuration import configuration

def handler(event, context):
    s3 = boto3.client('s3')
    textract = boto3.client('textract')
    # Get bucket name and file key from the event
    # bucket_name = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    bucket_name = configuration.get_parameter('BucketName')
    raw_prefix = configuration.get_parameter('RawFilesPrefix')
    processed_prefix = configuration.get_parameter('ToBeProcessedFilesPrefix')

    print(f"Raw Prefix: {raw_prefix}")
    print(f"Processed Prefix: {processed_prefix}")
    print(f"Processing file: {key} from bucket: {bucket_name}")

    # Invoking textract to analyze the file
    response = textract.analyze_document(
        Document = {
            'S3Object': {
                'Bucket': bucket_name,
                'Name': key
            }
        },
        FeatureTypes=['TABLES', 'FORMS']
    )

    # Extract text from the response
    extracted_text = []
    for block in response['Blocks']:
        if block['BlockType'] == 'LINE':
            extracted_text.append(block['Text'])

    
    # Save extracted text to the ProcessedFiles folder
    processed_key = key.replace(raw_prefix, processed_prefix).replace('.pdf', '.txt').replace('.jpg', '.txt').replace('.png', '.txt')
    print(f"Processed Key: {processed_key}")

    # Save the extracted text to the processed prefix
    s3.put_object(
        Bucket=bucket_name,
        Key=processed_key,
        Body="\n".join(extracted_text)
    )

    return {"StatusCode": 200, "body": "Text Extraction Complete!"}