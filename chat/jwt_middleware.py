import asyncio
from urllib.parse import parse_qs
from django.db import close_old_connections
from django.contrib.auth.models import AnonymousUser
from channels.middleware import BaseMiddleware
from channels.auth import AuthMiddlewareStack
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JWTAuthMiddleware(BaseMiddleware):
    """
    WebSocket 연결을 위한 JWT 인증 미들웨어

    WebSocket 연결 시 쿼리 파라미터에서 JWT 토큰을 추출하여 인증을 수행합니다.
    """

    def __init__(self, inner):
        self.inner = inner
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        # DB 연결 정리
        close_old_connections()

        # 쿼리 파라미터에서 토큰 추출
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token = query_params.get("token", [""])[0]

        # 토큰이 없는 경우 기존 세션 인증 사용
        if not token:
            return await self.inner(scope, receive, send)

        # JWT 토큰 검증
        try:
            # 동기 함수를 비동기로 실행
            validated_token = await asyncio.to_thread(
                self.jwt_auth.get_validated_token, token
            )
            user = await asyncio.to_thread(self.jwt_auth.get_user, validated_token)

            # 인증된 사용자 정보를 스코프에 저장
            scope["user"] = user
        except (InvalidToken, TokenError):
            # 토큰이 유효하지 않은 경우 AnonymousUser 설정
            scope["user"] = AnonymousUser()
        except Exception as e:
            print(f"JWT 인증 오류: {e}")
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """
    세션 인증과 JWT 인증을 모두 지원하는 미들웨어 스택
    """
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
