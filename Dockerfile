FROM public.ecr.aws/lambda/python:3.12 AS builder

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target .

COPY download_model.py .
RUN python download_model.py

FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

COPY --from=builder /var/task /var/task

COPY app.py .
CMD ["app.handler"]