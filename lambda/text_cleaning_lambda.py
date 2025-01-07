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
    Detects headings using formatting, position, and common keywords.
    """
    lines = text.split("\n")
    tagged_lines = []

    for i, line in enumerate(lines):
        stripped_line = line.strip()

        # Common headings list
        if stripped_line.lower() in COMMON_HEADINGS:
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        # Numbered headings (e.g., "1. Introduction", "1-1 Objectives")
        if re.match(r"^\d+(\.\d+)*[\.\-]?\s+[A-Za-z]+", stripped_line):
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        # Headings with fewer than 10 words and no punctuation
        if re.match(r"^[A-Za-z\s]+$", stripped_line) and len(stripped_line.split()) <= 10:
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        # Headings with trailing colon (e.g., "Summary:")
        if stripped_line.endswith(":") and len(stripped_line.split()) <= 10:
            tagged_lines.append(f"[HEADING] {stripped_line}")
            continue

        tagged_lines.append(stripped_line)

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
    annotated_text = list(text)  # Convert text to a mutable list for offset-based replacement

    current_position = 0  # Tracks position in the original text

    for sentence in sentences:
        try:
            response = comprehend.detect_entities(Text=sentence, LanguageCode="en")
            entities = response["Entities"]
            
            # Adjust offsets based on the sentence's position in the original text
            sentence_start = text.find(sentence, current_position)
            sentence_end = sentence_start + len(sentence)
            
            # Process entities in reverse order to avoid offset conflicts
            for entity in sorted(entities, key=lambda x: x["BeginOffset"], reverse=True):
                if entity["Type"] in ["PERSON", "ORGANIZATION", "LOCATION", "TITLE"]:
                    # Skip redundant or irrelevant entities
                    if len(entity["Text"]) > 2:
                        start = sentence_start + entity["BeginOffset"]
                        end = sentence_start + entity["EndOffset"]
                        annotated_text[start:end] = f"[{entity['Type']}] {text[start:end]}"
            
            # Update current position
            current_position = sentence_end
        except Exception as e:
            logger.warning(f"Error detecting entities for sentence: {sentence}. Error: {e}")
            continue

    return "".join(annotated_text)




# Data cleaning pipeline
def data_cleaning_pipeline(raw_text):
    # Detect and tag headings first
    cleaned_text = detect_and_tag_headings(raw_text)

    # Remove unwanted data
    cleaned_text = remove_html_tags(cleaned_text)
    cleaned_text = to_lowercase(cleaned_text)
    cleaned_text = standardize_accented_chars(cleaned_text)
    cleaned_text = remove_domains(cleaned_text)
    cleaned_text = remove_emails(cleaned_text)
    cleaned_text = remove_links(cleaned_text)
    cleaned_text = remove_phone_numbers(cleaned_text)
    cleaned_text = remove_special_characters(cleaned_text)
    cleaned_text = capitalize_proper_nouns(cleaned_text)

    # Annotate entities after cleaning
    cleaned_text = annotate_entities(cleaned_text)

    return cleaned_text



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
