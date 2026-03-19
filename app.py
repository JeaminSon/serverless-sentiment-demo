import os
# 람다 환경의 읽기/쓰기 가능 공간인 /tmp 사용
os.environ['TRANSFORMERS_CACHE'] = '/tmp'
os.environ['HF_HOME'] = '/tmp'

import time, boto3
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import ElectraTokenizer, AutoModelForSequenceClassification
import torch
from mangum import Mangum
import uuid

COLD_START = True 
MODEL_DIR = "/tmp/model" 
BUCKET_NAME = os.environ.get("MODEL_BUCKET_NAME") 
LABEL_MAP = {"0": "NEGATIVE", "1": "POSITIVE"}

app = FastAPI(title="Korean Sentiment API")

def download_model_from_s3():
    s3 = boto3.client('s3')
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)
    
    # S3에 저장된 실제 키 리스트
    files = [
        'temp_model/config.json', 
        'temp_model/model.safetensors', 
        'temp_model/tokenizer.json', 
        'temp_model/tokenizer_config.json',
        'temp_model/vocab.txt'
    ]
    
    for s3_key in files:
        # [핵심 수정] 가중치 파일 인식 문제 해결
        # model_model.safetensors -> model.safetensors로 정확히 변환되어야 라이브러리가 읽습니다.
        raw_file_name = s3_key.split('/')[-1]
        if 'model_model.safetensors' in raw_file_name:
            file_name = 'model.safetensors'
        else:
            file_name = raw_file_name.replace('model_', '')
            
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
    if tokenizer is None or model is None:
        download_model_from_s3()
        print("Loading model weights into memory...")
        
        # [수정] AutoTokenizer 대신 ElectraTokenizer를 직접 호출합니다.
        # vocab.txt 파일이 있으므로 이제 정상 작동합니다.
        tokenizer = ElectraTokenizer.from_pretrained(
            MODEL_DIR, 
            local_files_only=True
        )
        
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_DIR, 
            local_files_only=True,
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

        # --- 중립(Neutral) 판별 로직 ---
        if diff < 0.15:
            label = "NEUTRAL"
            score = max(pos_prob, neg_prob)
            reason = "긍정과 부정의 특징이 모두 미미하거나 비슷하게 나타납니다."
            advice = "문장에 감정을 나타내는 구체적인 단어를 섞어보세요."
        else:
            pred_id = torch.argmax(probs).item()
            label = LABEL_MAP.get(str(pred_id), str(pred_id))
            score = float(probs[pred_id])
            reason = f"모델이 {score*100:.1f}%의 확률로 {label} 특징을 감지했습니다."
            advice = "분석이 안정적으로 수행되었습니다."

        # Attention 분석
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

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('SentimentAnalysisLog')

def lambda_handler(event, context):
    try:
        log_item = {
            'requestId': str(uuid.uuid4()),
            'timestamp': int(time.time()),
            'label': result['label'],      # 긍정/부정 결과만 저장
            'confidence': Decimal(str(result['score'])), # 신뢰도 숫자 저장
            'latency_ms': 17               # 측정된 지연 시간
        }
        table.put_item(Item=log_item)
    except Exception as e:
        print(f"DB 저장 중 오류 발생(무시하고 진행): {e}")
        
    return result
 
handler = Mangum(app)  
