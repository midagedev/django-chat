import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import ChatRoom, ChatRoomMember, Message
from asgiref.sync import sync_to_async
from django.core.cache import cache
import asyncio


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_{self.room_id}"
        self.user = self.scope["user"]

        # 채팅방 참여 확인
        if not await self.is_room_member():
            await self.close()
            return

        # 채팅방 그룹에 참여
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # 사용자 온라인 상태 업데이트
        await self.update_user_status(True)
        await self.accept()

        # 다른 참여자들에게 입장 알림
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "user_join", "user": self.user.username}
        )

        # message worker 시작
        self.message_worker_task = asyncio.create_task(self.message_worker())

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            # 사용자 오프라인 상태 업데이트
            await self.update_user_status(False)

            # 채팅방 그룹에서 나가기
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

            # 다른 참여자들에게 퇴장 알림
            await self.channel_layer.group_send(
                self.room_group_name, {"type": "user_leave", "user": self.user.username}
            )

        # message worker 정지
        if hasattr(self, "message_worker_task"):
            self.message_worker_task.cancel()

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # 메시지를 큐에 추가
        message_key = f"message_queue_{self.room_id}"
        pending_messages = await sync_to_async(cache.get)(message_key) or []
        pending_messages.append({"sender": self.user.id, "content": message})
        await sync_to_async(cache.set)(message_key, pending_messages, timeout=3600)

        # 브로드캐스팅
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "chat_message", "message": message, "user": self.user.username},
        )

    async def chat_message(self, event):
        # WebSocket으로 메시지 전송
        await self.send(
            text_data=json.dumps(
                {"type": "message", "message": event["message"], "user": event["user"]}
            )
        )

    async def user_join(self, event):
        # 사용자 입장 메시지 전송
        await self.send(text_data=json.dumps({"type": "join", "user": event["user"]}))

    async def user_leave(self, event):
        # 사용자 퇴장 메시지 전송
        await self.send(text_data=json.dumps({"type": "leave", "user": event["user"]}))

    @database_sync_to_async
    def is_room_member(self):
        try:
            return ChatRoomMember.objects.filter(
                user=self.user, room_id=self.room_id
            ).exists()
        except Exception:
            return False

    @database_sync_to_async
    def update_user_status(self, is_online):
        ChatRoomMember.objects.filter(user=self.user, room_id=self.room_id).update(
            is_online=is_online
        )

    @database_sync_to_async
    def save_message(self, message):
        Message.objects.create(room_id=self.room_id, sender=self.user, content=message)

    async def save_message_handler(self, event):
        # 메시지 저장 처리
        await self.save_message(event["message"])

    async def message_worker(self):
        while True:
            # 처리할 메시지가 있는지 확인
            message_key = f"message_queue_{self.room_id}"
            pending_messages = await sync_to_async(cache.get)(message_key) or []

            if pending_messages:
                # 메시지 배치 처리
                messages_to_save = []
                for msg in pending_messages[:100]:  # 한 번에 최대 100개 처리
                    messages_to_save.append(
                        Message(
                            room_id=self.room_id,
                            sender_id=msg["sender"],
                            content=msg["content"],
                        )
                    )

                await database_sync_to_async(Message.objects.bulk_create)(
                    messages_to_save
                )

                # 처리된 메시지 제거
                await sync_to_async(cache.set)(
                    message_key,
                    pending_messages[100:],
                    timeout=3600,  # 1시간 캐시
                )

            await asyncio.sleep(0.5)  # 0.5초마다 체크