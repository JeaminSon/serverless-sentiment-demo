FROM public.ecr.aws/lambda/python:3.12 AS builder

COPY requirements_lambda.txt
RUN pip install --no-cache-dir -r requirements.txt --target .

COPY app.py .
CMD ["app.handler"]