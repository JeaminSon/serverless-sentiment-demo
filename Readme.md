# Serverless Korean Sentiment Analysis (KoELECTRA)
AWS Lambda + Docker + Streamlit 실시간 모니터링 시스템


##  Live Demo
Web UI (S3/CloudFront): https://d1s8pxdb9ftrht.cloudfront.net
Real-time Dashboard (Streamlit)**: https://serverless-sentiment-demo-djgk5apqhnssqc9dtsgnr3.streamlit.app/
API Endpoint**: https://u1i1chh9h5.execute-api.ap-northeast-2.amazonaws.com/

---

## System Architecture
사용자 요청부터 분석 결과의 시각화까지 이어지는 전체 데이터 흐름입니다.

1.  Frontend: S3 Static Hosting과 CloudFront(CDN)를 통해 빠르고 안정적인 UI 제공 
2.  Inference Engine: AWS Lambda 위에서 Docker 컨테이너로 작동하는 FastAPI 서버
3.  Model: `daekeun-ml/koelectra-small-v3-nsmc` 모델을 활용한 감성 분류 
4.  Database: 분석 결과 메타데이터를 Amazon DynamoDB에 실시간 저장 
5.  Monitoring: Streamlit Cloud를 활용하여 DynamoDB의 데이터를 실시간 차트로 시각화 

---

## Real-time Monitoring & Dashboard
서비스 성능 모니터링 및 모델의 판단 경향성 분석을 위해 Privacy-First 로그 파이프라인을 구축했습니다.

Privacy Design: 사용자의 원문 텍스트(Raw Text)는 절대 저장하지 않으며, 결과값(Label, Confidence)과 성능 지표(Latency)만 수집하여 보안성을 강화했습니다.
Infrastructure Separation:
    Lambda (Backend): 무거운 딥러닝 라이브러리(`torch`, `transformers`)를 포함한 최적화된 컨테이너 환경 
    Dashboard (Frontend): 시각화 라이브러리(`pandas`, `plotly`)만 사용하여 빌드 속도 및 운영 효율 극대화 (약 10초 내 빌드 완료)
Key Metrics: 총 분석 횟수, 평균 응답 속도(ms), 감성 분포 비중(Pie Chart), 시간별 지연 시간 추이(Line Chart). 

---

## Tech Stack
Model: `daekeun-ml/koelectra-small-v3-nsmc` 
Language: Python 3.12 
Framework: FastAPI, Mangum 
Infrastructure: AWS (Lambda, ECR, S3, CloudFront, DynamoDB) 
CI/CD: GitHub Actions, Terraform (IaC) 
Monitoring: Streamlit Cloud, Discord Webhook 

---

## CI/CD Pipeline & Operations
GitHub에 코드를 Push하면 인프라 업데이트부터 배포까지 자동으로 진행됩니다. 

1.  Infrastructure Update: Terraform을 통해 AWS 리소스 설정 및 메모리(2048MB) 자동 관리 
2.  Containerization: Docker 이미지를 빌드하여 Amazon ECR에 푸시 
3.  Deployment: 최신 이미지로 Lambda 함수 코드 및 설정 자동 업데이트 
4.  Notification: Discord Webhook을 통해 배포 메타데이터(커밋, 작성자, 상태) 실시간 알림 

---
## ⚡ Performance Optimization (ONNX)
* **Cold Start**: ~10s ➔ **~0.1s (100배 개선)**
* **Warm Start**: ~28ms ➔ **~5ms (5배 개선)**
* **Build Time**: ~5m 40s ➔ **~2m 36s (2배 개선)**
* **Optimization**: PyTorch 모델을 ONNX Runtime으로 전환하여 의존성 경량화 및 추론 속도 최적화 달성
