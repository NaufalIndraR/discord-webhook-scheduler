FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout/stderr for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Default execution using main.py
CMD ["python", "main.py"]

