# Sakan - WhatsApp lead agent for a Dubai brokerage.
#
# Multi-stage so the runtime image carries no build toolchain.

FROM python:3.11-slim AS build
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS runtime

# Run as a non-root user. A webhook endpoint is public by definition; it has no
# business running as root.
RUN useradd --create-home --uid 10001 sakan

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=build /opt/venv /opt/venv
COPY --chown=sakan:sakan app ./app
COPY --chown=sakan:sakan prompts ./prompts
COPY --chown=sakan:sakan agencies ./agencies

USER sakan
EXPOSE 8123

# The container is unhealthy the moment the app stops answering, not merely when
# the process dies - a wedged event loop still has a live PID.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8123/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8123"]
