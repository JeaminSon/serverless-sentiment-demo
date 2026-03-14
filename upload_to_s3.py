import boto3
import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification

BUCKET_NAME = "sentiment-model-storage-jambread"
MODEL_NAME = "monologg/koelectra-small-v3-discriminator" 
LOCAL_TEMP_DIR = "./temp_model"

print("모델 다운로드 중...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

tokenizer.save_pretrained(LOCAL_TEMP_DIR)
model.save_pretrained(LOCAL_TEMP_DIR)

print("S3 업로드 중...")
s3 = boto3.client('s3')

for root, dirs, files in os.walk(LOCAL_TEMP_DIR):
    for file in files:
        local_path = os.path.join(root, file)
        s3_path = os.path.join("model", file)
        s3.upload_file(local_path, BUCKET_NAME, s3_path)
        print(f"업로드 완료: {s3_path}")

print("모든 작업이 완료되었습니다!")
