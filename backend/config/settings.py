"""BaseMgt 平台配置。

所有环境相关参数通过项目根目录的 .env 读取（见 .env.example）。
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR
PROJECT_ROOT = BASE_DIR.parent

# 让 apps 可以直接以 apps.xxx 方式导入
sys.path.insert(0, str(BACKEND_DIR))


def _load_dotenv():
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env_bool(name, default=False):
    return os.environ.get(name, "1" if default else "0") not in ("0", "", "false", "False")


SECRET_KEY = os.environ.get("BM_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = env_bool("BM_DEBUG", True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.core",
    "apps.iam",
    "apps.mdm",
    "apps.catalog",
    "apps.orchestration",
    "apps.page",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("BM_DB_NAME", "basemgt"),
        "USER": os.environ.get("BM_DB_USER", "basemgt"),
        "PASSWORD": os.environ.get("BM_DB_PASSWORD", ""),
        "HOST": os.environ.get("BM_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("BM_DB_PORT", "5433"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    # 各 ViewSet 均显式指定 permission_classes（apps.iam.permissions），
    # 这里只对未显式声明的接口（如 /api/health）生效
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# ---- BaseMgt 自有配置 ----
# 为 1 时关闭接口鉴权（未登录按管理员处理），仅建议本地开发
BM_AUTH_DISABLED = env_bool("BM_AUTH_DISABLED", True)
# 是否允许编排中出现 python 脚本节点（可执行任意代码）
BM_ENABLE_SCRIPT_NODE = env_bool("BM_ENABLE_SCRIPT_NODE", True)
# 单次运行最大节点执行步数，防止死循环
BM_MAX_RUN_STEPS = int(os.environ.get("BM_MAX_RUN_STEPS", "2000"))
# 单节点执行超时（秒），0 表示不限制
BM_NODE_TIMEOUT = int(os.environ.get("BM_NODE_TIMEOUT", "0"))
# 数据源连接缓存时长（秒）
BM_CONN_TTL = int(os.environ.get("BM_CONN_TTL", "300"))
# SQL 控制台是否允许写操作（INSERT/UPDATE/DELETE）；DDL 一律禁止
BM_SQL_CONSOLE_WRITE = env_bool("BM_SQL_CONSOLE_WRITE", False)
# 单节点 SQL 语句超时（毫秒），0 表示不限制
BM_SQL_TIMEOUT_MS = int(os.environ.get("BM_SQL_TIMEOUT_MS", "30000"))
# 单次运行整体超时（秒），0 表示不限制
BM_RUN_TIMEOUT = int(os.environ.get("BM_RUN_TIMEOUT", "0"))
# 异步运行：1 时 /api/.../run 立即返回，由 worker 后台执行
BM_ASYNC_RUN = env_bool("BM_ASYNC_RUN", True)
