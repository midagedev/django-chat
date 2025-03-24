import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import ChatRoom, ChatRoomMember, Message


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

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # 메시지 저장과 브로드캐스팅을 분리하여 처리
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "chat_message", "message": message, "user": self.user.username},
        )

        # 메시지 저장을 위한 이벤트 발송
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "save_message_handler",
                "message": message,
            },
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
