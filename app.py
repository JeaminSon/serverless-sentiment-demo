import os, time
from fastapi import FastAPI, HTTPException, Request
from collections import deque
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum

COLD_START = True
MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/model")
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_REQUESTS = 20

_RATE_BUCKET = {}

app = FastAPI(title="Korean Sentiment API")

# 컨테이너 시작 시 1회 로딩 (콜드스타트에만 영향)
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/predict")
def predict(inp: PredictIn, request: Request):
    global COLD_START
    t0 = time.time()
    now = t0
    ip = _get_client_ip(request)
    _rate_limit_check(ip, now)
    
    text = (inp.text or "").strip()
    if not text:
       raise HTTPException(status_code=400, detail="text is required")
    cold = COLD_START
    COLD_START = False

    try:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            pred_id = int(torch.argmax(probs).item())
            score = float(probs[pred_id].item())
    except Exception as e:
        print({"msg": "predict_error", "err": str(e)})
        raise HTTPException(status_code=500, detail="inference failed")

    raw_label = str(pred_id)
    label = LABEL_MAP.get(raw_label, raw_label)
    latency_ms = int((time.time() - t0) * 1000)

    # CloudWatch 로그 (원문 텍스트는 남기지 않음)
    print({"msg": "predict", "len": len(text), "label": label, "score": score, "latency_ms": latency_ms})

    return {"label": label, "score": score, "raw_label": raw_label, "latency_ms": latency_ms, "cold_start": cold}


def _get_client_ip(request: Request) -> str:
    # Lambda Function URL 앞단 프록시가 X-Forwarded-For를 넣어줌
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # "client, proxy1, proxy2" 형태일 수 있음 → 첫 번째가 원 IP
        return xff.split(",")[0].strip()
    # fallback (환경 따라 None일 수 있음)
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

def _rate_limit_check(ip: str, now: float) -> None:
    q = _RATE_BUCKET.get(ip)
    if q is None:
        q = deque()
        _RATE_BUCKET[ip] = q

    # 윈도우 밖 기록 제거
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    while q and q[0] < cutoff:
        q.popleft()

    if len(q) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too Many Requests: {RATE_LIMIT_MAX_REQUESTS}/{RATE_LIMIT_WINDOW_SEC}s"
        )

    q.append(now)

handler = Mangum(app)