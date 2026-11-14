import importlib


def test_celery_app_registers_only_managed_tasks():
    module = importlib.import_module("bot_factories.managed_bot.celery_app")
    module = importlib.reload(module)

    assert module.celery_app.conf.imports == ("bot_factories.managed_bot.tasks",)
