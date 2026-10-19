"""One background worker per database; independent scheduler and delivery loops."""

import threading
import time
from compass.delivery import reminders_and_escalations, dispatch_push
from compass.telegram_bot import tick_telegram


def _loop(app, operation, interval, label):
    while True:
        try:
            with app.app_context():
                operation()
        except Exception as error:
            # External exceptions can contain secret-bearing URLs. Log type only.
            app.logger.warning("%s worker: %s", label, type(error).__name__)
        time.sleep(interval)


def start_worker(app):
    threads = []
    for operation, interval, label in [
        (reminders_and_escalations, 10, "scheduler"),
        (dispatch_push, 5, "push"),
        (tick_telegram, 5, "telegram"),
    ]:
        thread = threading.Thread(
            target=_loop,
            args=(app, operation, interval, label),
            daemon=True,
            name="compass-" + label,
        )
        thread.start()
        threads.append(thread)
    return threads[0]


if __name__ == "__main__":
    from app import create_app

    start_worker(create_app()).join()
