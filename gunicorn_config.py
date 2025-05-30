# gunicorn_config.py
import os
import gevent.monkey

# --- Monkey-patch as early as possible ---
gevent.monkey.patch_all()
print("GUNICORN_CONFIG: gevent.monkey.patch_all() has been executed.")

# --- Gunicorn Settings ---
port = os.getenv('PORT', '10000') # Default to 10000 or whatever Render actually provides
bind = f"0.0.0.0:{port}"
worker_class = "gevent"
# workers = int(os.getenv('WEB_CONCURRENCY', 2)) # Example
# loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info')

print(f"GUNICORN_CONFIG: Loaded. Settings: bind='{bind}', worker_class='{worker_class}'")

# Explicitly set up Gunicorn hooks from app.py
def on_worker_boot(worker):
    from app import on_worker_boot as app_on_worker_boot
    print(f"GUNICORN_CONFIG: Calling app.on_worker_boot for worker PID {worker.pid if worker else 'N/A'}")
    if worker: # Gunicorn passes the worker object
        app_on_worker_boot(worker)

def worker_int(worker):
    from app import worker_int as app_worker_int
    print(f"GUNICORN_CONFIG: Calling app.worker_int for worker PID {worker.pid if worker else 'N/A'}")
    if worker:
        app_worker_int(worker)

def worker_abort(worker):
    from app import worker_abort as app_worker_abort
    print(f"GUNICORN_CONFIG: Calling app.worker_abort for worker PID {worker.pid if worker else 'N/A'}")
    if worker:
        app_worker_abort(worker)