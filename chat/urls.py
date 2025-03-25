"""
URL configuration for chat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views

router = DefaultRouter()
router.register(r"rooms", views.ChatRoomViewSet, basename="chatroom")
router.register(r"users", views.UserViewSet, basename="user")

rooms_router = routers.NestedDefaultRouter(router, r"rooms", lookup="room")
rooms_router.register(r"messages", views.MessageViewSet, basename="room-messages")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("test/", views.test_api_view, name="test_api"),
    path("api/", include(router.urls)),
    path("api/", include(rooms_router.urls)),
]
