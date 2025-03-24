from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth.models import User
from django.shortcuts import render
from .models import ChatRoom, ChatRoomMember, Message
from .serializers import (
    ChatRoomSerializer,
    MessageSerializer,
    UserSerializer,
    ChatRoomMemberSerializer,
)


def test_api_view(request):
    return render(request, "chat/test_api.html")


class ChatRoomViewSet(viewsets.ModelViewSet):
    serializer_class = ChatRoomSerializer

    def get_queryset(self):
        return ChatRoom.objects.all()

    def perform_create(self, serializer):
        chat_room = serializer.save()
        ChatRoomMember.objects.create(room=chat_room, user=self.request.user)

    @action(detail=False, methods=["post"])
    def create_direct_chat(self, request):
        target_user_id = request.data.get("user_id")
        if not target_user_id:
            return Response(
                {"error": "대화 상대를 지정해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "존재하지 않는 사용자입니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 이미 존재하는 1:1 대화방 확인
        existing_room = (
            ChatRoom.objects.filter(
                room_type="direct",
                participants__user=request.user,
            )
            .filter(participants__user=target_user)
            .first()
        )

        if existing_room:
            serializer = self.get_serializer(existing_room)
            return Response(serializer.data)

        # 새로운 1:1 대화방 생성
        room_name = f"DM: {request.user.username} & {target_user.username}"
        chat_room = ChatRoom.objects.create(name=room_name, room_type="direct")

        # 참여자 추가
        ChatRoomMember.objects.create(room=chat_room, user=request.user)
        ChatRoomMember.objects.create(room=chat_room, user=target_user)

        serializer = self.get_serializer(chat_room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        chat_room = self.get_object()

        if chat_room.room_type == "direct":
            return Response(
                {"error": "직접 메시지 방에는 참여할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if chat_room.participants.count() >= 100:
            return Response(
                {"error": "채팅방이 가득 찼습니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        ChatRoomMember.objects.get_or_create(room=chat_room, user=request.user)
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        chat_room = self.get_object()
        ChatRoomMember.objects.filter(room=chat_room, user=request.user).delete()
        return Response(status=status.HTTP_200_OK)


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        room_id = self.kwargs.get("room_pk")
        return Message.objects.filter(room_id=room_id)

    def perform_create(self, serializer):
        room_id = self.kwargs.get("room_pk")
        serializer.save(room_id=room_id, sender=self.request.user)

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def search(self, request):
        query = request.query_params.get("q", "")
        if len(query) < 3:
            return Response(
                {"error": "검색어는 최소 3자 이상이어야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)
