# Serverless Korean Sentiment Analysis (AWS Lambda + ECR + S3)

Korean sentiment analysis demo deployed as a serverless container on AWS Lambda.
A static web UI is hosted on S3 + CloudFront and calls the Lambda Function URL

## Demo
- Web (CloudFront): https://d1s8pxdb9ftrht.cloudfront.net
- API (Lambda Function URL):https://u1i1chh9h5.execute-api.ap-northeast-2.amazonaws.com/


[User Browser] ────▶ [CloudFront (CDN)] ────▶ [S3 Static Web]
                                          │
                                          ▼
      [Amazon ECR] ────────────▶ [AWS Lambda (Docker)]
 (Container Registry)                     │
                                  ┌───────┴───────┐
                                  ▼               ▼
                        [HuggingFace Model] [Amazon DynamoDB]
                          (KoELECTRA)      (Inference Logs)
                                                  │
                                                  ▼
                                         [Streamlit Dashboard]
                                         (Real-time Monitoring)
## API
POST /predict
Request
{
  "text": "오늘 기분이 좋아"
}
Response 
{
  "label": "POSITIVE",
  "score": 0.997,
  "raw_label": "1",
  "latency_ms": 28,
  "cold_start": false
}

GET /health 
{"ok": true}

## Operations / Configuration
Region: ap-northeast-2 (Seoul)
Lambda memory: 2048 MB
Lambda timeout: 120 seconds
Container image: AWS ECR
Frontend: S3 static hosting + CloudFront CDN

## Performance (measured from client)
Cold start (first call): ~5.1 s
Warm start (subsequent calls): ~28 ms
Measurement method:
Sent multiple POST requests to /predict
First call includes cold start overhead
Subsequent calls represent warm container latency

### Abuse prevention (soft rate limiting)
Implemented in-app per-IP rate limiting:
Limit: 20 requests / 60 seconds
Keyed by client IP (X-Forwarded-For)
Returns HTTP 429 when exceeded
Note:
This is enforced per Lambda execution environment
Under high concurrency, limits may be distributed
Future hardening
Planned improvements:
AWS WAF rate-based rules
Edge-level throttling via CloudFront
Bot filtering

Privacy Considerations
Raw user text is not logged
Only metadata logged to CloudWatch:
text length
label
latency
Browser dashboard history is opt-in
History stored only in local browser session

Frontend Features
Real-time sentiment analysis
Cold vs Warm detection badge
Confidence level indicator
Client-side performance dashboard
Optional recent history (privacy-aware)
Collapsible dashboard UI

### IaC (Infrastructure as Code)
- **Tool**: Terraform
- **State Management**: Remote Backend using AWS S3 (`sentiment-demo-jambread-2026`)
- **Managed Resources**: 
  - AWS Lambda (Configuration & Memory Management)
  - AWS ECR (Container Registry Data)

### CI/CD Pipeline
- **Tool**: GitHub Actions
- **Workflow**:
  1. **Infrastructure Update**: Automatically applies Terraform changes on push.
  2. **Containerization**: Builds Docker image and pushes to Amazon ECR.
  3. **Deployment**: Updates Lambda function code and configuration (Memory: 1024MB/2048MB).
- **Build Performance**: Average deployment time ~5m 40s.

### Troubleshooting Experience
- Resolved AWS IAM Permissions Boundary issues related to S3/Lambda access.
- Managed S3 Bucket Region mismatch (ap-northeast-2 vs us-east-1) during Backend migration.

### Real-time Monitoring & Notifications
- **Tool**: Discord Webhook Integration
- **Feature**: Automated deployment status reports.
- **Details**: 
  - Sends real-time notifications to Discord upon GitHub Actions workflow completion (Success/Failure).
  - Includes deployment metadata: Commits, Author, Workflow status, and direct links to Action logs.
  - Enables rapid feedback loops for the development team.

#  Serverless Sentiment Analysis Demo (KoELECTRA)

이 프로젝트는 AWS Lambda와 S3를 활용하여 영화 리뷰 감성 분석(NSMC)을 수행하는 서버레스 데모입니다.

## 기술 스택
- **Model**: `daekeun-ml/koelectra-small-v3-nsmc`
- **Infrastructure**: AWS Lambda (2048MB), S3, API Gateway
- **Backend**: FastAPI, Mangum, Transformers

---

## 중요 트러블슈팅 기록 (필독)

### 1. S3 모델 파일 구성 및 명칭
Lambda의 `/tmp` 공간으로 다운로드할 때 파일명이 고정되어 있어야 합니다. S3 버킷의 `temp_model/` 폴더 내에 아래 이름으로 파일이 존재해야 합니다.
- `model_config.json` (기존 config.json)
- `model_model.safetensors` (기존 model.safetensors)
- `model_tokenizer.json`
- `model_tokenizer_config.json`
- `model_vocab.txt` (매우 중요: ElectraTokenizer 작동을 위해 필수)

### 2. Windows 11 환경 설정 (개발 환경)
Windows 11 업그레이드 후 `python` 실행 시 MS Store가 열리거나 반응이 없는 경우:
- **앱 실행 별칭 관리**: `python.exe` 및 `python3.exe`를 '끄기'로 설정.
- **실행 권장**: `python` 대신 `py` 커맨드를 사용하거나, 실제 설치 경로(AppData 내)를 직접 사용하여 라이브러리를 설치하십시오.
- **인코딩**: 한글 주석이 포함된 `.py` 파일은 반드시 **UTF-8**로 저장해야 `SyntaxError`를 방지할 수 있습니다.

### 3. 모델 로딩 로직 (app.py)
`AutoTokenizer` 사용 시 패키지 버전 충돌로 `ValueError`가 발생할 수 있습니다. 이 경우 `ElectraTokenizer`를 명시적으로 호출하고, S3에서 받은 `vocab.txt`를 직접 참조하도록 구성했습니다.

---

##  로컬 환경 설정
1. 필요한 라이브러리 설치:
   ```bash
   py -m pip install transformers torch huggingface_hub

## 📊 Real-time Monitoring & Database
이 프로젝트는 서비스 성능 모니터링 및 모델의 판단 경향성 분석을 위해 **Privacy-First** 로그 파이프라인을 구축했습니다.

- [cite_start]**Storage**: Amazon DynamoDB (`SentimentAnalysisLog` 테이블) [cite: 12]
- **Data Schema**:
    - `requestId`: 고유 식별자 (UUID)
    - `timestamp`: 추론 시점 (Unix Timestamp, Number 타입)
    - `label`: 감성 분석 결과 (POSITIVE / NEGATIVE / NEUTRAL)
    - `confidence`: 모델 신뢰도 (Decimal 타입)
    - `latency_ms`: 처리 지연 시간
- **Privacy Design**: 사용자의 원문 텍스트(Raw Text)는 절대 저장하지 않으며, 분석 결과값(Metadata)만 수집하여 보안성을 강화했습니다.

### 4. Docker 기반 Lambda 배포 이슈 (CI/CD)
- [cite_start]**현상**: Git Push만으로 Lambda 코드가 갱신되지 않는 문제 발생. [cite: 5]
- [cite_start]**원인**: 컨테이너 방식은 이미지 빌드(Build) -> ECR 푸시(Push) -> 함수 업데이트(UpdateFunctionCode) 과정이 필수적임. [cite: 5]
- **해결**: AWS CLI를 이용해 최신 ECR 이미지를 배포(Deploy)하도록 프로세스를 정립함.

### 5. DynamoDB 데이터 타입 불일치 (ValidationException)
- **현상**: `PutItem` 실행 시 `Type mismatch for key timestamp` 에러 발생.
- **원인**: DynamoDB 테이블 생성 시 `timestamp`를 숫자(N)로 설정했으나, Python 코드에서 문자열로 전송함.
- [cite_start]**해결**: 기존 테이블을 삭제 후 정렬 키(Sort Key) 타입을 숫자로 재설계하여 쿼리 효율성(범위 검색 및 정렬)을 최적화함. [cite: 4]

## 기술 스택 (Updated)
- **Database**: Amazon DynamoDB (NoSQL)
- [cite_start]**Container**: Docker, Amazon ECR 
- [cite_start]**Language**: Python 3.12, FastAPI [cite: 12, 15]
- [cite_start]**Monitoring**: CloudWatch, Discord Webhook [cite: 8, 9]