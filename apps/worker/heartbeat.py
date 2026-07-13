import os
import tempfile
from pathlib import Path

from celery.signals import heartbeat_sent, worker_ready, worker_shutdown

# Cross-platform temp directory for heartbeat/ready files
TMP_DIR = os.path.join(tempfile.gettempdir(), "maxkb-celery")
os.makedirs(TMP_DIR, exist_ok=True)


@heartbeat_sent.connect
def heartbeat(sender, **kwargs):
    worker_name = sender.eventer.hostname.split("@")[0]
    heartbeat_path = Path(TMP_DIR) / f"worker_heartbeat_{worker_name}"
    heartbeat_path.touch()


@worker_ready.connect
def worker_ready(sender, **kwargs):
    worker_name = sender.hostname.split("@")[0]
    ready_path = Path(TMP_DIR) / f"worker_ready_{worker_name}"
    ready_path.touch()


@worker_shutdown.connect
def worker_shutdown(sender, **kwargs):
    worker_name = sender.hostname.split("@")[0]
    for signal in ["ready", "heartbeat"]:
        path = Path(TMP_DIR) / f"worker_{signal}_{worker_name}"
        path.unlink(missing_ok=True)
