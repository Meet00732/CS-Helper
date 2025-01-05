import boto3
import spacy
import re
import unicodedata
from bs4 import BeautifulSoup
import contractions
from nltk.corpus import stopwords
from configuration import configuration


# Initialize s3 client and spacy model
s3 = boto3.client('s3')
nlp = spacy.load("en_core_web_sm")
stop_words = set(stopwords.words("english"))


def remove_html_tags(text):
    """Remove HTML tags from text."""
    return BeautifulSoup(text, "html.parser").get_text()


def to_lowercase(text):
    """Convert text to lowercase."""
    return text.lower()


def standardize_accented_chars(text):
    """Convert accented characters to standard ASCII charcters."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8", "ignore")


def remove_urls(text):
    """Removes URLs from the text."""
    return re.sub(r"https?://\S+|www\.\S+", "", text)


def expand_contractions(text):
    """Expand contractions (e.g don't -> do not)"""
    expanded_words = [contractions.fix(word) for word in text.split()]
    return " ".join(expanded_words)


def remove_special_characters(text):
    """Removes special characters from the text."""
    pattern = r"[^a-zA-Z0-9.,!?/:;\"\'\s]"
    return re.sub(pattern, "", text)


def remove_punctuation(text):
    """Removes punctuations from the text."""
    return "".join([c for c in text if c not in re.escape("!#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")])


def lemmatization(text):
    """Perform lemmatization to extract base forms of the words."""
    doc = nlp(text)
    return " ".join([token.lemma_ for token in doc])

def remove_stopwords(text):
    """Removes stop words from the text."""
    doc = nlp(text)
    return " ".join([token.text for token in doc if not token.is_stop])


def annotate_entities(text):
    """Annotate text with named entity tags."""
    doc = nlp(text)
    annotated_text = text
    for ent in doc.ents:
        annotated_text = annotated_text.replace(ent.text, f"[{ent.label_}] {ent.text}")
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
    cleaned_text = expand_contractions(cleaned_text)
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
    response = s3.get_object(Bucket=bucket_name, key=key)
    raw_text = response["Body"].read().decode("utf-8")

    # Process text
    annotated_text = data_cleaning_pipeline(raw_text)

    # Save the processed text to correct s3.
    destination_folder = configuration.get_parameter("ProcessedFilesPrefix")
    file_name = key.split("/")[-1]
    annotated_key = f"{destination_folder}{file_name.replace(".txt", "_cleaned_annotated.txt")}"

    s3.put_object(Bucket=bucket_name, Key=annotated_key, Body=annotated_text)

    return {
        "statusCode": 200,
        "body": f"File processed successfully. Annotated text saved as {annotated_key}."
    }

