import os
# 람다 환경의 읽기/쓰기 가능 공간인 /tmp 사용
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'

import time, boto3
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum

COLD_START = True 
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") 
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}

app = FastAPI(title="Korean Sentiment API")

def download_model_from_s3():
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)
    
    # S3에 저장된 실제 키 리스트 (슬래시 구분)
    files = [
        'temp_model/model_config.json', 
        'temp_model/model_model.safetensors', 
        'temp_model/model_tokenizer.json', 
        'temp_model/model_tokenizer_config.json'
    ]
    
    for s3_key in files:
        # [핵심] model_ 접두사를 제거하여 라이브러리가 인식 가능한 표준 파일명으로 변환
        # 예: model_config.json -> config.json
        file_name = s3_key.split('/')[-1].replace('model_model', 'model').replace('model_', '')
        target = os.path.join(MODEL_DIR, file_name)
        
        if not os.path.exists(target):
            print(f"Downloading {s3_key} to {target}...") 
            try:
                s3.download_file(BUCKET_NAME, s3_key, target)
            except Exception as e:
                print(f"S3 Download Error: {str(e)}")
                raise e

tokenizer = None
model = None

def get_model():
    global tokenizer, model
    # 모델 로드 전용 함수 (Lazy Loading)
    if tokenizer is None or model is None:
        download_model_from_s3()
        print("Loading model weights into memory...")
        # /tmp/model 안의 config.json 등을 읽어 가중치 로드
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_DIR, 
            output_attentions=True 
        )
        model.eval()
        print("Model loaded successfully.")
    return tokenizer, model

class PredictIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/predict")
def predict(inp: PredictIn, request: Request):
    global COLD_START
    tk, md = get_model() 
    
    t0 = time.time()
    text = (inp.text or "").strip()[:1000] 
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
        
        neg_prob = float(probs[0])
        pos_prob = float(probs[1])
        diff = abs(pos_prob - neg_prob) 

        # --- 중립(Neutral) 판별 및 설명 로직 ---
        # 긍정/부정 확률 차이가 15% 미만이면 모델이 갈등하는 상태로 간주
        if diff < 0.15:
            label = "NEUTRAL"
            score = max(pos_prob, neg_prob)
            reason = "긍정과 부정의 특징이 모두 미미하거나 비슷하게 나타납니다."
            advice = "문장에 감정을 나타내는 구체적인 형용사를 추가해 보세요."
        else:
            pred_id = torch.argmax(probs).item()
            label = LABEL_MAP.get(str(pred_id), str(pred_id))
            score = float(probs[pred_id])
            reason = f"모델이 {score*100:.1f}%의 확률로 {label}의 특징을 감지했습니다."
            advice = "분석이 성공적으로 완료되었습니다."

        # Attention 분석 (영향력 있는 단어 Top 3)
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
        "latency_ms": latency_ms,
        "cold_start": cold
    } 

handler = Mangum(app)
