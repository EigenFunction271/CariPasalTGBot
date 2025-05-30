# gunicorn_config.py
import os
import gevent.monkey

# --- Monkey-patch as early as possible ---
gevent.monkey.patch_all()
print("GUNICORN_CONFIG: gevent.monkey.patch_all() has been executed.")
# Attempt to explicitly ensure asyncio uses gevent's loop if patch_all didn't suffice.
# This might be redundant with modern gevent, but worth a try given the persistent loop issues.
try:
    import asyncio
    from gevent.hub import get_hub # gevent's main event loop
    
    # Create a new policy that uses gevent's hub as the asyncio loop
    # This is an advanced step and syntax might vary slightly with gevent versions
    # The goal is to make asyncio.get_event_loop() always return gevent's hub.
    # One common way gevent does this is by patching asyncio.selector_events._BaseSelectorEventLoop
    # If get_hub() is already the loop, this is fine.
    
    # Check if current default loop is already gevent's hub based
    # This is hard to check directly without knowing gevent internals deeply.
    # Modern gevent's patch_all is usually aggressive.
    
    # A less intrusive check and potential fix:
    # PTB creates its own Application that then gets an event loop.
    # If the default event loop obtained by PTB is not correctly gevent-patched,
    # that's where the problem lies.
    
    # For now, let's assume patch_all() is doing its job, as the loop *reports* as running.
    # The issue is more subtle than the loop simply not being set.
    
except Exception as e:
    print(f"GUNICORN_CONFIG_WARNING: Exception during advanced gevent/asyncio policy setup: {e}")



# --- Gunicorn Settings ---
port = os.getenv('PORT', '10000') # Default to 10000 or whatever Render actually provides
bind = f"0.0.0.0:{port}"
worker_class = "gevent"
# workers = int(os.getenv('WEB_CONCURRENCY', 2)) # Example
# loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info')
workers = 1 # KEEP THIS AT 1 FOR DEBUGGING a-sync issues like this
print(f"GUNICORN_CONFIG: Loaded. Settings: bind='{bind}', worker_class='{worker_class}', workers={workers}")


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