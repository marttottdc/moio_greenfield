from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parent.parent
TLS_DIR = ROOT_DIR / ".local" / "certs"
TLS_CERT_FILE = Path(os.getenv("LOCAL_TLS_CERT_FILE", TLS_DIR / "localhost-cert.pem"))
TLS_KEY_FILE = Path(os.getenv("LOCAL_TLS_KEY_FILE", TLS_DIR / "localhost-key.pem"))

bind = [f"0.0.0.0:{os.getenv('BACKEND_PORT', '8093')}"]
worker_class = "uvloop"  # Use uvloop for improved performance
worker_connections = 1000
workers = 1
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log errors to stdout
loglevel = "debug"

max_requests = 1000  # recycle before leaks pile up
max_requests_jitter = 100  # stagger restarts
graceful_timeout = 30

if TLS_CERT_FILE.exists() and TLS_KEY_FILE.exists():
    certfile = str(TLS_CERT_FILE)
    keyfile = str(TLS_KEY_FILE)
