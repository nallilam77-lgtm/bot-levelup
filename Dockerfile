FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy
# tini como proceso principal: recoge los procesos de Chromium que terminan. Sin él quedaban como
# "zombis", se acumulaban y el contenedor no podía abrir más ("[Errno 11] Resource temporarily unavailable").
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
