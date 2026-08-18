FROM python:3.12-slim

WORKDIR /workspace
RUN pip install --no-cache-dir \
  "alembic>=1.14,<2.0" \
  "aiohttp>=3.10,<4.0" \
  "argon2-cffi>=23.1,<24.0" \
  "fastapi>=0.115,<1.0" \
  "itsdangerous>=2.2,<3.0" \
  "psycopg[binary]>=3.2,<4.0" \
  "prometheus-client>=0.21,<1.0" \
  "redis>=5.2,<6.0" \
  "SQLAlchemy>=2.0,<3.0" \
  "uvicorn[standard]>=0.30,<1.0"
COPY apps/control-api/app ./app
COPY apps/gateway/gateway ./gateway
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8080 8090
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
