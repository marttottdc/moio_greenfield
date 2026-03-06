bind = ["0.0.0.0:9000"]
worker_class = 'uvloop'  # Use uvloop for improved performance
worker_connections = 1000
workers = 1
accesslog = '-'  # Log to stdout
errorlog = '-'  # Log errors to stdout
loglevel = 'debug'

max_requests = 1000  # recycle before leaks pile up
max_requests_jitter = 100  # stagger restarts
graceful_timeout = 30
