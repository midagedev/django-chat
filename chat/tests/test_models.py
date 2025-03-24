from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from chat.models import ChatRoom, ChatRoomMember, Message, validate_message_content


class ChatRoomTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.chat_room = ChatRoom.objects.create(name="Test Room", room_type="group")

    def test_chat_room_creation(self):
        self.assertEqual(self.chat_room.name, "Test Room")
        self.assertEqual(self.chat_room.room_type, "group")

    def test_chat_room_str(self):
        self.assertEqual(str(self.chat_room), "Test Room")

    def test_group_chat_max_participants(self):
        # 100명 이상의 참가자를 추가하려고 할 때 ValidationError 발생 확인
        for i in range(101):
            user = User.objects.create_user(username=f"user{i}", password="12345")
            ChatRoomMember.objects.create(user=user, room=self.chat_room)

        with self.assertRaises(ValidationError):
            self.chat_room.clean()


class MessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.chat_room = ChatRoom.objects.create(name="Test Room", room_type="direct")

    def test_message_creation(self):
        message = Message.objects.create(
            room=self.chat_room, sender=self.user, content="Test message"
        )
        self.assertEqual(message.content, "Test message")
        self.assertEqual(message.sender, self.user)
        self.assertFalse(message.is_read)

    def test_message_content_validation(self):
        # 직접 validator 함수를 테스트
        with self.assertRaises(ValidationError):
            validate_message_content("a" * 1001)

        # 정상적인 길이의 메시지는 통과해야 함
        self.assertEqual(validate_message_content("a" * 1000), "a" * 1000)
