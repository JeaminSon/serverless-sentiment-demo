FROM public.ecr.aws/lambda/python:3.12

# 기본 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델 다운로드 (빌드 시점에 실행)
COPY download_model.py .
RUN python download_model.py

# 앱 코드
COPY app.py .

# Lambda가 찾는 핸들러 지정
CMD ["app.handler"]