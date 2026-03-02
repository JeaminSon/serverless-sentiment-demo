FROM public.ecr.aws/lambda/python:3.12

# 기본 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델 다운로드 (빌드 시점에 실행)
COPY download_model.py .
RUN python download_model.py

# 앱 코드
COPY app.py .

# FastAPI를 Lambda에서 돌리기 위해 Mangum 사용 (가장 간단한 호환 방법)
RUN pip install --no-cache-dir mangum==0.17.0

# Lambda 핸들러 파일 생성
RUN python - <<'PY'
from mangum import Mangum
import app
handler = Mangum(app.app)
import pickle, os
PY

# Lambda가 찾는 핸들러 지정
CMD ["app.handler"]