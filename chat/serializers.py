from rest_framework import serializers
from django.contrib.auth.models import User
from .models import ChatRoom, ChatRoomMember, Message


class UserSerializer(serializers.ModelSerializer):
    """사용자 정보 시리얼라이저"""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "email"]


class UserRegistrationSerializer(serializers.ModelSerializer):
    """사용자 등록 시리얼라이저"""

    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    password2 = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ["username", "password", "password2", "email", "first_name"]
        extra_kwargs = {"first_name": {"required": True}, "email": {"required": True}}

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "비밀번호가 일치하지 않습니다."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create_user(**validated_data)
        return user


class ChatRoomMemberSerializer(serializers.ModelSerializer):
    """채팅방 멤버 시리얼라이저"""

    user = UserSerializer(read_only=True)

    class Meta:
        model = ChatRoomMember
        fields = ["id", "room", "user", "is_online", "joined_at"]


class MessageSerializer(serializers.ModelSerializer):
    """채팅 메시지 시리얼라이저"""

    user = UserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "room", "user", "message", "created_at"]


class ChatRoomSerializer(serializers.ModelSerializer):
    """채팅방 정보 시리얼라이저"""

    class Meta:
        model = ChatRoom
        fields = ["id", "name", "room_type", "created_at"]

    def get_last_message(self, obj):
        last_message = obj.messages.order_by("-created_at").first()
        if last_message:
            return MessageSerializer(last_message).data
        return None
