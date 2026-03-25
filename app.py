import os
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'

import time, boto3, uuid
import numpy as np
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request, Depends, Security
from pydantic import BaseModel
from transformers import ElectraTokenizer
import onnxruntime as ort
from mangum import Mangum
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

# --- 환경 변수 로드 ---
# [주의] AWS 람다 콘솔에 MY_API_KEY와 MODEL_BUCKET_NAME이 등록되어 있어야 합니다.
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME")
API_KEY = os.environ.get("MY_API_KEY", "jambreadson77!") 

# --- DynamoDB 설정 ---
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SentimentAnalysisLog')

COLD_START = True 
MODEL_DIR = "/tmp/model" 
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}

# --- 인증 설정 (Security Dependency) ---
API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(header_value: str = Security(api_key_header)):
    # 브라우저의 OPTIONS 요청은 인증을 따지지 않고 통과시켜야 CORS가 해결됩니다.
    if header_value != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return header_value

app = FastAPI(title="Korean Sentiment API (ONNX)")

# --- CORS 설정 (최우선 순위) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

def download_model_from_s3():
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True) 
    
    files = [
        'temp_model/config.json', 
        'temp_model/model.onnx',
        'temp_model/model.onnx.data',
        'temp_model/tokenizer.json', 
        'temp_model/tokenizer_config.json', 
        'temp_model/vocab.txt'
    ]
    
    for s3_key in files:
        raw_file_name = s3_key.split('/')[-1]
        file_name = raw_file_name.replace('model_', '')
        target = os.path.join(MODEL_DIR, file_name)
        
        if not os.path.exists(target):
            try:
                s3.download_file(BUCKET_NAME, s3_key, target)
            except Exception as e:
                print(f"파일 다운로드 실패: {s3_key}, 에러: {e}")
                raise e

tokenizer = None
ort_session = None

def get_model():
    global tokenizer, ort_session
    if tokenizer is None or ort_session is None:
        download_model_from_s3()
        tokenizer = ElectraTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
        onnx_path = os.path.join(MODEL_DIR, "model.onnx")
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        ort_session = ort.InferenceSession(
            onnx_path, 
            sess_options, 
            providers=['CPUExecutionProvider']
        )
    return tokenizer, ort_session

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health(): return {"ok": True}

# --- 핵심 수정: Depends(get_api_key) 적용 ---
@app.post("/predict")
async def predict(inp: PredictIn, key: str = Depends(get_api_key)):
    global COLD_START
    tk, session = get_model() 
    
    t0 = time.time()
    text = (inp.text or "").strip()[:1000] 
    if not text: raise HTTPException(status_code=400, detail="text is required")
    
    cold = COLD_START
    COLD_START = False

    try:
        inputs = tk(text, return_tensors="np", truncation=True, max_length=256)
        ort_inputs = {
            'input_ids': inputs['input_ids'].astype(np.int64),
            'attention_mask': inputs['attention_mask'].astype(np.int64)
        }

        ort_outs = session.run(None, ort_inputs)
        logits = ort_outs[0]

        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
        probs = probs[0]

        neg_prob, pos_prob = float(probs[0]), float(probs[1])
        diff = abs(pos_prob - neg_prob) 

        if diff < 0.15:
            label, score = "NEUTRAL", max(pos_prob, neg_prob)
        else:
            pred_id = np.argmax(probs)
            label, score = LABEL_MAP.get(str(pred_id), str(pred_id)), float(probs[pred_id])

        latency_ms = int((time.time() - t0) * 1000)
        
        try:
            log_item = {
                'requestId': str(uuid.uuid4()),
                'timestamp': int(time.time()),
                'label': label,
                'confidence': Decimal(str(round(score, 4))),
                'latency_ms': latency_ms
            }
            table.put_item(Item=log_item)
        except Exception as db_err:
            print(f"DB 저장 실패(무시): {db_err}")

        return {
            "label": label,
            "score": score,
            "latency_ms": latency_ms,
            "cold_start": cold
        }

    except Exception as e:
        print(f"추론 중 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))

handler = Mangum(app)