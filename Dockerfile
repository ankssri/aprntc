# aprntc — single-container deploy: build the React frontend, serve it + the API
# from FastAPI/uvicorn. Multi-stage so the final image has no Node toolchain.

# ---- stage 1: build the frontend ----
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build          # -> /web/dist

# ---- stage 2: python runtime ----
FROM python:3.12-slim AS app
WORKDIR /app

# install the package (+ web extra) first for layer caching
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e '.[web,byteplus]'

# bring in the built frontend; APRNTC_STATIC_DIR points the app at it
COPY --from=web /web/dist ./web/dist
ENV APRNTC_STATIC_DIR=/app/web/dist

# runtime config (override at deploy): keys via env / mounted .env, data dir for
# SQLite + per-tenant namespaces.
ENV APRNTC_DB_URL=sqlite:////data/aprntc.db
VOLUME ["/data"]
EXPOSE 8000

# serve API + static UI on one port
CMD ["python", "-m", "uvicorn", "aprntc.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
