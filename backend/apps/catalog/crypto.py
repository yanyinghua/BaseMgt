"""数据源口令加密。

口令以 Fernet 密文（前缀 enc:）存库；未带前缀的历史明文仍可读取，
写入时一律加密。密钥由 settings.SECRET_KEY 派生——更换 SECRET_KEY 会导致
已存口令无法解密，需重新录入。
"""
import base64
import hashlib

from django.conf import settings

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "enc:"


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_password(raw):
    raw = raw or ""
    if not raw:
        return ""
    return ENC_PREFIX + _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_password(stored):
    stored = stored or ""
    if not stored.startswith(ENC_PREFIX):
        return stored  # 历史明文，兼容读取
    try:
        return _fernet().decrypt(stored[len(ENC_PREFIX):].encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
