FROM python:3.11-slim

WORKDIR /app

# ગુજરાતી ફોન્ટ (ચોરસ ખાના દૂર કરવા) અને ffmpeg (મોબાઈલ માઈક ઓડિયો માટે) ઇન્સ્ટોલ કરો
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-core \
    fonts-noto-extra \
    ffmpeg \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p .files geo_cache

EXPOSE 7860

CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "7860"]
