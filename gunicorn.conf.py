"""
Gunicorn settings, picked up automatically from the working directory — so
they apply to the Render service whatever its dashboard start command is
(the service was created via Render's API, not from render.yaml, so
render.yaml's startCommand isn't what runs). A flag passed on the command
line still wins over a value here.

Without this file gunicorn runs ONE sync worker: every request queues behind
the one before it. Measured on the live service (2026-09-14): six parallel
GET /api/health/ answered at 1.7s, 3.3s, 5.0s, 6.6s, 8.1s and 9.8s. A single
frontend page fans out 3-6 backend calls at once, so pages queued behind
each other and a cold start could push a render past Vercel's 60s limit.

Nearly all of a request's time here is spent waiting on the network (Neon
Postgres, the Notion API), not on CPU, so threads in one process fix the
queueing without the memory cost of more worker processes on a 512MB free
instance.
"""
import os

worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
threads = int(os.environ.get("GUNICORN_THREADS", 8))
# Heartbeat for the worker process, not a per-request cap under gthread; a
# slow Notion write-back must not get the worker killed and 502 the request.
timeout = 60
