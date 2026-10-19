"""Use with one Gunicorn worker per database; the worker hosts the scheduler."""

from compass.worker import start_worker


def post_worker_init(worker):
    start_worker(worker.wsgi)
