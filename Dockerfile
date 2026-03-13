FROM public.ecr.aws/lambda/python:3.12 AS builder

RUN dnf install -y gcc-c++

COPY requirements.txt .
RUN pip install --no-cache-dir --target /install -r requirements.txt

COPY download_model.py .
RUN python download_model.py

FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder /install /var/task

COPY --from=builder /var/task/model /var/task/model

COPY app.py .
CMD ["app.handler"]