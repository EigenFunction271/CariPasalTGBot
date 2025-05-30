# gunicorn_config.py
import os
import gevent.monkey

# --- Monkey-patch as early as possible ---
# This should be one of the very first things executed when Gunicorn starts a worker.
gevent.monkey.patch_all()
print("GUNICORN_CONFIG: gevent.monkey.patch_all() has been executed.") # For log confirmation

# --- Gunicorn Settings ---
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
worker_class = "gevent"
# workers = int(os.getenv('WEB_CONCURRENCY', 2)) # Example: Adjust as needed
# loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info') # Useful for Gunicorn's own logs

# If your Gunicorn hooks (like on_worker_boot) are defined in app.py,
# Gunicorn will still pick them up when it loads app:app.
# This config file is primarily for settings and early setup like patching.

print(f"GUNICORN_CONFIG: Loaded. Settings: bind='{bind}', worker_class='{worker_class}'")

# Optional: If you want to explicitly define hooks here, you could,
# but it's often cleaner to keep them in app.py if Gunicorn finds them.
# Example of how you might re-export if needed, or define them here:
# from app import on_worker_boot # Ensure app.py doesn't cause circular imports or premature loads

print(f"GUNICORN_CONFIG: os.environ['PORT'] = {os.environ.get('PORT')}")
