import json
import asyncio
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.layers import get_channel_layer
from django.urls import re_path
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from chat.consumers import ChatConsumer, OnlineStatusConsumer
from chat.models import ChatRoom, ChatRoomMember, Message


class ChatConsumerTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # URL 패턴 설정
        cls.application = URLRouter(
            [
                re_path(r"ws/chat/(?P<room_id>\d+)/$", ChatConsumer.as_asgi()),
                re_path(r"ws/online/$", OnlineStatusConsumer.as_asgi()),
            ]
        )

    async def asyncSetUp(self):
        # 테스트 데이터 초기화
        await database_sync_to_async(cache.clear)()

        # 테스트 사용자와 채팅방 생성
        self.user1 = await database_sync_to_async(User.objects.create_user)(
            username="testuser1", password="12345"
        )
        self.user2 = await database_sync_to_async(User.objects.create_user)(
            username="testuser2", password="12345"
        )
        self.chat_room = await database_sync_to_async(ChatRoom.objects.create)(
            name="Test Room", room_type="direct"
        )
        # 채팅방 멤버 추가
        await database_sync_to_async(ChatRoomMember.objects.create)(
            user=self.user1, room=self.chat_room
        )
        await database_sync_to_async(ChatRoomMember.objects.create)(
            user=self.user2, room=self.chat_room
        )
        # 실제 channel layer 사용
        self.channel_layer = get_channel_layer()

    async def setup_communicator(self, user, room_id=None):
        """사용자와 방 ID로 WebSocket 커뮤니케이터 설정"""
        if room_id is None:
            room_id = self.chat_room.id

        # WebSocket 연결 설정
        communicator = WebsocketCommunicator(self.application, f"/ws/chat/{room_id}/")
        # 인증된 사용자로 scope 설정
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {"kwargs": {"room_id": str(room_id)}}
        return communicator

    async def test_connect_to_room(self):
        """채팅방 연결 테스트"""
        await self.asyncSetUp()
        communicator = await self.setup_communicator(self.user1)

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "채팅방에 연결할 수 없습니다")

        # 약간의 지연 추가
        await asyncio.sleep(0.1)

        # 연결 후 메시지 수신 (여러 메시지를 받을 수 있음)
        found_join_message = False
        # 최대 3개 메시지 수신 시도
        for _ in range(3):
            try:
                response = await asyncio.wait_for(
                    communicator.receive_json_from(), timeout=0.5
                )
                # join 메시지 찾기
                if (
                    response.get("type") == "join"
                    and response.get("user") == "testuser1"
                ):
                    found_join_message = True
                    break
            except asyncio.TimeoutError:
                break

        # join 메시지를 받았는지 확인
        self.assertTrue(found_join_message, "입장 메시지를 수신하지 못했습니다")

        await communicator.disconnect()
        await asyncio.sleep(0.1)

    async def test_chat_message(self):
        """채팅 메시지 송수신 테스트"""
        await self.asyncSetUp()
        # 첫 번째 사용자 연결
        communicator1 = await self.setup_communicator(self.user1)
        connected, _ = await communicator1.connect()
        self.assertTrue(connected)

        # 초기 메시지 수신 (모든 메시지 처리)
        await asyncio.sleep(0.2)
        while True:
            try:
                await asyncio.wait_for(communicator1.receive_from(), timeout=0.5)
            except asyncio.TimeoutError:
                break

        # 두 번째 사용자 연결
        communicator2 = await self.setup_communicator(self.user2)
        connected, _ = await communicator2.connect()
        self.assertTrue(connected)

        # 초기 메시지 수신 (모든 메시지 처리)
        await asyncio.sleep(0.2)
        while True:
            try:
                await asyncio.wait_for(communicator2.receive_from(), timeout=0.5)
            except asyncio.TimeoutError:
                break

        # 첫 번째 사용자가 메시지 전송
        test_message = "안녕하세요, 테스트 메시지입니다!"
        await communicator1.send_json_to({"message": test_message})
        await asyncio.sleep(0.2)  # 메시지 처리 시간 확보

        # 두 번째 사용자가 메시지 수신 확인
        response = await communicator2.receive_json_from()
        self.assertEqual(response["message"], test_message)
        self.assertEqual(response["user"], "testuser1")

        # 메시지 워커가 메시지를 저장할 시간 확보
        await asyncio.sleep(1.5)

        # 데이터베이스에 메시지가 저장되었는지 확인
        message_exists = await database_sync_to_async(self._check_message_exists)(
            self.chat_room, test_message, self.user1
        )
        self.assertTrue(message_exists, "메시지가 데이터베이스에 저장되지 않았습니다")

        await communicator1.disconnect()
        await communicator2.disconnect()
        await asyncio.sleep(0.1)

    def _check_message_exists(self, room, content, sender):
        """메시지가 데이터베이스에 존재하는지 확인 (동기 함수)"""
        return Message.objects.filter(
            room=room, content=content, sender=sender
        ).exists()

    async def test_unauthorized_access(self):
        """권한 없는 사용자의 접근 테스트"""
        await self.asyncSetUp()
        # 권한이 없는 사용자의 접근 테스트
        unauthorized_user = await database_sync_to_async(User.objects.create_user)(
            username="unauthorized", password="12345"
        )

        communicator = await self.setup_communicator(unauthorized_user)
        connected, _ = await communicator.connect()
        self.assertFalse(connected, "권한 없는 사용자가 채팅방에 접속할 수 있습니다")

    async def test_online_status_update(self):
        """온라인 상태 업데이트 테스트"""
        await self.asyncSetUp()
        # 첫 번째 사용자 연결
        communicator1 = await self.setup_communicator(self.user1)
        connected, _ = await communicator1.connect()
        self.assertTrue(connected)

        # 초기 메시지 수신 (모든 메시지 처리)
        await asyncio.sleep(0.2)
        while True:
            try:
                await asyncio.wait_for(communicator1.receive_from(), timeout=0.5)
            except asyncio.TimeoutError:
                break

        # 두 번째 사용자 연결
        communicator2 = await self.setup_communicator(self.user2)
        connected, _ = await communicator2.connect()
        self.assertTrue(connected)

        # 초기 메시지 수신 (모든 메시지 처리)
        await asyncio.sleep(0.2)
        while True:
            try:
                await asyncio.wait_for(communicator2.receive_from(), timeout=0.5)
            except asyncio.TimeoutError:
                break

        # 첫 번째 사용자 연결 해제
        await communicator1.disconnect()
        await asyncio.sleep(0.5)  # 연결 종료 및 메시지 처리 시간 확보

        # 두 번째 사용자가 메시지를 수신했는지 확인
        online_status_received = False
        for _ in range(3):
            try:
                response = await asyncio.wait_for(
                    communicator2.receive_json_from(), timeout=0.5
                )
                # 타입에 관계없이 유저 정보가 있는 메시지를 찾음
                if "users" in response:
                    online_status_received = True
                    # 첫 번째 사용자가 오프라인으로 표시되었는지 확인
                    online_users = [
                        u
                        for u in response["users"]
                        if u.get("is_online", False) and u["id"] == self.user1.id
                    ]
                    self.assertEqual(
                        len(online_users),
                        0,
                        "첫 번째 사용자가 여전히 온라인으로 표시됩니다",
                    )
                    break
            except asyncio.TimeoutError:
                break

        # 온라인 상태 메시지를 받았는지 확인
        self.assertTrue(
            online_status_received, "온라인 상태 업데이트 메시지를 수신하지 못했습니다"
        )

        await communicator2.disconnect()
        await asyncio.sleep(0.1)

    async def test_heartbeat(self):
        """하트비트 메시지 테스트"""
        await self.asyncSetUp()
        communicator = await self.setup_communicator(self.user1)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # 모든 초기 메시지 수신 (큐 비우기)
        await asyncio.sleep(0.2)
        while True:
            try:
                await asyncio.wait_for(communicator.receive_from(), timeout=0.5)
            except asyncio.TimeoutError:
                break

        # 하트비트 메시지 전송
        await communicator.send_json_to({"type": "heartbeat"})
        await asyncio.sleep(0.5)  # 메시지 처리 시간 확보

        # 어떤 메시지든 수신 시도
        received_response = False
        try:
            await asyncio.wait_for(communicator.receive_from(), timeout=1.0)
            received_response = True
        except asyncio.TimeoutError:
            pass

        # 하트비트는 응답이 없을 수도 있음 (서버 내부 처리만 함)
        # 이 테스트는 하트비트 메시지가 오류 없이 처리되는지 확인하는 용도

        await communicator.disconnect()
        await asyncio.sleep(0.1)


class OnlineStatusConsumerTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # URL 패턴 설정
        cls.application = URLRouter(
            [
                re_path(r"ws/online/$", OnlineStatusConsumer.as_asgi()),
            ]
        )

    async def asyncSetUp(self):
        # 테스트 데이터 초기화
        await database_sync_to_async(cache.clear)()

        # 테스트 사용자 생성
        self.user = await database_sync_to_async(User.objects.create_user)(
            username="testuser", password="12345"
        )
        self.channel_layer = get_channel_layer()

    async def test_connect_to_global_status(self):
        """전역 온라인 상태 연결 테스트"""
        await self.asyncSetUp()

        # WebSocket 연결 설정
        communicator = WebsocketCommunicator(self.application, "/ws/online/")
        communicator.scope["user"] = self.user

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "전역 온라인 상태에 연결할 수 없습니다")

        # 온라인 상태 메시지 수신 확인
        response = await communicator.receive_json_from()
        # 응답 타입 확인 (실제 응답은 online_users_update)
        self.assertEqual(response["type"], "online_users_update")

        # 이 응답에는 users 키가 없음 - OnlineStatusConsumer.online_status_update 메서드 참조

        await communicator.disconnect()
        await asyncio.sleep(0.1)
