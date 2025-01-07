import boto3
import re
import unicodedata
import logging
from bs4 import BeautifulSoup
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from textblob import TextBlob
from configuration import configuration

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client('s3')

# Configure NLTK to use prepackaged resources
import nltk
nltk.data.path.append("/var/task/nltk_data")  # Path to prepackaged data in the deployment package

# Initialize NLTK tools with fallback
try:
    stop_words = set(stopwords.words("english"))
except LookupError as e:
    logger.warning("Missing stopwords resource; attempting to download dynamically.")
    nltk.download("stopwords", download_dir="/tmp")
    nltk.data.path.append("/tmp")
    stop_words = set(stopwords.words("english"))

try:
    lemmatizer = WordNetLemmatizer()
except LookupError as e:
    logger.warning("Missing wordnet resource; attempting to download dynamically.")
    nltk.download("wordnet", download_dir="/tmp")
    nltk.data.path.append("/tmp")
    lemmatizer = WordNetLemmatizer()

# Text cleaning functions
def remove_html_tags(text):
    return BeautifulSoup(text, "html.parser").get_text()

def to_lowercase(text):
    return text.lower()

def standardize_accented_chars(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8", "ignore")

def remove_urls(text):
    return re.sub(r"https?://\S+|www\.\S+", "", text)

def remove_special_characters(text):
    pattern = r"[^a-zA-Z0-9.,!?/:;\"\'\s]"
    return re.sub(pattern, "", text)

def remove_punctuation(text):
    return "".join([c for c in text if c not in re.escape("!#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")])

def lemmatization(text):
    words = word_tokenize(text)
    return " ".join([lemmatizer.lemmatize(word) for word in words])

def remove_stopwords(text):
    words = word_tokenize(text)
    return " ".join([word for word in words if word.lower() not in stop_words])

def annotate_entities(text):
    blob = TextBlob(text)
    annotated_text = text
    for noun_phrase in blob.noun_phrases:
        annotated_text = annotated_text.replace(noun_phrase, f"[ENTITY] {noun_phrase}")
    return annotated_text

# Data cleaning pipeline
def data_cleaning_pipeline(raw_text):
    cleaned_text = remove_html_tags(raw_text)
    cleaned_text = to_lowercase(cleaned_text)
    cleaned_text = standardize_accented_chars(cleaned_text)
    cleaned_text = remove_urls(cleaned_text)
    cleaned_text = remove_special_characters(cleaned_text)
    cleaned_text = remove_punctuation(cleaned_text)
    cleaned_text = lemmatization(cleaned_text)
    cleaned_text = remove_stopwords(cleaned_text)
    return annotate_entities(cleaned_text)

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
