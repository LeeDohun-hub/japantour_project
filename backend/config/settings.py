"""Django settings — Japan Tour API + 정적 프론트."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = BASE_DIR.parent
load_dotenv(_REPO_ROOT / ".env", encoding="utf-8")

# src/ package는 프로젝트 루트에 있으므로 sys.path에 추가
_REPO_ROOT_STR = str(_REPO_ROOT)
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("1", "true", "yes")

_secret_key_env = os.environ.get("DJANGO_SECRET_KEY", "")
if not _secret_key_env:
    if DEBUG:
        _secret_key_env = "django-insecure-dev-only-not-for-production"
    else:
        raise ValueError(
            "DJANGO_SECRET_KEY 환경변수가 설정되지 않았습니다. "
            "프로덕션 배포 전에 반드시 설정하세요: "
            "python -c \"import secrets; print(secrets.token_hex(50))\""
        )
SECRET_KEY = _secret_key_env

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "faiss").strip().lower()

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "tour_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES: list = []

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8시간

# CSRF_TRUSTED_ORIGINS: 운영 도메인을 쉼표로 구분해서 환경변수에 설정
# 예) CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
_trusted_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if _trusted_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _trusted_origins.split(",") if o.strip()]

if not DEBUG:
    # 프로덕션 전용 보안 헤더
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

if DEBUG:
    # 개발 환경: 인메모리 캐시 세션 → runserver 재시작 시 자동 로그아웃
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"

def _build_database_config() -> dict:
    engine = os.environ.get("DB_ENGINE", "sqlite").strip().lower()

    if engine in {"postgres", "postgresql", "django.db.backends.postgresql"}:
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "japantour"),
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
        sslmode = os.environ.get("POSTGRES_SSLMODE", "").strip()
        if sslmode:
            config["OPTIONS"] = {"sslmode": sslmode}
        return config

    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


DATABASES = {"default": _build_database_config()}

STATIC_URL = "static/"
FRONTEND_DIR = _REPO_ROOT / "frontend"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "src": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "tour_api": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
