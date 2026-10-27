"""Запуск планировщика в единственном Gunicorn worker."""

from compass.worker import start_worker
import os


def post_worker_init(worker):
    if os.environ.get("COMPASS_DISABLE_WORKER") != "1":
        start_worker(worker.wsgi)
