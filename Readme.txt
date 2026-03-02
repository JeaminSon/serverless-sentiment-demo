# Serverless Korean Sentiment Analysis (AWS Lambda + ECR + S3)

Korean sentiment analysis demo deployed as a serverless container on AWS Lambda.
A static web UI is hosted on S3 + CloudFront and calls the Lambda Function URL

## Demo
- Web (CloudFront): https://d1s8pxdb9ftrht.cloudfront.net
- API (Lambda Function URL): https://2r5xcr2sl7fdgiokzns35gfw5m0vmcuc.lambda-url.ap-northeast-2.on.aws/predict


## Architecture
Browser
  ↓
CloudFront (CDN)
  ↓
S3 Static Website (Frontend)
  ↓
Lambda Function URL
  ↓
FastAPI (Docker container)
  ↓
HuggingFace KoELECTRA model

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
⚠️ Note:
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

