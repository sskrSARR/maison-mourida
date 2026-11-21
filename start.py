import os
import subprocess
import sys
import time
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def run(args):
    subprocess.check_call([sys.executable, "manage.py", *args])


def wait_db():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        return
    import psycopg

    dsn = url.replace("postgres://", "postgresql://", 1)
    last = "inconnu"
    for _ in range(45):
        try:
            with psycopg.connect(dsn):
                return
        except Exception as exc:
            last = type(exc).__name__
            time.sleep(1)
    sys.exit(f"Base de données inaccessible ({last})")


if __name__ == "__main__":
    import make_icon

    make_icon.main()
    wait_db()
    if not os.environ.get("RENDER"):
        run(["makemigrations", "accounts", "catalog", "subscriptions", "orders", "payments", "notifications", "--noinput"])
    run(["migrate", "--noinput"])
    run(["seed"])
    run(["collectstatic", "--noinput"])
    port = os.environ.get("PORT", "8000")
    workers = "1" if os.environ.get("RENDER") else "2"
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "config.wsgi:application",
            "--bind",
            f"0.0.0.0:{port}",
            "--workers",
            workers,
            "--timeout",
            "60",
            "--access-logfile",
            "-",
        ],
    )
