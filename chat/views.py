from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.cache import cache
from django.shortcuts import get_object_or_404, render
from rest_framework_simplejwt.tokens import RefreshToken
from .models import ChatRoom, ChatRoomMember, Message
from .serializers import (
    ChatRoomSerializer,
    MessageSerializer,
    UserSerializer,
    ChatRoomMemberSerializer,
    UserRegistrationSerializer,
)


def test_api_view(request):
    """채팅 테스트 웹 인터페이스"""
    return render(request, "chat/test_api.html")


class ChatRoomViewSet(viewsets.ModelViewSet):
    """채팅방 관련 API 엔드포인트

    채팅방 생성, 조회, 참여, 나가기 등의 기능을 제공합니다.
    """

    queryset = ChatRoom.objects.all()
    serializer_class = ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request):
        """새 채팅방 생성"""
        try:
            name = request.data.get("name")
            room_type = request.data.get("room_type", "group")
            if not name:
                return Response(
                    {"error": "채팅방 이름을 입력해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 채팅방 생성
            chat_room = ChatRoom.objects.create(name=name, room_type=room_type)

            # 생성자를 채팅방 멤버로 추가
            ChatRoomMember.objects.create(room=chat_room, user=request.user)

            return Response(
                ChatRoomSerializer(chat_room).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"])
    def create_direct_chat(self, request):
        """두 사용자 간의 1:1 채팅방 생성"""
        try:
            target_user_id = request.data.get("user_id")
            if not target_user_id:
                return Response(
                    {"error": "대화 상대를 선택해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 대화 상대 확인
            try:
                target_user = User.objects.get(id=target_user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "존재하지 않는 사용자입니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # 자기 자신과의 채팅 방지
            if target_user.id == request.user.id:
                return Response(
                    {"error": "자기 자신과 대화할 수 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 두 사용자가 이미 참여 중인 1:1 채팅방이 있는지 확인
            user_rooms = ChatRoom.objects.filter(
                participants__user=request.user, room_type="direct"
            )
            for room in user_rooms:
                # 해당 방에 대상 사용자도 참여 중인지 확인
                if ChatRoomMember.objects.filter(room=room, user=target_user).exists():
                    # 이미 존재하는 1:1 채팅방이 있다면 해당 방 정보 반환
                    return Response(ChatRoomSerializer(room).data)

            # 새 1:1 채팅방 생성
            room_name = f"{request.user.username}_{target_user.username}"
            chat_room = ChatRoom.objects.create(name=room_name, room_type="direct")

            # 두 사용자를 채팅방 멤버로 추가
            ChatRoomMember.objects.create(room=chat_room, user=request.user)
            ChatRoomMember.objects.create(room=chat_room, user=target_user)

            return Response(
                ChatRoomSerializer(chat_room).data, status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        """특정 채팅방의 메시지 목록 조회"""
        try:
            # 채팅방 존재 및 접근 권한 확인
            chat_room = self.get_object()
            if not ChatRoomMember.objects.filter(
                room=chat_room, user=request.user
            ).exists():
                return Response(
                    {"error": "채팅방에 참여하고 있지 않습니다."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # 최신 메시지 50개를 조회한 후 시간순으로 정렬하여 반환
            messages = Message.objects.filter(room=chat_room).order_by("-created_at")[
                :50
            ]
            messages = list(reversed(messages))  # 최신순에서 시간순으로 변경
            serializer = MessageSerializer(messages, many=True)

            return Response({"results": serializer.data})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["get"])
    def users(self, request, pk=None):
        """특정 채팅방의 참여자 목록 조회"""
        try:
            chat_room = self.get_object()
            if not ChatRoomMember.objects.filter(
                room=chat_room, user=request.user
            ).exists():
                return Response(
                    {"error": "채팅방에 참여하고 있지 않습니다."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            members = ChatRoomMember.objects.filter(room=chat_room).select_related(
                "user"
            )
            serializer = ChatRoomMemberSerializer(members, many=True)

            # 사용자 목록 형식 변경 - users 키를 가진 딕셔너리로 반환
            users_data = []
            for member in serializer.data:
                user_data = member["user"]
                user_data["is_online"] = member["is_online"]
                users_data.append(user_data)

            return Response({"users": users_data})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        """채팅방에 참여"""
        try:
            chat_room = self.get_object()

            # 이미 참여 중인지 확인
            if ChatRoomMember.objects.filter(
                room=chat_room, user=request.user
            ).exists():
                return Response(
                    {"error": "이미 참여 중인 채팅방입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 1:1 채팅방은 직접 참여 불가
            if chat_room.room_type == "direct":
                return Response(
                    {"error": "1:1 채팅방에는 직접 참여할 수 없습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 채팅방에 참여
            ChatRoomMember.objects.create(room=chat_room, user=request.user)

            return Response({"success": "채팅방에 참여했습니다."})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """채팅방 나가기"""
        try:
            chat_room = self.get_object()

            # 참여 중인지 확인
            member = ChatRoomMember.objects.filter(room=chat_room, user=request.user)
            if not member.exists():
                return Response(
                    {"error": "참여하고 있지 않은 채팅방입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 채팅방 나가기
            member.delete()

            # 채팅방에 남은 사용자가 없는 경우 채팅방 삭제
            if not ChatRoomMember.objects.filter(room=chat_room).exists():
                chat_room.delete()
                return Response(
                    {
                        "success": "채팅방을 나갔습니다. 참여자가 없어 채팅방이 삭제되었습니다."
                    }
                )

            return Response({"success": "채팅방을 나갔습니다."})
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """메시지 관련 API 엔드포인트

    메시지 조회 기능을 제공합니다. 메시지 생성은 WebSocket을 통해 이루어집니다.
    """

    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """사용자가 참여한 채팅방의 메시지만 조회"""
        user = self.request.user
        return (
            Message.objects.filter(room__participants__user=user)
            .select_related("sender")
            .order_by("-created_at")
        )


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """사용자 관련 API 엔드포인트

    사용자 정보 조회 및 온라인 상태 확인 기능을 제공합니다.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def me(self, request):
        """현재 로그인한 사용자 정보 조회"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def online(self, request):
        """온라인 상태인 사용자 목록 조회"""
        # Redis 캐시에서 온라인 상태인 사용자 ID 목록 조회
        online_user_ids = cache.get("online_users", [])
        online_users = User.objects.filter(id__in=online_user_ids)
        serializer = UserSerializer(online_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["put"], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """사용자 프로필 정보 업데이트"""
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    """사용자 등록 API

    JWT 토큰 기반 인증을 위한 사용자 등록 API입니다.
    회원가입 후 자동으로 JWT 토큰을 발급합니다.
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "message": "회원가입이 완료되었습니다.",
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
