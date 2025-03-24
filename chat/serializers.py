from rest_framework import serializers
from django.contrib.auth.models import User
from .models import ChatRoom, ChatRoomMember, Message


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class ChatRoomMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = ChatRoomMember
        fields = ["user", "is_online", "last_seen"]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer()

    class Meta:
        model = Message
        fields = ["id", "sender", "content", "created_at", "is_read"]


class ChatRoomSerializer(serializers.ModelSerializer):
    participants = ChatRoomMemberSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "name",
            "room_type",
            "participants",
            "last_message",
            "created_at",
        ]

    def get_last_message(self, obj):
        last_message = obj.messages.order_by("-created_at").first()
        if last_message:
            return MessageSerializer(last_message).data
        return None
