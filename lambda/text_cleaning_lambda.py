import boto3
import re
import unicodedata
from bs4 import BeautifulSoup
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from textblob import TextBlob
from configuration import configuration

# Initialize s3 client
s3 = boto3.client('s3')

# Download required NLTK resources
import nltk
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

stop_words = set(stopwords.words("english"))
lemmatizer = WordNetLemmatizer()

def remove_html_tags(text):
    """Remove HTML tags from text."""
    return BeautifulSoup(text, "html.parser").get_text()

def to_lowercase(text):
    """Convert text to lowercase."""
    return text.lower()

def standardize_accented_chars(text):
    """Convert accented characters to standard ASCII characters."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8", "ignore")

def remove_urls(text):
    """Removes URLs from the text."""
    return re.sub(r"https?://\S+|www\.\S+", "", text)

def remove_special_characters(text):
    """Removes special characters from the text."""
    pattern = r"[^a-zA-Z0-9.,!?/:;\"\'\s]"
    return re.sub(pattern, "", text)

def remove_punctuation(text):
    """Removes punctuations from the text."""
    return "".join([c for c in text if c not in re.escape("!#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")])

def lemmatization(text):
    """Perform lemmatization to extract base forms of the words."""
    words = word_tokenize(text)
    return " ".join([lemmatizer.lemmatize(word) for word in words])

def remove_stopwords(text):
    """Removes stop words from the text."""
    words = word_tokenize(text)
    return " ".join([word for word in words if word.lower() not in stop_words])

def annotate_entities(text):
    """Annotate text with named entity tags."""
    blob = TextBlob(text)
    annotated_text = text
    for noun_phrase in blob.noun_phrases:
        annotated_text = annotated_text.replace(noun_phrase, f"[ENTITY] {noun_phrase}")
    return annotated_text

#### Pipeline to perform NLP tasks.
def data_cleaning_pipeline(raw_text):
    """
        Pipeline for data cleaning.
    """
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
def lambda_handler(event, context):
    """
    Lambda function to clean and annotate text from an S3 file.
    """

    # Extract S3 bucket and file details
    bucket_name = event["Records"][0]["s3"]["bucket"]["name"]
    key = event["Records"][0]["s3"]["object"]["key"]

    # Getting file from s3.
    response = s3.get_object(Bucket=bucket_name, Key=key)
    raw_text = response["Body"].read().decode("utf-8")

    # Process text
    annotated_text = data_cleaning_pipeline(raw_text)

    # Save the processed text to correct s3.
    destination_folder = configuration.get_parameter("ProcessedFilesPrefix")
    file_name = key.split("/")[-1]
    annotated_key = f"{destination_folder}{file_name.replace('.txt', '_cleaned_annotated.txt')}"

    s3.put_object(Bucket=bucket_name, Key=annotated_key, Body=annotated_text)

    return {
        "statusCode": 200,
        "body": f"File processed successfully. Annotated text saved as {annotated_key}."
    }
