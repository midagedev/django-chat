import json
import time
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from django.core.cache import cache
from .models import ChatRoom, ChatRoomMember, Message

# 전역 변수 및 상수 정의
CLEANUP_INTERVAL = 20  # 상태 정리 주기 (초)
HEARTBEAT_TIMEOUT = 15  # 하트비트 타임아웃 (초)
CACHE_TIMEOUT = 30  # 캐시 유지 시간 (초)
ONLINE_STATUS_GROUP = "online_status"  # 전역 온라인 상태 관리 그룹명

# 온라인 상태 관리 관련 변수
last_status_cleanup = 0  # 마지막 상태 정리 시간
cleanup_in_progress = False  # 상태 정리 작업 진행 여부
user_last_heartbeat = {}  # 사용자별 마지막 하트비트 저장


class ChatConsumer(AsyncWebsocketConsumer):
    """채팅방 WebSocket 소비자

    각 채팅방에 연결된 WebSocket을 처리하며, 메시지 전송 및 수신,
    사용자 온라인 상태 관리 등을 담당합니다.
    """

    async def connect(self):
        """WebSocket 연결 설정"""
        try:
            # 기본 정보 설정
            self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
            self.room_group_name = f"chat_{self.room_id}"
            self.user = self.scope["user"]

            # 익명 사용자인 경우 연결 거부
            if self.user.is_anonymous:
                await self.close(code=4001)
                return

            # 채팅방 참여 확인
            if not await self.is_room_member():
                await self.close(code=4002)
                return

            # 채팅방 그룹에 참여
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

            # 사용자 온라인 상태 업데이트
            await self.update_user_status(True)

            # 온라인 상태 변경 알림 전송
            await self.channel_layer.group_send(
                self.room_group_name, {"type": "online_status_update"}
            )

            # 하트비트 초기 시간 설정
            user_key = f"{self.user.id}_{self.room_id}"
            user_last_heartbeat[user_key] = time.time()

            # 연결 수락
            await self.accept()

            # 다른 참여자들에게 입장 알림
            await self.channel_layer.group_send(
                self.room_group_name, {"type": "user_join", "user": self.user.username}
            )

            # 현재 채팅방의 온라인 사용자 정보 전송
            await self.online_status_update({"type": "online_status_update"})

            # 메시지 워커 시작
            self.message_worker_task = asyncio.create_task(self.message_worker())

        except Exception as e:
            print(f"채팅 연결 오류: {e}")
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """WebSocket 연결 종료"""
        try:
            if hasattr(self, "room_group_name"):
                # 사용자 오프라인 상태 업데이트
                await self.update_user_status(False)

                # 채팅방 그룹에서 나가기
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )

                # 다른 참여자들에게 퇴장 알림
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "user_leave", "user": self.user.username},
                )

                # 온라인 상태 업데이트 알림 (채팅방)
                await self.channel_layer.group_send(
                    self.room_group_name, {"type": "online_status_update"}
                )

                # 전역 온라인 상태 그룹에도 알림 전송
                await self.channel_layer.group_send(
                    ONLINE_STATUS_GROUP, {"type": "online_status_update"}
                )

            # 메시지 워커 정지
            if hasattr(self, "message_worker_task") and self.message_worker_task:
                self.message_worker_task.cancel()

            # 하트비트 기록 정리
            user_key = f"{self.user.id}_{self.room_id}"
            if user_key in user_last_heartbeat:
                del user_last_heartbeat[user_key]

        except Exception as e:
            print(f"채팅 연결 종료 오류: {e}")

    async def receive(self, text_data):
        """클라이언트로부터 메시지 수신"""
        try:
            text_data_json = json.loads(text_data)

            # 하트비트 메시지인 경우 온라인 상태만 갱신
            if text_data_json.get("type") == "heartbeat":
                user_key = f"{self.user.id}_{self.room_id}"
                user_last_heartbeat[user_key] = time.time()
                await self.update_user_status(True)
                # 온라인 상태 변경 알림 전송
                await self.channel_layer.group_send(
                    self.room_group_name, {"type": "online_status_update"}
                )
                return

            # 일반 메시지 처리
            message = text_data_json.get("message")
            if not message or not message.strip():
                return

            # 메시지 큐에 추가
            await self.add_message_to_queue(message)

            # 브로드캐스팅
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                    "user": self.user.username,
                },
            )

        except json.JSONDecodeError:
            print("유효하지 않은 JSON 메시지를 받았습니다")
        except Exception as e:
            print(f"메시지 수신 오류: {e}")

    async def add_message_to_queue(self, message):
        """메시지를 큐에 추가"""
        message_key = f"message_queue_{self.room_id}"
        pending_messages = await sync_to_async(cache.get)(message_key) or []
        pending_messages.append(
            {"sender": self.user.id, "content": message, "timestamp": time.time()}
        )
        await sync_to_async(cache.set)(message_key, pending_messages, timeout=3600)

    async def chat_message(self, event):
        """채팅 메시지 이벤트 처리"""
        await self.send(
            text_data=json.dumps(
                {"type": "message", "message": event["message"], "user": event["user"]}
            )
        )

    async def user_join(self, event):
        """사용자 입장 이벤트 처리"""
        await self.send(text_data=json.dumps({"type": "join", "user": event["user"]}))

    async def user_leave(self, event):
        """사용자 퇴장 이벤트 처리"""
        await self.send(text_data=json.dumps({"type": "leave", "user": event["user"]}))

    async def online_status_update(self, event):
        """온라인 상태 업데이트 이벤트 처리"""
        room_users = await self.get_room_users_status()
        await self.send(
            text_data=json.dumps({"type": "online_status", "users": room_users})
        )

    @database_sync_to_async
    def get_room_users_status(self):
        """방 참여자들의 온라인 상태 정보를 가져옵니다."""
        # 채팅방 멤버 정보 조회 (최적화된 쿼리 사용)
        members = ChatRoomMember.objects.filter(room_id=self.room_id).select_related(
            "user"
        )

        # 온라인 상태 확인
        online_key = f"online_users_{self.room_id}"
        online_users = cache.get(online_key) or set()

        # 유저 데이터 구성
        users_data = []
        for member in members:
            user = member.user
            users_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "is_online": user.id in online_users,
                }
            )

        return users_data

    @database_sync_to_async
    def is_room_member(self):
        """현재 사용자가 채팅방의 멤버인지 확인합니다."""
        try:
            return ChatRoomMember.objects.filter(
                user=self.user, room_id=self.room_id
            ).exists()
        except Exception:
            return False

    @database_sync_to_async
    def update_user_status(self, is_online):
        """사용자의 온라인 상태를 업데이트합니다."""
        try:
            # DB 업데이트
            ChatRoomMember.objects.filter(user=self.user, room_id=self.room_id).update(
                is_online=is_online
            )

            # 채팅방 온라인 상태 캐싱
            self._update_room_online_status(is_online)

            # 전역 온라인 상태 업데이트
            self._update_global_online_status(is_online)

            return True
        except Exception as e:
            print(f"사용자 상태 업데이트 오류: {e}")
            return False

    def _update_room_online_status(self, is_online):
        """채팅방 내 사용자 온라인 상태 업데이트"""
        online_key = f"online_users_{self.room_id}"
        online_users = cache.get(online_key) or set()

        if is_online:
            online_users.add(self.user.id)
        else:
            online_users.discard(self.user.id)

        cache.set(online_key, online_users, timeout=CACHE_TIMEOUT)

    def _update_global_online_status(self, is_online):
        """전역 온라인 상태 업데이트"""
        global_online_key = "global_online_users"
        global_online_users = cache.get(global_online_key) or set()

        if is_online:
            global_online_users.add(self.user.id)
        else:
            # 다른 채팅방에 사용자가 접속해 있는지 확인
            other_rooms_exist = (
                ChatRoomMember.objects.filter(user=self.user, is_online=True)
                .exclude(room_id=self.room_id)
                .exists()
            )

            # 다른 방에 접속해 있지 않은 경우에만 전역 상태에서 제거
            if not other_rooms_exist:
                global_online_users.discard(self.user.id)

        cache.set(global_online_key, global_online_users, timeout=CACHE_TIMEOUT)

    async def message_worker(self):
        """백그라운드 메시지 저장 워커

        메시지 큐에서 메시지를 주기적으로 가져와 일괄 처리합니다.
        """
        while True:
            try:
                # 처리할 메시지가 있는지 확인
                message_key = f"message_queue_{self.room_id}"
                pending_messages = await sync_to_async(cache.get)(message_key) or []

                if pending_messages:
                    # 메시지 배치 처리 (최대 100개)
                    messages_to_save = []
                    for msg in pending_messages[:100]:
                        messages_to_save.append(
                            Message(
                                room_id=self.room_id,
                                sender_id=msg["sender"],
                                content=msg["content"],
                                created_at=msg.get("timestamp", time.time()),
                            )
                        )

                    # 벌크 생성으로 DB 효율성 향상
                    await database_sync_to_async(Message.objects.bulk_create)(
                        messages_to_save
                    )

                    # 처리된 메시지 제거
                    await sync_to_async(cache.set)(
                        message_key,
                        pending_messages[100:],
                        timeout=3600,
                    )
            except Exception as e:
                print(f"메시지 처리 중 오류: {e}")

            # 0.5초마다 체크
            await asyncio.sleep(0.5)


class OnlineStatusConsumer(AsyncWebsocketConsumer):
    """전역 온라인 상태 관리 소비자

    사용자가 대화방에 참여하지 않아도 온라인 상태 정보를 받을 수 있습니다.
    """

    async def connect(self):
        """WebSocket 연결 설정"""
        try:
            self.user = self.scope["user"]

            # 익명 사용자인 경우 연결은 허용하되 상태 업데이트는 하지 않음
            if not self.user.is_anonymous:
                # 온라인 상태 그룹에 추가
                await self.channel_layer.group_add(
                    ONLINE_STATUS_GROUP, self.channel_name
                )

                # 사용자 온라인 상태 업데이트 및 알림 전송
                room_ids = await self.update_global_status(True)

                # 온라인 상태 그룹에 알림 전송
                print(f"새 사용자 접속 알림: {self.user.username}")
                await self.channel_layer.group_send(
                    ONLINE_STATUS_GROUP, {"type": "online_status_update"}
                )

                # 각 방에 알림 전송
                for room_id in room_ids:
                    await self.channel_layer.group_send(
                        f"chat_{room_id}", {"type": "online_status_update"}
                    )

                # 하트비트 초기 시간 설정
                user_key = f"global_{self.user.id}"
                user_last_heartbeat[user_key] = time.time()

                # 필요한 경우 상태 정리 워커 시작
                await self.start_cleanup_worker_if_needed()

            # 연결 수락
            await self.accept()

        except Exception as e:
            print(f"온라인 상태 연결 오류: {e}")
            await self.close(code=4000)

    async def start_cleanup_worker_if_needed(self):
        """필요한 경우 상태 정리 워커 시작"""
        global last_status_cleanup, cleanup_in_progress

        current_time = time.time()
        if (
            current_time - last_status_cleanup > CLEANUP_INTERVAL
        ) and not cleanup_in_progress:
            self.status_cleanup_task = asyncio.create_task(self.status_cleanup_worker())
        else:
            self.status_cleanup_task = None

    async def disconnect(self, close_code):
        """WebSocket 연결 종료"""
        try:
            # 사용자가 인증된 경우만 상태 업데이트
            if not self.user.is_anonymous:
                # 사용자 오프라인 상태 업데이트
                await self.update_global_status(False)

                # 온라인 상태 그룹에서 제거
                await self.channel_layer.group_discard(
                    ONLINE_STATUS_GROUP, self.channel_name
                )

                # 하트비트 기록 정리
                user_key = f"global_{self.user.id}"
                if user_key in user_last_heartbeat:
                    del user_last_heartbeat[user_key]

                # 상태 정리 워커 정지 (시작한 사람이 정지)
                if hasattr(self, "status_cleanup_task") and self.status_cleanup_task:
                    self.status_cleanup_task.cancel()
                    global cleanup_in_progress
                    cleanup_in_progress = False

        except Exception as e:
            print(f"온라인 상태 연결 종료 오류: {e}")

    async def receive(self, text_data):
        """클라이언트로부터 메시지 수신"""
        try:
            if self.user.is_anonymous:
                return

            text_data_json = json.loads(text_data)

            # 하트비트 메시지인 경우 온라인 상태 갱신
            if text_data_json.get("type") == "heartbeat":
                user_key = f"global_{self.user.id}"
                user_last_heartbeat[user_key] = time.time()
                await self.update_global_status(True)

        except json.JSONDecodeError:
            print("유효하지 않은 JSON 메시지를 받았습니다")
        except Exception as e:
            print(f"온라인 상태 메시지 수신 오류: {e}")

    async def online_status_update(self, event):
        """온라인 상태 업데이트 알림"""
        await self.send(text_data=json.dumps({"type": "online_users_update"}))

    @database_sync_to_async
    def update_global_status(self, is_online):
        """전역 온라인 상태 업데이트"""
        try:
            # 글로벌 온라인 사용자 목록 업데이트
            global_online_key = "global_online_users"
            online_users = cache.get(global_online_key) or set()

            # 온라인 상태 변경 여부 확인
            status_changed = False

            if is_online:
                if self.user.id not in online_users:
                    online_users.add(self.user.id)
                    status_changed = True
                    print(f"사용자 온라인 상태 추가: {self.user.username}")
            else:
                if self.user.id in online_users:
                    online_users.discard(self.user.id)
                    status_changed = True
                    print(f"사용자 온라인 상태 제거: {self.user.username}")

            cache.set(global_online_key, online_users, timeout=CACHE_TIMEOUT)

            # 사용자가 참여한 모든 채팅방의 상태 업데이트
            rooms = list(ChatRoom.objects.filter(participants__user=self.user))
            room_ids = []

            for room in rooms:
                room_ids.append(room.id)
                room_key = f"online_users_{room.id}"
                room_online = cache.get(room_key) or set()

                if is_online:
                    room_online.add(self.user.id)
                    # 해당 방 멤버십 상태 업데이트
                    ChatRoomMember.objects.filter(room=room, user=self.user).update(
                        is_online=True
                    )
                else:
                    room_online.discard(self.user.id)
                    # 해당 방 멤버십 상태 업데이트
                    ChatRoomMember.objects.filter(room=room, user=self.user).update(
                        is_online=False
                    )

                cache.set(room_key, room_online, timeout=CACHE_TIMEOUT)

            # 방 ID 목록 반환
            return room_ids

        except Exception as e:
            print(f"전역 상태 업데이트 오류: {e}")
            return []

    async def status_cleanup_worker(self):
        """전체 온라인 사용자 상태를 주기적으로 정리하는 워커"""
        global last_status_cleanup, cleanup_in_progress
        cleanup_in_progress = True

        try:
            # 글로벌 온라인 사용자 정리
            await self.cleanup_global_online_status()

            # 채팅방별 온라인 상태 정리
            await self.cleanup_room_online_status()

            # 정리 완료 시간 기록
            last_status_cleanup = time.time()

        except Exception as e:
            print(f"온라인 상태 정리 중 오류: {e}")
        finally:
            cleanup_in_progress = False
            # 일정 시간 후 다시 실행하도록 스케줄
            await asyncio.sleep(CLEANUP_INTERVAL)
            # 다른 작업이 없을 때만 다시 실행
            if not cleanup_in_progress:
                asyncio.create_task(self.status_cleanup_worker())

    async def cleanup_global_online_status(self):
        """글로벌 온라인 상태 정리"""
        global_online_key = "global_online_users"
        global_online_users = await sync_to_async(cache.get)(global_online_key) or set()
        current_time = time.time()

        # 하트비트 타임아웃 확인 (글로벌)
        global_to_remove = set()
        for user_id in global_online_users:
            user_key = f"global_{user_id}"
            last_heartbeat = user_last_heartbeat.get(user_key, 0)

            # 하트비트 타임아웃 확인
            if current_time - last_heartbeat > HEARTBEAT_TIMEOUT:
                global_to_remove.add(user_id)
                # 사용자 하트비트 기록 삭제
                if user_key in user_last_heartbeat:
                    del user_last_heartbeat[user_key]

        # 글로벌 온라인 목록 업데이트
        if global_to_remove:
            valid_global_users = global_online_users - global_to_remove
            await sync_to_async(cache.set)(
                global_online_key, valid_global_users, timeout=CACHE_TIMEOUT
            )

            # 온라인 상태 그룹에 업데이트 알림
            await self.channel_layer.group_send(
                ONLINE_STATUS_GROUP, {"type": "online_status_update"}
            )

        return global_to_remove

    async def cleanup_room_online_status(self):
        """채팅방별 온라인 상태 정리"""
        # 글로벌 상태 정리에서 제거된 사용자 목록
        global_to_remove = await self.cleanup_global_online_status()

        # 모든 채팅방 정보 가져오기
        rooms = await database_sync_to_async(list)(ChatRoom.objects.all())
        current_time = time.time()

        for room in rooms:
            # 채팅방의 온라인 상태 캐시 키
            online_key = f"online_users_{room.id}"
            online_users = await sync_to_async(cache.get)(online_key) or set()

            if online_users:
                # 하트비트 타임아웃 확인
                to_remove = set()
                for user_id in online_users:
                    # 글로벌 상태에서 이미 오프라인으로 판단된 사용자는 제거
                    if user_id in global_to_remove:
                        to_remove.add(user_id)
                        continue

                    # 방별 하트비트 확인
                    user_key = f"{user_id}_{room.id}"
                    last_heartbeat = user_last_heartbeat.get(user_key, 0)

                    # 하트비트 타임아웃 확인
                    if current_time - last_heartbeat > HEARTBEAT_TIMEOUT:
                        to_remove.add(user_id)
                        # 사용자 하트비트 기록 삭제
                        if user_key in user_last_heartbeat:
                            del user_last_heartbeat[user_key]

                if to_remove:
                    # 캐시에서 제거
                    valid_online_users = online_users - to_remove
                    await sync_to_async(cache.set)(
                        online_key, valid_online_users, timeout=CACHE_TIMEOUT
                    )

                    # DB 업데이트
                    await database_sync_to_async(
                        ChatRoomMember.objects.filter(
                            room=room, user_id__in=list(to_remove)
                        ).update
                    )(is_online=False)

                    # 채팅방에도 알림 전송
                    await self.channel_layer.group_send(
                        f"chat_{room.id}", {"type": "online_status_update"}
                    )