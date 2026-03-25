import os
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'

import time, boto3, uuid
import numpy as np
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import ElectraTokenizer
import onnxruntime as ort
from mangum import Mangum
from fastapi.middleware.cors import CORSMiddleware

# --- DynamoDB 설정 ---
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SentimentAnalysisLog')

COLD_START = True 
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") 
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}
API_KEY = os.environ.get("MY_API_KEY")

app = FastAPI(title="Korean Sentiment API (ONNX)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)
def download_model_from_s3():
    """S3에서 ONNX 모델 및 설정 파일 다운로드"""
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True) 
    
    # [수정] 다운로드할 파일 목록에 model.onnx 추가
    files = [
        'temp_model/config.json', 
        'temp_model/model.onnx', # .safetensors 대신 .onnx
        'temp_model/model.onnx.data',
        'temp_model/tokenizer.json', 
        'temp_model/tokenizer_config.json', 
        'temp_model/vocab.txt'
    ]
    
    for s3_key in files:
        raw_file_name = s3_key.split('/')[-1]
        # 파일명 규칙 유지 (model_ 접두어 제거 등 사용자님 기존 로직 반영)
        file_name = raw_file_name.replace('model_', '')
        target = os.path.join(MODEL_DIR, file_name)
        
        if not os.path.exists(target):
            try:
                s3.download_file(BUCKET_NAME, s3_key, target)
            except Exception as e:
                print(f"파일 다운로드 실패: {s3_key}, 에러: {e}")
                raise e

# 전역 변수 설정
tokenizer = None
ort_session = None

def get_model():
    """ONNX 세션 및 토크나이저 로드"""
    global tokenizer, ort_session
    if tokenizer is None or ort_session is None:
        download_model_from_s3()
        
        # 1. 토크나이저 로드
        tokenizer = ElectraTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
        
        # 2. ONNX 런타임 세션 로드 (torch 없이 실행)
        onnx_path = os.path.join(MODEL_DIR, "model.onnx")
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        # CPU 환경 최적화 설정
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

@app.post("/predict")
async def predict(inp: PredictIn, request: Request):
    # [핵심] 브라우저의 사전 확인(OPTIONS) 요청은 인증을 건너뜁니다.
    if request.method == "OPTIONS":
        return {"ok": True}

    # 실제 데이터가 오가는 POST 요청일 때만 키를 검사합니다.
    client_api_key = request.headers.get("x-api-key")
    
    if client_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")

    global COLD_START
    tk, session = get_model() 
    
    t0 = time.time()
    text = (inp.text or "").strip()[:1000] 
    if not text: raise HTTPException(status_code=400, detail="text is required")
    
    cold = COLD_START
    COLD_START = False

    try:
        # [수정] ONNX용 입력 데이터 생성 (numpy 기반)
        inputs = tk(text, return_tensors="np", truncation=True, max_length=256)
        ort_inputs = {
            'input_ids': inputs['input_ids'].astype(np.int64),
            'attention_mask': inputs['attention_mask'].astype(np.int64)
        }

        # ONNX 추론 실행
        ort_outs = session.run(None, ort_inputs)
        logits = ort_outs[0]

        # [수정] Softmax 계산 (numpy 기반)
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
        probs = probs[0] # 첫 번째 결과값 추출

        neg_prob, pos_prob = float(probs[0]), float(probs[1])
        diff = abs(pos_prob - neg_prob) 

        # 사용자님의 기존 NEUTRAL 판정 로직 유지
        if diff < 0.15:
            label, score = "NEUTRAL", max(pos_prob, neg_prob)
        else:
            pred_id = np.argmax(probs)
            label, score = LABEL_MAP.get(str(pred_id), str(pred_id)), float(probs[pred_id])

        latency_ms = int((time.time() - t0) * 1000)
        
        # DynamoDB 로그 저장 로직 유지 [cite: 12, 24]
        try:
            log_item = {
                'requestId': str(uuid.uuid4()),
                'timestamp': int(time.time()),
                'label': label,
                'confidence': Decimal(str(round(score, 4))),
                'latency_ms': latency_ms
            }
            table.put_item(Item=log_item) [cite: 24, 30]
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