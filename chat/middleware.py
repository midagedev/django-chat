import uuid
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.auth.models import AnonymousUser
from django.utils.crypto import get_random_string
from rest_framework_simplejwt.authentication import JWTAuthentication


class AutoCreateUserMiddleware:
    """
    익명 사용자를 위한 자동 계정 생성 미들웨어

    - 쿠키 기반 세션 인증을 사용할 경우 익명 사용자를 위한 임시 계정을 생성합니다.
    - JWT 인증을 사용할 경우 이 미들웨어는 무시됩니다.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_authentication = JWTAuthentication()

    def __call__(self, request):
        # JWT 인증 확인
        try:
            jwt_auth = self.jwt_authentication.authenticate(request)
            if jwt_auth:
                # JWT 토큰으로 인증된 경우, 미들웨어 건너뛰기
                return self.get_response(request)
        except:
            pass

        # 인증되지 않은 경우에만 임시 사용자 생성
        if not request.user.is_authenticated:
            if not request.session.session_key:
                request.session.save()

            session_key = request.session.session_key
            username = f"temp_{session_key[:8]}"

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                password = get_random_string(12)
                user = User.objects.create_user(
                    username=username, password=password, first_name="임시사용자"
                )

            login(request, user)

        response = self.get_response(request)
        return response
