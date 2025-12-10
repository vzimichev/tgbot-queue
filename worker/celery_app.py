from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app()
