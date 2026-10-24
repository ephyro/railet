FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home railet && mkdir -p /app/private-media && chown railet:railet /app/private-media
USER railet
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
