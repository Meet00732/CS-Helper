import boto3
import re
import unicodedata
import logging
from bs4 import BeautifulSoup
from nltk.tokenize import sent_tokenize
from datetime import datetime
from configuration import configuration

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


COMMON_HEADINGS = [
    "abstract", "introduction", "methods", "methodology", "results",
    "discussion", "conclusion", "references", "acknowledgments"
]

# Initialize S3 client
s3 = boto3.client('s3')

# Configure NLTK to use prepackaged resources
import nltk
nltk.data.path.append("/var/task/nltk_data")  # Path to prepackaged data in the deployment package


# Text cleaning functions
def remove_html_tags(text):
    return BeautifulSoup(text, "html.parser").get_text()

def to_lowercase(text):
    return text.lower()

def standardize_accented_chars(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8", "ignore")

def remove_punctuation(text):
    return "".join([c for c in text if c not in re.escape("!#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")])

def remove_emails(text):
    return re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)

def remove_phone_numbers(text):
    return re.sub(r'\b\d{10,15}\b', '', text)

def remove_links(text):
    return re.sub(r'http[s]?://\S+|www\.\S+', '', text)

def standardize_dates(text):
    return re.sub(r'\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b',
                  lambda m: datetime.strptime(m.group(0), '%d/%m/%Y').strftime('%Y-%m-%d'), text)


def capitalize_proper_nouns(text):
    words = text.split()
    return " ".join([word.capitalize() if word.islower() and len(word) > 3 else word for word in words])


def remove_domains(text):
    """Remove .com and similar domain extensions."""
    return re.sub(r'\b\w+\.(com|org|net|edu|gov|info|io|xyz|co)\b', '', text)


def remove_special_characters(text):
    """
    Removes only @ and # characters from the text.
    """
    return text.replace("@", "").replace("#", "")


def detect_and_tag_headings(text):
    """
    Detects and tags headings using formatting, position, and common keywords.
    """
    lines = text.split("\n")
    tagged_lines = []

    for i, line in enumerate(lines):
        stripped_line = line.strip()

        # Common headings list
        if stripped_line.lower() in COMMON_HEADINGS:
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        # Numbered headings (e.g., "1. Introduction", "1-1 Objectives", "1) Heading")
        if re.match(r"^\d+(\.\d+)*[\.\-\)]?\s+[A-Za-z]+", stripped_line):
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        # Default: keep the original line
        tagged_lines.append(line)

    return "\n".join(tagged_lines)




# def annotate_entities(text):
#     blob = TextBlob(text)
#     annotated_text = text
#     for noun_phrase in blob.noun_phrases:
#         annotated_text = annotated_text.replace(noun_phrase, f"[ENTITY] {noun_phrase}")
#     return annotated_text

def annotate_entities(text):
    """
    Annotate text with entities detected by AWS Comprehend.
    """
    comprehend = boto3.client("comprehend")
    sentences = sent_tokenize(text)
    annotated_lines = text.splitlines()  # Preserve line structure

    for i, line in enumerate(annotated_lines):
        try:
            response = comprehend.detect_entities(Text=line, LanguageCode="en")
            entities = response["Entities"]

            # Sort entities by offset for accurate annotation
            for entity in sorted(entities, key=lambda x: x["BeginOffset"], reverse=True):
                if entity["Type"] in ["PERSON", "ORGANIZATION", "LOCATION", "TITLE"]:
                    # Annotate the line while preserving original text
                    start, end = entity["BeginOffset"], entity["EndOffset"]
                    annotated_line = list(line)
                    annotated_line[start:end] = f"[{entity['Type']}] {line[start:end]}"
                    annotated_lines[i] = "".join(annotated_line)
        except Exception as e:
            logger.warning(f"Error detecting entities for line: {line}. Error: {e}")
            continue

    return "\n".join(annotated_lines)





# Data cleaning pipeline
def data_cleaning_pipeline(raw_text):
    # Step 1: Detect and tag headings first
    tagged_text = detect_and_tag_headings(raw_text)

    # Step 2: Remove unwanted data while preserving structure
    lines = tagged_text.splitlines()
    cleaned_lines = []

    for line in lines:
        # Clean individual lines
        line = remove_html_tags(line)
        line = to_lowercase(line)
        line = standardize_accented_chars(line)
        line = remove_domains(line)
        line = remove_emails(line)
        line = remove_links(line)
        line = remove_phone_numbers(line)
        line = remove_special_characters(line)
        line = capitalize_proper_nouns(line)
        line = standardize_dates(line)

        # Append cleaned line
        cleaned_lines.append(line)

    # Step 3: Annotate entities after cleaning
    cleaned_text = "\n".join(cleaned_lines)
    annotated_text = annotate_entities(cleaned_text)

    return annotated_text



# Lambda handler
def handler(event, context):
    try:
        # Extract S3 bucket and file details
        bucket_name = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        
        logger.info(f"Processing file from bucket: {bucket_name}, key: {key}")

        # Ensure the file is a .txt file
        if not key.endswith(".txt"):
            logger.error(f"Unsupported file type: {key}")
            return {
                "statusCode": 400,
                "body": "Unsupported file type. Only .txt files are allowed."
            }

        # Get file from S3
        response = s3.get_object(Bucket=bucket_name, Key=key)
        raw_text = response["Body"].read().decode("utf-8")

        # Process text
        annotated_text = data_cleaning_pipeline(raw_text)

        # Save processed text back to S3
        destination_folder = configuration.get_parameter("ProcessedFilesPrefix")
        file_name = key.split("/")[-1]
        annotated_key = f"{destination_folder}{file_name.replace('.txt', '_cleaned_annotated.txt')}"

        s3.put_object(Bucket=bucket_name, Key=annotated_key, Body=annotated_text)

        logger.info(f"Processed file saved to: {annotated_key}")
        return {
            "statusCode": 200,
            "body": f"File processed successfully. Annotated text saved as {annotated_key}."
        }

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Error processing file: {str(e)}"
        }
