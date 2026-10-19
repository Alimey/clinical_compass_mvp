FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
# Optional CA bundle for builders behind a trusted HTTPS proxy. TLS stays enabled.
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.lock; \
    else pip install --no-cache-dir -r requirements.lock; fi
RUN useradd --create-home compass && mkdir /data && chown compass:compass /data
COPY --chown=compass:compass app.py .
COPY --chown=compass:compass static ./static
COPY --chown=compass:compass compass ./compass
USER compass
ENV COMPASS_DB=/data/compass.db
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app:create_app()"]
