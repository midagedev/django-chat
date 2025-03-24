import uuid
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.contrib.auth.models import AnonymousUser
from django.utils.crypto import get_random_string


class AutoCreateUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
