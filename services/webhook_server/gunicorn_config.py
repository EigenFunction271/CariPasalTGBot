import os

# --- Gunicorn Settings ---
port = os.getenv('PORT', '10000')
bind = f"0.0.0.0:{port}"
worker_class = "gthread"  # Using threaded worker for Flask
workers = 1  # Single worker for webhook server
threads = 4  # Number of threads per worker
timeout = 30  # Increased timeout for webhook processing

# --- Logging ---
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stdout
loglevel = "info"

# --- Worker Settings ---
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# --- Application Settings ---
wsgi_app = "services.webhook_server.app:app" 