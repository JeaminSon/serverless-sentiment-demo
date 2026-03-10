FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. 모델 준비 (가장 에러 없는 방식)
# 만약 로컬에 model/ 폴더가 있다면 아래 줄을 쓰세요.
COPY model/ ./model/

# 만약 모델 폴더가 없고 스크립트를 실행해야 한다면 아래 두 줄을 쓰세요.
# COPY download_model.py .
# RUN python download_model.py

# 3. 소스 코드 복사
COPY app.py .

CMD ["app.handler"]