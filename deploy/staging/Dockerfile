FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=railet.staging
WORKDIR /app
COPY requirements.txt requirements-staging.txt ./
RUN pip install --no-cache-dir -r requirements-staging.txt && useradd --create-home railet && mkdir -p /app/private-media && chown railet:railet /app /app/private-media
COPY --chown=railet:railet manage.py ./
COPY --chown=railet:railet railet ./railet
COPY --chown=railet:railet core ./core
COPY --chown=railet:railet inventory ./inventory
COPY --chown=railet:railet customers ./customers
COPY --chown=railet:railet deals ./deals
COPY --chown=railet:railet documents ./documents
COPY --chown=railet:railet feedback ./feedback
COPY --chown=railet:railet finance ./finance
COPY --chown=railet:railet templates ./templates
COPY --chown=railet:railet static ./static
USER railet
CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn railet.wsgi:application --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile -"]
