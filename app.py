import os
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'
import time, boto3
from fastapi import FastAPI, HTTPException, Request
from collections import deque
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum 

COLD_START = True 
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") 
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
    
    files = ['model\\config.json', 'model\\model.safetensors', 'model\\tokenizer.json', 'model\\tokenizer_config.json']
    
    for s3_key in files:
        file_name = s3_key.split('\\')[-1]
        target = os.path.join(MODEL_DIR, file_name)
        if not os.path.exists(target):
            print(f"Downloading {s3_key} from S3...")
            s3.download_file(BUCKET_NAME, s3_key, target)

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
    #ip = _get_client_ip(request)
    #_rate_limit_check(ip, now)

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
        probs = torch.softmax(logits, dim=-1)[0]
        
        # 긍정/부정 확률 추출 (0: NEG, 1: POS)
        neg_prob = float(probs[0])
        pos_prob = float(probs[1])
        diff = abs(pos_prob - neg_prob) # 두 확률의 차이 계산

        # --- 중립 판별 및 신뢰도 설명 로직 ---
        # 우선순위: 차이가 0.15(15%) 미만이면 무조건 중립 처리
        if diff < 0.15:
            label = "NEUTRAL"
            score = max(pos_prob, neg_prob) # 둘 중 높은 쪽을 일단 점수로 표기
            reason = "긍정과 부정의 특징이 모두 미미하거나 비슷하게 나타납니다."
            advice = "문장에 '슬프다', '기쁘다'와 같은 감정 표현을 섞어보세요."
        else:
            pred_id = torch.argmax(probs).item()
            label = LABEL_MAP.get(str(pred_id), str(pred_id))
            score = float(probs[pred_id])
            reason = f"모델이 {score*100:.1f}%의 확률로 {label}의 특징을 감지했습니다."
            advice = "분석이 안정적으로 수행되었습니다."

        # (Attention 분석 로직 - 기존과 동일)
        attentions = outputs.attentions[-1]
        avg_attention = attentions[0].mean(dim=0).mean(dim=0)
        tokens = tk.convert_ids_to_tokens(inputs['input_ids'][0])
        token_scores = []
        for i, (token, score_val) in enumerate(zip(tokens, avg_attention.tolist())):
            if token not in [tk.cls_token, tk.sep_token, tk.pad_token]:
                token_scores.append((token.replace('##', ''), score_val))
        
        top_words = sorted(token_scores, key=lambda x: x[1], reverse=True)[:3]
        top_word_list = [w[0] for w in top_words]

    except Exception as e:
        print({"msg": "predict_error", "err": str(e)})
        raise HTTPException(status_code=500, detail="inference failed")

    latency_ms = int((time.time() - t0) * 1000)
    
    return {
        "label": label,
        "score": score,
        "analysis": {
            "reason": reason,
            "advice": advice,
            "top_influential_words": top_word_list
        },
        "latency_ms": latency_ms
    } 

# ... (IP 추출 및 Rate Limit 함수는 그대로 유지) ...
handler = Mangum(app)
