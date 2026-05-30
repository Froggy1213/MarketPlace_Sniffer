FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

RUN uv run playwright install chromium

COPY . .

# 1. Создаем системного пользователя 'appuser' без админских прав
RUN useradd -m -d /app -s /bin/bash appuser

# 2. Указываем Playwright скачивать браузеры в папку нашего пользователя
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

# 3. Передаем права на все файлы проекта новому пользователю
RUN chown -R appuser:appuser /app

# 4. Переключаемся на безопасного пользователя
USER appuser

# 5. Устанавливаем Chromium от имени appuser
RUN uv run playwright install chromium

CMD ["uv", "run", "python", "main.py"]