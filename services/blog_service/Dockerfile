FROM python:3.11-slim

WORKDIR /app

# 필요한 패키지 설치
RUN apt-get update && apt-get install -y build-essential libssl-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# cryptography 설치 포함
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install cryptography

RUN pip install fastapi sqlmodel asyncmy redis httpx

COPY ./app .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
