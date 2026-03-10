FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY download_model.py .
RUN python download_model.py

# 3. 소스 코드 복사
COPY app.py .

CMD ["app.handler"]