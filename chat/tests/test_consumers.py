import json
import asyncio
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.layers import get_channel_layer
from django.urls import re_path
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from chat.consumers import ChatConsumer
from chat.models import ChatRoom, ChatRoomMember


class ChatConsumerTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # URL 패턴 설정
        cls.application = URLRouter(
            [
                re_path(r"ws/chat/(?P<room_id>\d+)/$", ChatConsumer.as_asgi()),
            ]
        )

    async def asyncSetUp(self):
        # 테스트 사용자와 채팅방 생성
        self.user = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="12345"
        )
        self.chat_room = await database_sync_to_async(ChatRoom.objects.create)(
            name="Test Room", room_type="direct"
        )
        await database_sync_to_async(ChatRoomMember.objects.create)(
            user=self.user, room=self.chat_room
        )
        # 실제 channel layer 사용
        self.channel_layer = get_channel_layer()

    async def setup_communicator(self):
        # WebSocket 연결 설정
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/{self.chat_room.id}/"
        )
        # 인증된 사용자로 scope 설정
        communicator.scope["user"] = self.user
        communicator.scope["url_route"] = {
            "kwargs": {"room_id": str(self.chat_room.id)}
        }
        return communicator

    async def test_connect_to_room(self):
        await self.asyncSetUp()
        communicator = await self.setup_communicator()

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # 약간의 지연 추가
        await asyncio.sleep(0.1)

        # 연결 후 메시지 수신 확인
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "join")
        self.assertEqual(response["user"], "testuser")

        await communicator.disconnect()
        await asyncio.sleep(0.1)

    async def test_chat_message(self):
        await self.asyncSetUp()
        communicator = await self.setup_communicator()

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await asyncio.sleep(0.1)

        # 입장 메시지 수신
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "join")

        # 메시지 전송
        await communicator.send_json_to({"message": "Hello, World!"})

        # 메시지 수신 확인
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "message")
        self.assertEqual(response["message"], "Hello, World!")
        self.assertEqual(response["user"], "testuser")

        await communicator.disconnect()
        await asyncio.sleep(0.1)

    async def test_unauthorized_access(self):
        await self.asyncSetUp()
        # 권한이 없는 사용자의 접근 테스트
        unauthorized_user = await database_sync_to_async(User.objects.create_user)(
            username="unauthorized", password="12345"
        )

        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/{self.chat_room.id}/"
        )
        communicator.scope["user"] = unauthorized_user
        communicator.scope["url_route"] = {
            "kwargs": {"room_id": str(self.chat_room.id)}
        }
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
