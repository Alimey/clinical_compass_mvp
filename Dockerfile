FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --create-home compass && mkdir /data && chown compass:compass /data
COPY --chown=compass:compass app.py .
COPY --chown=compass:compass static ./static
USER compass
ENV COMPASS_DB=/data/compass.db
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app:create_app()"]
