import os

from flake8.main import application

CONFIG_PATH = os.path.dirname(__file__)


def run_flake8():
    app = application.Application()
    app.initialize(
        [
            f"--config={CONFIG_PATH}/.flake8",
            "--extend-exclude=test/integration/,test/unit/,test/e2e/,"
            "test/__init__.py,test/conftest.py,conftest.py"
        ]
    )
    app.run_checks()
    app.report()
