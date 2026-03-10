FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY download_model.py .
RUN python download_model.py

COPY app.py .
CMD ["app.handler"]