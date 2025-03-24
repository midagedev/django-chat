# Django Chat Application

Django 기반의 실시간 채팅 애플리케이션입니다. Django Channels를 사용하여 WebSocket 통신을 구현했습니다.

## 기술 스택

- Python 3.11+
- Django 5.0+
- Django Channels 4.0+
- Django REST Framework 3.15+
- PostgreSQL 15
- Redis 7
- Docker & Docker Compose

## 설치 방법

### 개발 환경 설정

1. Python 3.11 이상 설치

2. uv 패키지 매니저 설치
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. 의존성 설치
```bash
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install --no-cache -r pyproject.toml
```

### Docker를 사용한 실행

```bash
docker compose up
```

서버는 http://localhost:8000 에서 실행됩니다.

## 환경 변수

프로젝트 실행을 위해 다음 환경 변수가 필요합니다:

- `DATABASE_URL`: PostgreSQL 데이터베이스 연결 문자열
- `REDIS_URL`: Redis 서버 연결 문자열
- `DJANGO_SETTINGS_MODULE`: Django 설정 모듈 경로

## 개발 도구

- Ruff: 코드 린팅 및 포맷팅
- Pytest: 테스트 실행

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
