import os, time, boto3
from fastapi import FastAPI, HTTPException, Request
from collections import deque
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum

COLD_START = True 
# 1. 경로 설정 수정: 람다의 쓰기 가능 공간인 /tmp를 사용합니다.
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") # 테라폼에서 넣은 환경변수
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_REQUESTS = 20

_RATE_BUCKET = {} 

app = FastAPI(title="Korean Sentiment API") #앙

# --- [추가] S3에서 모델을 가져오는 함수 ---
def download_model_from_s3():
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)
    
    # 우리가 업로드한 파일들 (image_31af1e.png 참고)
    files = ['config.json', 'model.safetensors', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json']
    
    for f in files:
        target = os.path.join(MODEL_DIR, f)
        if not os.path.exists(target):
            print(f"Downloading {f} from S3...")
            s3.download_file(BUCKET_NAME, f"model/{f}", target)

# 2. 로딩 로직 변경: 전역 변수로 두고 필요할 때 로드 (Lazy Loading)
tokenizer = None
model = None

def get_model():
    global tokenizer, model
    if tokenizer is None or model is None:
        download_model_from_s3()
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        # output_attentions 설정을 추가합니다.
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_DIR, 
            output_attentions=True 
        )
        model.eval()
    return tokenizer, model

# --- 이하 기존 로직과 동일 ---

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/predict")
def predict(inp: PredictIn, request: Request):
    global COLD_START
    # 모델 로드 확인 (호출 시점에 로드됨)
    tk, md = get_model() 
    
    t0 = time.time()
    now = t0
    ip = _get_client_ip(request)
    _rate_limit_check(ip, now)

    text = (inp.text or "").strip() [:1000] 
    if not text:
       raise HTTPException(status_code=400, detail="text is required")
    cold = COLD_START
    COLD_START = False

    try:
        inputs = tk(text, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            outputs = md(**inputs)
        logits = outputs.logits
        attentions = outputs.attentions[-1] 
        avg_attention = attentions[0].mean(dim=0).mean(dim=0)
        
        tokens = tk.convert_ids_to_tokens(inputs['input_ids'][0])
        token_scores = []
        for i, (token, score_val) in enumerate(zip(tokens, avg_attention.tolist())):
            if token not in [tk.cls_token, tk.sep_token, tk.pad_token]:
                token_scores.append((token.replace('##', ''), score_val))
        
        top_words = sorted(token_scores, key=lambda x: x[1], reverse=True)[:3]
        top_word_list = [w[0] for w in top_words]

        probs = torch.softmax(logits, dim=-1)[0]
    except Exception as e:
        print({"msg": "predict_error", "err": str(e)})
        raise HTTPException(status_code=500, detail="inference failed")

    # (이후 리턴 로직은 동일)
    raw_label = str(pred_id)
    label = LABEL_MAP.get(raw_label, raw_label)
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "label": label,
        "score": score,
        "analysis": {
            "top_influential_words": top_word_list 
        },
        "latency_ms": latency_ms
    }

# ... (IP 추출 및 Rate Limit 함수는 그대로 유지) ...
handler = Mangum(app)
