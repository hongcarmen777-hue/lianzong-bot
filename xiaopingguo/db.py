\
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_openid: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Show(Base):
    __tablename__ = "shows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("show_id", "slot", name="uq_player_show_slot"),
        UniqueConstraint("show_id", "name", name="uq_player_show_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    slot: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    user_openid: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    show: Mapped["Show"] = relationship()


class GroupBinding(Base):
    __tablename__ = "group_bindings"
    __table_args__ = (
        UniqueConstraint("group_openid", name="uq_group_openid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_openid: Mapped[str] = mapped_column(String(200), index=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    group_type: Mapped[str] = mapped_column(String(30))
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    show: Mapped["Show"] = relationship()
    player: Mapped[Optional["Player"]] = relationship()


class UserShowState(Base):
    __tablename__ = "user_show_states"
    __table_args__ = (
        UniqueConstraint("user_openid", name="uq_user_state_openid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_openid: Mapped[str] = mapped_column(String(200), index=True)
    active_show_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shows.id"), nullable=True)


class HeartLetter(Base):
    __tablename__ = "heart_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    sender_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    target_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    content: Mapped[str] = mapped_column(Text)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    owner_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    picker_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SmallGroupMember(Base):
    __tablename__ = "small_group_members"
    __table_args__ = (
        UniqueConstraint("group_binding_id", "player_id", name="uq_small_group_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_binding_id: Mapped[int] = mapped_column(ForeignKey("group_bindings.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)


class NPCProfile(Base):
    __tablename__ = "npc_profiles"
    __table_args__ = (
        UniqueConstraint("show_id", "name", name="uq_npc_show_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GroupMode(Base):
    __tablename__ = "group_modes"
    __table_args__ = (
        UniqueConstraint("group_openid", name="uq_group_mode_openid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_openid: Mapped[str] = mapped_column(String(200), index=True)
    npc_profile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("npc_profiles.id"), nullable=True)


class AIHistory(Base):
    __tablename__ = "ai_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_key: Mapped[str] = mapped_column(String(300), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Database:
    def __init__(self, url: str):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self):
        Base.metadata.create_all(self.engine)

    def is_admin(self, user_openid: str) -> bool:
        with self.Session() as s:
            return s.scalar(select(Admin).where(Admin.user_openid == user_openid)) is not None

    def claim_admin(self, user_openid: str):
        with self.Session.begin() as s:
            if s.scalar(select(Admin).where(Admin.user_openid == user_openid)) is None:
                s.add(Admin(user_openid=user_openid))

    def create_show(self, code: str, name: str) -> Show:
        code = code.strip().lower()
        with self.Session.begin() as s:
            existing = s.scalar(select(Show).where(Show.code == code))
            if existing:
                raise ValueError(f"恋综代号 {code} 已存在")
            show = Show(code=code, name=name.strip())
            s.add(show)
            s.flush()
            return show

    def get_show_by_code(self, code: str) -> Optional[Show]:
        with self.Session() as s:
            return s.scalar(select(Show).where(Show.code == code.strip().lower()))

    def get_show(self, show_id: int) -> Optional[Show]:
        with self.Session() as s:
            return s.get(Show, show_id)

    def list_shows(self) -> list[Show]:
        with self.Session() as s:
            return list(s.scalars(select(Show).order_by(Show.id)))

    def bind_group(
        self,
        group_openid: str,
        show_id: int,
        group_type: str,
        label: Optional[str] = None,
        player_id: Optional[int] = None,
    ) -> GroupBinding:
        with self.Session.begin() as s:
            binding = s.scalar(select(GroupBinding).where(GroupBinding.group_openid == group_openid))
            if binding:
                binding.show_id = show_id
                binding.group_type = group_type
                binding.label = label
                binding.player_id = player_id
            else:
                binding = GroupBinding(
                    group_openid=group_openid,
                    show_id=show_id,
                    group_type=group_type,
                    label=label,
                    player_id=player_id,
                )
                s.add(binding)
            s.flush()
            return binding

    def get_group_binding(self, group_openid: str) -> Optional[GroupBinding]:
        with self.Session() as s:
            stmt = select(GroupBinding).where(GroupBinding.group_openid == group_openid)
            return s.scalar(stmt)

    def list_group_bindings(self, show_id: int) -> list[GroupBinding]:
        with self.Session() as s:
            stmt = select(GroupBinding).where(GroupBinding.show_id == show_id).order_by(GroupBinding.id)
            return list(s.scalars(stmt))

    def add_player(self, show_id: int, slot: str, name: str) -> Player:
        with self.Session.begin() as s:
            player = Player(show_id=show_id, slot=slot.strip(), name=name.strip())
            s.add(player)
            s.flush()
            return player

    def get_player(self, show_id: int, slot_or_name: str) -> Optional[Player]:
        key = slot_or_name.strip()
        with self.Session() as s:
            stmt = select(Player).where(
                Player.show_id == show_id,
                (Player.slot == key) | (Player.name == key),
            )
            return s.scalar(stmt)

    def list_players(self, show_id: int, active_only: bool = True) -> list[Player]:
        with self.Session() as s:
            stmt = select(Player).where(Player.show_id == show_id)
            if active_only:
                stmt = stmt.where(Player.active.is_(True))
            stmt = stmt.order_by(Player.slot, Player.id)
            return list(s.scalars(stmt))

    def bind_player_user(self, player_id: int, user_openid: str):
        with self.Session.begin() as s:
            player = s.get(Player, player_id)
            if not player:
                raise ValueError("嘉宾不存在")
            player.user_openid = user_openid

    def players_for_user(self, user_openid: str) -> list[Player]:
        with self.Session() as s:
            stmt = select(Player).where(Player.user_openid == user_openid, Player.active.is_(True))
            return list(s.scalars(stmt))

    def set_active_show(self, user_openid: str, show_id: int):
        with self.Session.begin() as s:
            state = s.scalar(select(UserShowState).where(UserShowState.user_openid == user_openid))
            if state:
                state.active_show_id = show_id
            else:
                s.add(UserShowState(user_openid=user_openid, active_show_id=show_id))

    def get_active_show_for_user(self, user_openid: str) -> Optional[Show]:
        with self.Session() as s:
            state = s.scalar(select(UserShowState).where(UserShowState.user_openid == user_openid))
            if state and state.active_show_id:
                return s.get(Show, state.active_show_id)

            players = list(s.scalars(
                select(Player).where(Player.user_openid == user_openid, Player.active.is_(True))
            ))
            show_ids = sorted({p.show_id for p in players})
            if len(show_ids) == 1:
                return s.get(Show, show_ids[0])
            return None

    def player_for_user_in_show(self, user_openid: str, show_id: int) -> Optional[Player]:
        with self.Session() as s:
            stmt = select(Player).where(
                Player.user_openid == user_openid,
                Player.show_id == show_id,
                Player.active.is_(True),
            )
            return s.scalar(stmt)

    def add_heart_letter(
        self,
        show_id: int,
        sender_player_id: int,
        target_player_id: int,
        content: str,
        anonymous: bool = True,
    ) -> HeartLetter:
        with self.Session.begin() as s:
            letter = HeartLetter(
                show_id=show_id,
                sender_player_id=sender_player_id,
                target_player_id=target_player_id,
                content=content.strip(),
                anonymous=anonymous,
            )
            s.add(letter)
            s.flush()
            return letter

    def undelivered_letters_for_target(self, target_player_id: int) -> list[HeartLetter]:
        with self.Session() as s:
            stmt = (
                select(HeartLetter)
                .where(
                    HeartLetter.target_player_id == target_player_id,
                    HeartLetter.delivered.is_(False),
                )
                .order_by(HeartLetter.id)
            )
            return list(s.scalars(stmt))

    def mark_letter_delivered(self, letter_id: int):
        with self.Session.begin() as s:
            letter = s.get(HeartLetter, letter_id)
            if letter:
                letter.delivered = True

    def add_wish(self, show_id: int, owner_player_id: int, content: str) -> Wish:
        with self.Session.begin() as s:
            wish = Wish(show_id=show_id, owner_player_id=owner_player_id, content=content.strip())
            s.add(wish)
            s.flush()
            return wish

    def list_open_wishes(self, show_id: int) -> list[Wish]:
        with self.Session() as s:
            stmt = select(Wish).where(Wish.show_id == show_id, Wish.status == "open").order_by(Wish.id)
            return list(s.scalars(stmt))

    def pick_wish(self, wish_id: int, picker_player_id: int) -> Wish:
        with self.Session.begin() as s:
            wish = s.get(Wish, wish_id)
            if not wish or wish.status != "open":
                raise ValueError("这个心愿不存在或已经被摘走")
            if wish.owner_player_id == picker_player_id:
                raise ValueError("不能摘自己的心愿")
            wish.status = "picked"
            wish.picker_player_id = picker_player_id
            s.flush()
            return wish

    def set_small_group_members(self, group_binding_id: int, player_ids: list[int]):
        with self.Session.begin() as s:
            old = list(s.scalars(
                select(SmallGroupMember).where(SmallGroupMember.group_binding_id == group_binding_id)
            ))
            for row in old:
                s.delete(row)
            for pid in player_ids:
                s.add(SmallGroupMember(group_binding_id=group_binding_id, player_id=pid))

    def upsert_npc(self, show_id: int, name: str, prompt: str) -> NPCProfile:
        with self.Session.begin() as s:
            npc = s.scalar(select(NPCProfile).where(NPCProfile.show_id == show_id, NPCProfile.name == name))
            if npc:
                npc.prompt = prompt.strip()
            else:
                npc = NPCProfile(show_id=show_id, name=name.strip(), prompt=prompt.strip())
                s.add(npc)
            s.flush()
            return npc

    def get_npc(self, show_id: int, name: str) -> Optional[NPCProfile]:
        with self.Session() as s:
            return s.scalar(select(NPCProfile).where(NPCProfile.show_id == show_id, NPCProfile.name == name.strip()))

    def set_group_npc(self, group_openid: str, npc_profile_id: Optional[int]):
        with self.Session.begin() as s:
            mode = s.scalar(select(GroupMode).where(GroupMode.group_openid == group_openid))
            if mode:
                mode.npc_profile_id = npc_profile_id
            else:
                s.add(GroupMode(group_openid=group_openid, npc_profile_id=npc_profile_id))

    def get_group_npc(self, group_openid: str) -> Optional[NPCProfile]:
        with self.Session() as s:
            mode = s.scalar(select(GroupMode).where(GroupMode.group_openid == group_openid))
            if not mode or not mode.npc_profile_id:
                return None
            return s.get(NPCProfile, mode.npc_profile_id)

    def add_history(self, key: str, role: str, content: str):
        with self.Session.begin() as s:
            s.add(AIHistory(conversation_key=key, role=role, content=content))

    def get_history(self, key: str, limit: int) -> list[AIHistory]:
        with self.Session() as s:
            stmt = (
                select(AIHistory)
                .where(AIHistory.conversation_key == key)
                .order_by(AIHistory.id.desc())
                .limit(limit)
            )
            rows = list(s.scalars(stmt))
            rows.reverse()
            return rows
