import importlib
from types import SimpleNamespace
from unittest.mock import Mock

from worker.celery_factory import CeleryFactory


def test_celery_app_registers_admin_tasks(monkeypatch):
    app = SimpleNamespace(conf=SimpleNamespace())
    create_app = Mock(return_value=app)
    monkeypatch.setattr(CeleryFactory, "create_app", create_app)

    module = importlib.import_module("bot_factories.admin_bot.celery_app")
    module = importlib.reload(module)

    create_app.assert_called_with(router=module.admin_router)
    assert module.celery_app is app
    assert app.conf.imports == ("bot_factories.admin_bot.tasks",)
