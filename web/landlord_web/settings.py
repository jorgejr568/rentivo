import os
from pathlib import Path

from landlord.db import _get_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "LANDLORD_SECRET_KEY",
    "django-insecure-change-me-in-production",
)

DEBUG = os.environ.get("LANDLORD_DEBUG", "true").lower() in ("true", "1", "yes")

_raw_hosts = os.environ.get("LANDLORD_ALLOWED_HOSTS", "*")
# Strip scheme if provided (e.g. "https://example.com" -> "example.com")
ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = []
for h in _raw_hosts.split(","):
    h = h.strip()
    if not h:
        continue
    if h.startswith("https://") or h.startswith("http://"):
        CSRF_TRUSTED_ORIGINS.append(h)
        ALLOWED_HOSTS.append(h.split("://", 1)[1])
    else:
        ALLOWED_HOSTS.append(h)
        if h != "*":
            CSRF_TRUSTED_ORIGINS.append(f"https://{h}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "landlord_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "landlord_web.wsgi.application"

# Use the same database as the CLI app — resolve paths relative to project root
_PROJECT_ROOT = BASE_DIR.parent
_db_url = _get_url()
if _db_url.startswith("sqlite"):
    _db_path = _db_url.replace("sqlite:///", "")
    if not os.path.isabs(_db_path) or not os.path.exists(_db_path):
        # Re-resolve from project root (handles CWD being web/)
        from landlord.settings import settings as _ls
        _db_path = str(_PROJECT_ROOT / _ls.db_path)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _db_path,
        }
    }
else:
    # MariaDB/MySQL
    from urllib.parse import urlparse

    parsed = urlparse(_db_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 3306),
        }
    }

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
