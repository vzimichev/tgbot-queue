from worker.celery_app import celery_app

# Optional entry point to run worker programmatically
if __name__ == "__main__":
    celery_app.worker_main(["worker", "--loglevel=info"])
