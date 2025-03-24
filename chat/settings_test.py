from .settings import *

# 테스트용 데이터베이스 설정 (SQLite 사용)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",  # In-memory SQLite 데이터베이스
    }
}

# 테스트용 채널 레이어 설정 (In-Memory Channel Layer 사용)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# 캐시 설정 (로컬 메모리 캐시 사용)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# 테스트 속도 향상을 위한 설정
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# 테스트용 미디어 파일 설정
MEDIA_ROOT = "/tmp/test_media/"

# 테스트용 이메일 백엔드
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
