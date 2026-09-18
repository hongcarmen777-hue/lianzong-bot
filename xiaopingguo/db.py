from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


LONG_TEXT = Text().with_variant(LONGTEXT(), "mysql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_load(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "xp_admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_openid: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BotSetting(Base):
    __tablename__ = "xp_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(LONG_TEXT)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ShowRecord(Base):
    __tablename__ = "xp_shows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    series: Mapped[str] = mapped_column(String(150), default="")
    title: Mapped[str] = mapped_column(String(250), default="")
    full_name: Mapped[str] = mapped_column(String(350), default="")
    tags_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    schedule_json: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    identity_cards_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    summary: Mapped[str] = mapped_column(LONG_TEXT, default="")
    metadata_json: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    raw_text: Mapped[str] = mapped_column(LONG_TEXT)
    raw_chunks_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)


class IngestDraft(Base):
    __tablename__ = "xp_ingest_drafts"
    __table_args__ = (UniqueConstraint("admin_openid", name="uq_xp_draft_admin"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_openid: Mapped[str] = mapped_column(String(200), index=True)
    show_code: Mapped[str] = mapped_column(String(40), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="upsert")
    chunks_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AIHistory(Base):
    __tablename__ = "xp_ai_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_key: Mapped[str] = mapped_column(String(300), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(LONG_TEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Database:
    def __init__(self, url: str):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def is_admin(self, user_openid: str) -> bool:
        with self.Session() as s:
            return s.scalar(select(Admin).where(Admin.user_openid == user_openid)) is not None

    def claim_admin(self, user_openid: str) -> None:
        with self.Session.begin() as s:
            if s.scalar(select(Admin).where(Admin.user_openid == user_openid)) is None:
                s.add(Admin(user_openid=user_openid))

    def get_setting(self, key: str) -> Optional[str]:
        with self.Session() as s:
            row = s.scalar(select(BotSetting).where(BotSetting.key == key))
            return row.value if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.Session.begin() as s:
            row = s.scalar(select(BotSetting).where(BotSetting.key == key))
            if row:
                row.value = value
                row.updated_at = utcnow()
            else:
                s.add(BotSetting(key=key, value=value))

    def get_main_group(self) -> Optional[str]:
        return self.get_setting("main_group_openid")

    def set_main_group(self, group_openid: str) -> None:
        self.set_setting("main_group_openid", group_openid)

    def start_draft(self, admin_openid: str, show_code: str, mode: str = "upsert") -> IngestDraft:
        show_code = show_code.strip().upper()
        with self.Session.begin() as s:
            row = s.scalar(select(IngestDraft).where(IngestDraft.admin_openid == admin_openid))
            if row:
                row.show_code = show_code
                row.mode = mode
                row.chunks_json = "[]"
                row.updated_at = utcnow()
            else:
                row = IngestDraft(admin_openid=admin_openid, show_code=show_code, mode=mode, chunks_json="[]")
                s.add(row)
            s.flush()
            return row

    def get_draft(self, admin_openid: str) -> Optional[IngestDraft]:
        with self.Session() as s:
            return s.scalar(select(IngestDraft).where(IngestDraft.admin_openid == admin_openid))

    def append_draft_chunk(self, admin_openid: str, content: str) -> int:
        with self.Session.begin() as s:
            row = s.scalar(select(IngestDraft).where(IngestDraft.admin_openid == admin_openid))
            if not row:
                raise ValueError("当前没有正在录入的恋综")
            chunks = _json_load(row.chunks_json, [])
            chunks.append(content)
            row.chunks_json = json.dumps(chunks, ensure_ascii=False)
            row.updated_at = utcnow()
            return len(chunks)

    def cancel_draft(self, admin_openid: str) -> None:
        with self.Session.begin() as s:
            row = s.scalar(select(IngestDraft).where(IngestDraft.admin_openid == admin_openid))
            if row:
                s.delete(row)

    def draft_payload(self, admin_openid: str) -> tuple[str, list[str]]:
        with self.Session() as s:
            row = s.scalar(select(IngestDraft).where(IngestDraft.admin_openid == admin_openid))
            if not row:
                raise ValueError("当前没有正在录入的恋综")
            chunks = _json_load(row.chunks_json, [])
            return row.show_code, chunks

    def get_show_by_code(self, code: str) -> Optional[ShowRecord]:
        code = code.strip().upper()
        with self.Session() as s:
            return s.scalar(select(ShowRecord).where(ShowRecord.code == code))

    def list_shows(self) -> list[ShowRecord]:
        with self.Session() as s:
            return list(s.scalars(select(ShowRecord).order_by(ShowRecord.updated_at.desc(), ShowRecord.id.desc())))

    def upsert_show(
        self,
        *,
        code: str,
        structured: dict,
        raw_text: str,
        raw_chunks: list[str],
    ) -> ShowRecord:
        code = code.strip().upper()
        tags = structured.get("tags") or []
        deadlines = structured.get("deadlines") or {}
        days = structured.get("days") or []
        cards = structured.get("identity_cards") or []
        schedule = {"deadlines": deadlines, "days": days}

        with self.Session.begin() as s:
            row = s.scalar(select(ShowRecord).where(ShowRecord.code == code))
            if row:
                row.series = str(structured.get("series") or "")
                row.title = str(structured.get("title") or "")
                row.full_name = str(structured.get("full_name") or code)
                row.tags_json = json.dumps(tags, ensure_ascii=False)
                row.schedule_json = json.dumps(schedule, ensure_ascii=False)
                row.identity_cards_json = json.dumps(cards, ensure_ascii=False)
                row.summary = str(structured.get("summary") or "")
                row.metadata_json = json.dumps(structured, ensure_ascii=False)
                row.raw_text = raw_text
                row.raw_chunks_json = json.dumps(raw_chunks, ensure_ascii=False)
                row.version += 1
                row.updated_at = utcnow()
            else:
                row = ShowRecord(
                    code=code,
                    series=str(structured.get("series") or ""),
                    title=str(structured.get("title") or ""),
                    full_name=str(structured.get("full_name") or code),
                    tags_json=json.dumps(tags, ensure_ascii=False),
                    schedule_json=json.dumps(schedule, ensure_ascii=False),
                    identity_cards_json=json.dumps(cards, ensure_ascii=False),
                    summary=str(structured.get("summary") or ""),
                    metadata_json=json.dumps(structured, ensure_ascii=False),
                    raw_text=raw_text,
                    raw_chunks_json=json.dumps(raw_chunks, ensure_ascii=False),
                    version=1,
                )
                s.add(row)
            s.flush()
            return row

    def delete_draft_after_save(self, admin_openid: str) -> None:
        self.cancel_draft(admin_openid)

    def add_history(self, key: str, role: str, content: str) -> None:
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

    def archive_context(self, max_chars: int = 80000) -> str:
        shows = self.list_shows()
        if not shows:
            return "（档案库目前为空）"

        blocks: list[str] = []
        total = 0
        for show in shows:
            tags = _json_load(show.tags_json, [])
            cards = _json_load(show.identity_cards_json, [])
            schedule = _json_load(show.schedule_json, {})
            lines = [f"【{show.code}｜{show.full_name or show.title or show.code}】"]
            if tags:
                lines.append("TAG：" + " / ".join(str(x) for x in tags))
            if show.summary:
                lines.append("概况：" + show.summary.strip())

            deadlines = schedule.get("deadlines") or {}
            if deadlines:
                compact_deadlines = "；".join(f"{k}={v}" for k, v in deadlines.items() if v)
                if compact_deadlines:
                    lines.append("时间：" + compact_deadlines)

            if cards:
                lines.append("身份牌：")
                for card in cards:
                    number = card.get("number", "")
                    header = card.get("header", "")
                    rel = card.get("relationship", "")
                    themes = card.get("themes") or []
                    summary = str(card.get("summary") or "").strip()
                    raw = str(card.get("raw") or "").strip()
                    lines.append(f"- {number}｜{header}" if header else f"- {number}")
                    if rel:
                        lines.append(f"  关系：{rel}")
                    if themes:
                        lines.append("  关键词：" + " / ".join(str(x) for x in themes[:8]))
                    if summary:
                        lines.append("  简述：" + summary)
                    elif raw:
                        excerpt = raw[:450].replace("\n", " ")
                        lines.append("  原文摘录：" + excerpt)

            block = "\n".join(lines)
            if total + len(block) > max_chars:
                break
            blocks.append(block)
            total += len(block) + 2

        return "\n\n".join(blocks)
