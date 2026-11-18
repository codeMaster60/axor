FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=8080
CMD gunicorn cloud:app --bind 0.0.0.0:$PORT --workers 2 --threads 4
