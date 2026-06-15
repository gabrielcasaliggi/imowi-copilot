FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/
COPY main.py index.html config.js ./
COPY Base_de_Conocimiento_Tickets.md ./

# Volumen persistente solo si usás SQLite local en Docker (dev)
# En producción con DATABASE_URL=PostgreSQL no hace falta disco en Render
ENV DATA_DIR=/app/data
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

# Render inyecta $PORT — no hardcodear 8000 en producción
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
