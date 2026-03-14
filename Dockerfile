FROM public.ecr.aws/lambda/python:3.12 AS builder

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir --target /install -r requirements.txt

COPY download_model.py .
RUN python download_model.py

FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

COPY --from=builder /var/lang/lib/python3.12/site-packages /var/lang/lib/python3.12/site-packages
COPY --from=builder /var/task /var/task

COPY app.py .
CMD ["app.handler"]