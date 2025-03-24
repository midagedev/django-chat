from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


def validate_message_content(content):
    if len(content) > 1000:
        raise ValidationError("메시지는 1000자를 초과할 수 없습니다.")
    return content


class ChatRoom(models.Model):
    ROOM_TYPES = (
        ("direct", "1:1 채팅"),
        ("group", "그룹 채팅"),
    )

    name = models.CharField(max_length=255)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.room_type == "group":
            if self.participants.count() > 100:
                raise ValidationError(
                    "그룹 채팅방은 최대 100명까지만 참여할 수 있습니다."
                )

    def __str__(self):
        return self.name


class ChatRoomMember(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, related_name="participants"
    )
    is_online = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "room")

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"


class Message(models.Model):
    room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(validators=[validate_message_content])
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"
