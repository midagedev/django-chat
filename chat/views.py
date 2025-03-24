from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth.models import User
from .models import ChatRoom, ChatRoomMember, Message
from .serializers import (
    ChatRoomSerializer,
    MessageSerializer,
    UserSerializer,
    ChatRoomMemberSerializer,
)


class ChatRoomViewSet(viewsets.ModelViewSet):
    serializer_class = ChatRoomSerializer

    def get_queryset(self):
        return ChatRoom.objects.filter(participants__user=self.request.user).distinct()

    def perform_create(self, serializer):
        chat_room = serializer.save()
        ChatRoomMember.objects.create(room=chat_room, user=self.request.user)

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
