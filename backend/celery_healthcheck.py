import os
import subprocess
import socket

hostname = socket.gethostname()
command = f"celery -A moio_bot status | grep celery@{hostname}"

try:
    subprocess.run(command, shell=True, check=True)
    exit(0)  # Healthy
except subprocess.CalledProcessError:
    exit(1)  # Unhealthy