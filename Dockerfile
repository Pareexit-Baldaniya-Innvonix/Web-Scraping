FROM python:3.12-slim

LABEL org.opencontainers.image.title="amazon-scraper" \
      org.opencontainers.image.description="FastAPI + Playwright Amazon.in product/search/reviews scraper with web dashboard"

# ----- Environment -----
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# ----- System Packages -----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        git && \
    rm -rf /var/lib/apt/lists/*

# ----- Python Dependencies -----
COPY Pipfile Pipfile.lock ./

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --system --deploy --ignore-pipfile && \
    pip uninstall -y pipenv

# ----- Playwright -----
RUN playwright install --with-deps chromium

# ----- Copy Project -----
COPY . .

# ----- Runtime Directories -----
RUN mkdir -p \
        logs \
        output/reviews \
        output/searches \
        src/amazon_user_session

# ----- Non-root User -----
RUN groupadd --system appuser && \
    useradd --system \
        --gid appuser \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        appuser && \
    chown -R appuser:appuser /app /ms-playwright

USER appuser

EXPOSE 8000

# ----- Start Application -----
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]