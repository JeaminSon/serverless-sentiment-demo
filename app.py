import os
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'

import time, boto3, uuid
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import ElectraTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum

# --- [수정] DynamoDB 설정 ---
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SentimentAnalysisLog')

COLD_START = True 
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") 
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}

app = FastAPI(title="Korean Sentiment API")

# (기존 download_model_from_s3, get_model 함수는 그대로 유지...)
def download_model_from_s3():
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)
    files = ['temp_model/config.json', 'temp_model/model.safetensors', 'temp_model/tokenizer.json', 'temp_model/tokenizer_config.json', 'temp_model/vocab.txt']
    for s3_key in files:
        raw_file_name = s3_key.split('/')[-1]
        file_name = 'model.safetensors' if 'model_model.safetensors' in raw_file_name else raw_file_name.replace('model_', '')
        target = os.path.join(MODEL_DIR, file_name)
        if not os.path.exists(target):
            try: s3.download_file(BUCKET_NAME, s3_key, target)
            except Exception as e: raise e

tokenizer = None
model = None

def get_model():
    global tokenizer, model
    if tokenizer is None or model is None:
        download_model_from_s3()
        tokenizer = ElectraTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True, output_attentions=True)
        model.eval()
    return tokenizer, model

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health(): return {"ok": True}

@app.post("/predict")
def predict(inp: PredictIn, request: Request):
    global COLD_START
    tk, md = get_model() 
    
    t0 = time.time()
    text = (inp.text or "").strip()[:1000] 
    if not text: raise HTTPException(status_code=400, detail="text is required")
    
    cold = COLD_START
    COLD_START = False

    try:
        inputs = tk(text, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            outputs = md(**inputs)
        
        probs = torch.softmax(outputs.logits, dim=-1)[0]
        neg_prob, pos_prob = float(probs[0]), float(probs[1])
        diff = abs(pos_prob - neg_prob) 

        if diff < 0.15:
            label, score = "NEUTRAL", max(pos_prob, neg_prob)
        else:
            pred_id = torch.argmax(probs).item()
            label, score = LABEL_MAP.get(str(pred_id), str(pred_id)), float(probs[pred_id])

        latency_ms = int((time.time() - t0) * 1000)
        
        # --- [핵심 추가] DynamoDB 로그 저장 로직 ---
        try:
            log_item = {
                'requestId': str(uuid.uuid4()),
                'timestamp': int(time.time()),
                'label': label,
                'confidence': Decimal(str(round(score, 4))), # 소수점 4자리까지 Decimal로 저장
                'latency_ms': latency_ms
            }
            table.put_item(Item=log_item)
            print(f"DB 저장 성공: {label} ({score})")
        except Exception as db_err:
            print(f"DB 저장 실패(무시): {db_err}")

        return {
            "label": label,
            "score": score,
            "latency_ms": latency_ms,
            "cold_start": cold
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mangum 핸들러가 FastAPI 앱을 감싸도록 설정
handler = Mangum(app)