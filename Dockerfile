# Optional container build. Native install is recommended on Windows (see README),
# but this works anywhere Docker runs. Uses Microsoft's Playwright image so Chromium
# and its system libraries are already present.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
COPY pyproject.toml README.md ./
COPY pricewatch ./pricewatch
RUN pip install --no-cache-dir -e . && playwright install chromium

ENV PW_HOST=0.0.0.0 PW_PORT=8765 PW_DB_PATH=/data/pricewatch.db PW_PLAYWRIGHT_PROFILE_DIR=/data/browser-profile
VOLUME ["/data"]
EXPOSE 8765
CMD ["pricewatch", "serve"]
