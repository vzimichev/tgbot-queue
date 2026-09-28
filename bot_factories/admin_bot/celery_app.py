from bot_factories.admin_bot.telegram_routes import admin_router, notify_child_claim
from bot_factories.admin_bot.repository import process_claim_updates
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(router=admin_router)
celery_app.conf.beat_schedule = {
    "poll-managed-bot-claims": {
        "task": "admin.poll_claim_updates",
        "schedule": 3.0,
    }
}


@celery_app.task(name="admin.poll_claim_updates")
def poll_claim_updates():
    return {"processed": process_claim_updates(notify_child_claim)}
