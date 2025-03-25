# Django 실시간 채팅 시스템

Django와 Channels를 활용한 확장성 있는 실시간 채팅 애플리케이션입니다. WebSocket을 통한 양방향 통신으로 즉각적인 메시지 전송과 상태 업데이트를 제공합니다.

## 시스템 개요

이 애플리케이션은 다음 요구사항을 충족하도록 설계되었습니다:

- 실시간 양방향 메시지 통신
- 1:1 채팅 및 그룹 채팅(최대 100명) 지원
- 웹/앱 크로스 플랫폼 지원을 위한 RESTful API
- 사용자 온라인 상태 실시간 표시
- 메시지 기록 저장 및 조회
- 대규모 사용자 처리를 위한 확장성 고려

## 아키텍처

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  클라이언트  │     │   Django    │     │             │
│  (웹/앱)     │◄───►│  Channels   │◄───►│   Redis     │
└─────────────┘     │  (WebSocket) │     │             │
                    └─────────────┘     └─────────────┘
                           │                   ▲
                           ▼                   │
                    ┌─────────────┐     ┌─────────────┐
                    │   Django    │     │             │
                    │  REST API   │◄───►│ PostgreSQL  │
                    └─────────────┘     │             │
                                        └─────────────┘
```

- **프론트엔드**: REST API와 WebSocket 연결을 통해 백엔드와 통신
- **백엔드**: Django + Channels로 HTTP와 WebSocket 요청 처리
- **데이터 저장소**: PostgreSQL(영구 데이터), Redis(채널 레이어 및 캐싱)

## 기술 스택

- **백엔드**:
  - Python 3.11+
  - Django 5.0+
  - Django Channels 4.0+
  - Django REST Framework 3.15+
  - JWT 인증

- **데이터베이스**:
  - PostgreSQL 15
  - Redis 7

- **배포**:
  - Docker & Docker Compose
  - Daphne ASGI 서버

## 주요 기능

- **실시간 채팅**: WebSocket을 통한 즉각적인 메시지 전송
- **채팅방 관리**: 개인 및 그룹 채팅방 생성, 참여, 나가기
- **사용자 관리**: 등록, 로그인, 상태 표시
- **메시지 저장**: 모든 채팅 기록 데이터베이스 저장
- **온라인 상태**: 실시간 사용자 접속 상태 확인
- **부하 분산**: 분산 처리를 위한 Redis 채널 레이어 사용

## 설치 및 실행 방법

### 로컬 개발 환경 설정

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

4. PostgreSQL 및 Redis 설정
```bash
# PostgreSQL 설정은 settings.py 참조
# Redis 설정은 settings.py의 CHANNEL_LAYERS 참조
```

5. 개발 서버 실행
```bash
python manage.py migrate
python manage.py runserver
```

### Docker를 사용한 실행

1. Docker 및 Docker Compose 설치

2. 컨테이너 빌드 및 실행
```bash
docker compose up
```

3. 웹 브라우저에서 접속
```
http://localhost:8000/test
```

## API 엔드포인트

| 엔드포인트               | 메서드 | 설명                     |
|-------------------------|--------|------------------------|
| `/api/token/`           | POST   | JWT 토큰 발급           |
| `/api/token/refresh/`   | POST   | JWT 토큰 갱신           |
| `/api/register/`        | POST   | 사용자 등록             |
| `/api/rooms/`           | GET    | 채팅방 목록 조회         |
| `/api/rooms/`           | POST   | 채팅방 생성             |
| `/api/rooms/<id>/`      | GET    | 채팅방 상세 조회         |
| `/api/rooms/<id>/messages/` | GET | 채팅방 메시지 조회       |
| `/api/rooms/<id>/users/`    | GET | 채팅방 참여자 조회       |

## WebSocket 연결

- **채팅방 연결**: `ws://<host>/ws/chat/<room_id>/`
- **온라인 상태**: `ws://<host>/ws/online/`

## 확장성 및 성능 최적화

- Redis를 활용한 채널 레이어로 여러 서버 간 메시지 브로드캐스팅 가능
- 메시지 캐싱 및 큐를 통한 데이터베이스 부하 감소
- 비동기 처리를 통한 동시 연결 처리 최적화
- 컨테이너화로 손쉬운 수평 확장 가능

## 제한 사항

- 그룹 채팅 최대 인원: 100명
- 메시지 유형: 텍스트만 지원
- 메시지 길이: 최대 1,000자

## 테스트

API 및 웹소켓 테스트는 다음 URL에서 가능합니다:
```
http://localhost:8000/test