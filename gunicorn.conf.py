"""Default Render startup also enables the notification scheduler."""

import os
from compass.gunicorn_conf import post_worker_init

bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
workers = 1
threads = 4
