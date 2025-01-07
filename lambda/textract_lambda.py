import boto3
import json
from configuration import configuration

def extract_text_by_columns(textract_response):
    """
    Process AWS Textract response to handle two-column documents by processing
    the left column entirely before the right column.
    """
    blocks = textract_response.get("Blocks", [])
    text_blocks = [block for block in blocks if block["BlockType"] == "LINE"]

    # Separate blocks into columns based on their horizontal position
    left_column = []
    right_column = []

    for block in text_blocks:
        if block["Geometry"]["BoundingBox"]["Left"] < 0.5:
            left_column.append(block)
        else:
            right_column.append(block)

    # Sort each column vertically by their top position
    left_column = sorted(left_column, key=lambda x: x["Geometry"]["BoundingBox"]["Top"])
    right_column = sorted(right_column, key=lambda x: x["Geometry"]["BoundingBox"]["Top"])

    # Combine the text, processing the left column first
    combined_text = [block["Text"] for block in left_column]
    combined_text.extend(block["Text"] for block in right_column)

    return "\n".join(combined_text)


def handler(event, context):
    s3 = boto3.client('s3')
    textract = boto3.client('textract')

    # Get bucket name and file key from the event
    key = event['Records'][0]['s3']['object']['key']
    bucket_name = configuration.get_parameter('BucketName')
    raw_prefix = configuration.get_parameter('RawFilesPrefix')
    processed_prefix = configuration.get_parameter('ToBeProcessedFilesPrefix')

    print(f"Raw Prefix: {raw_prefix}")
    print(f"Processed Prefix: {processed_prefix}")
    print(f"Processing file: {key} from bucket: {bucket_name}")

    # Invoking Textract to analyze the file
    response = textract.analyze_document(
        Document={
            'S3Object': {
                'Bucket': bucket_name,
                'Name': key
            }
        },
        FeatureTypes=['TABLES', 'FORMS']
    )

    # Process the response to extract two-column structured text
    extracted_text = extract_text_by_columns(response)

    # Save extracted text to the ProcessedFiles folder
    processed_key = key.replace(raw_prefix, processed_prefix).replace('.pdf', '.txt').replace('.jpg', '.txt').replace('.png', '.txt')
    print(f"Processed Key: {processed_key}")

    # Save the extracted text to the processed prefix
    s3.put_object(
        Bucket=bucket_name,
        Key=processed_key,
        Body=extracted_text
    )

    return {"StatusCode": 200, "body": "Text Extraction Complete!"}
