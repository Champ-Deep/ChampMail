from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import os

celery_broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "champmail",
    broker=celery_broker_url,
    backend=celery_result_backend,
    include=[
        "app.tasks.sending",
        "app.tasks.sequences",
        "app.tasks.warmup",
        "app.tasks.domains",
        "app.tasks.bounces",
        "app.tasks.analytics",
        "app.tasks.campaign_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    worker_prefetch_multiplier=1,
    task_queues=[
        Queue("default", routing_key="default"),
        Queue("sending", routing_key="sending"),
        Queue("sequences", routing_key="sequences"),
        Queue("warmup", routing_key="warmup"),
        Queue("domain", routing_key="domain"),
    ],
    beat_schedule={
        "execute-sequence-steps": {
            "task": "app.tasks.sequences.execute_pending_steps",
            "schedule": crontab(minute="*/5"),
            "options": {"queue": "sequences"},
        },
        "warmup-daily-sends": {
            "task": "app.tasks.warmup.execute_warmup_sends",
            "schedule": crontab(hour=9, minute=0),
            "options": {"queue": "warmup"},
        },
        "check-domain-health": {
            "task": "app.tasks.domains.check_all_domain_health",
            "schedule": crontab(hour="*/6"),
            "options": {"queue": "domain"},
        },
        "process-bounces": {
            "task": "app.tasks.bounces.process_bounce_queue",
            "schedule": crontab(minute="*/10"),
            "options": {"queue": "sending"},
        },
        "aggregate-daily-stats": {
            "task": "app.tasks.analytics.aggregate_daily_stats",
            "schedule": crontab(hour=23, minute=55),
            "options": {"queue": "default"},
        },
    },
)


if __name__ == "__main__":
    celery_app.start()