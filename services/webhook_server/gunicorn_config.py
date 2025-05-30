import os

# --- Gunicorn Settings ---
port = os.getenv('PORT', '10000')
bind = f"0.0.0.0:{port}"
worker_class = "uvicorn.workers.UvicornWorker"  # Using Uvicorn worker for ASGI support
workers = 1  # Single worker for webhook server
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