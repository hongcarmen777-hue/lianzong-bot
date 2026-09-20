from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _json_load(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


@dataclass
class HTTPShowRecord:
    code: str
    series: str = ""
    title: str = ""
    full_name: str = ""
    tags_json: str = "[]"
    schedule_json: str = "{}"
    identity_cards_json: str = "[]"
    summary: str = ""
    metadata_json: str = "{}"
    raw_text: str = ""
    raw_chunks_json: str = "[]"
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class HTTPApplicationRecord:
    id: int
    show_code: str
    applicant_name: str = ""
    gender: str = ""
    age: str = ""
    preferred_card: str = ""
    tags_json: str = "[]"
    summary: str = ""
    parsed_json: str = "{}"
    raw_text: str = ""
    raw_chunks_json: str = "[]"
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None


class CloudBaseHTTPDatabase:
    """CloudBase MySQL REST API backend.

    Uses a server-side CloudBase API Key as a Bearer token. Tables are created
    once from cloudbase_mysql_setup.sql in the CloudBase SQL editor.
    """

    backend_name = "CloudBase MySQL HTTP API（持久化）"

    def __init__(self, env_id: str, api_key: str, *, timeout: int = 20):
        self.env_id = env_id.strip()
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.base_url = f"https://{self.env_id}.api.tcloudbasegateway.com/v1/rdb/rest"
        if not self.env_id or not self.api_key:
            raise ValueError("CloudBase HTTP 数据库需要 env_id 和 API Key")

    def create_all(self) -> None:
        # REST API is data-oriented; table DDL is intentionally kept visible
        # and explicit in cloudbase_mysql_setup.sql.
        return

    def verify_connection(self) -> None:
        """Fail fast unless the configured CloudBase database can really read AND write."""
        probe_key = "__xiaopingguo_db_probe__"
        probe_value = _now_sql()
        # A read-only check is not enough: the production bug we are guarding
        # against is "bot runs, but writes never reach MySQL".
        self.set_setting(probe_key, probe_value)
        read_back = self.get_setting(probe_key)
        if read_back != probe_value:
            raise RuntimeError("CloudBase MySQL 写入自检失败：探针写入后未能读回")
        self._delete("xp_settings", {"key": f"eq.{probe_key}"})
        # v0.2.7 requires the application table as part of the production schema.
        self._query("xp_applications", select="id", limit=1)

    def diagnostics(self) -> dict[str, Any]:
        # Every field below comes from a live HTTP query, not configuration guesses.
        return {
            "backend": self.backend_name,
            "env_id": self.env_id,
            "shows": len(self._query("xp_shows", select="code")),
            "admins": len(self._query("xp_admins", select="user_openid")),
            "drafts": len(self._query("xp_ingest_drafts", select="show_code")),
            "applications": len(self._query("xp_applications", select="id")),
        }

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: Optional[dict[str, Any]] = None,
        data: Any = None,
        prefer: Optional[str] = None,
    ) -> Any:
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            query = "?" + urlencode(clean, doseq=True, safe="(),.*[]%")
        url = f"{self.base_url}/{table}{query}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                text = raw.decode("utf-8")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"CloudBase MySQL HTTP API {exc.code}：{detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"CloudBase MySQL HTTP API 连接失败：{exc.reason}") from exc

    def _query(
        self,
        table: str,
        *,
        filters: Optional[dict[str, str]] = None,
        select: str = "*",
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": select}
        if filters:
            params.update(filters)
        if limit is not None:
            params["limit"] = str(limit)
        if order:
            params["order"] = order
        data = self._request("GET", table, params=params)
        return data if isinstance(data, list) else []

    def _insert(self, table: str, data: dict[str, Any]) -> None:
        self._request("POST", table, data=data)

    def _update(self, table: str, data: dict[str, Any], filters: dict[str, str]) -> None:
        self._request("PATCH", table, params=filters, data=data)

    def _delete(self, table: str, filters: dict[str, str]) -> None:
        self._request("DELETE", table, params=filters)

    @staticmethod
    def _show(row: dict[str, Any]) -> HTTPShowRecord:
        return HTTPShowRecord(
            code=str(row.get("code") or ""),
            series=str(row.get("series") or ""),
            title=str(row.get("title") or ""),
            full_name=str(row.get("full_name") or ""),
            tags_json=str(row.get("tags_json") or "[]"),
            schedule_json=str(row.get("schedule_json") or "{}"),
            identity_cards_json=str(row.get("identity_cards_json") or "[]"),
            summary=str(row.get("summary") or ""),
            metadata_json=str(row.get("metadata_json") or "{}"),
            raw_text=str(row.get("raw_text") or ""),
            raw_chunks_json=str(row.get("raw_chunks_json") or "[]"),
            version=int(row.get("version") or 1),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _application(row: dict[str, Any]) -> HTTPApplicationRecord:
        return HTTPApplicationRecord(
            id=int(row.get("id") or 0),
            show_code=str(row.get("show_code") or ""),
            applicant_name=str(row.get("applicant_name") or ""),
            gender=str(row.get("gender") or ""),
            age=str(row.get("age") or ""),
            preferred_card=str(row.get("preferred_card") or ""),
            tags_json=str(row.get("tags_json") or "[]"),
            summary=str(row.get("summary") or ""),
            parsed_json=str(row.get("parsed_json") or "{}"),
            raw_text=str(row.get("raw_text") or ""),
            raw_chunks_json=str(row.get("raw_chunks_json") or "[]"),
            version=int(row.get("version") or 1),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def is_admin(self, user_openid: str) -> bool:
        rows = self._query(
            "xp_admins",
            filters={"user_openid": f"eq.{user_openid}"},
            limit=1,
        )
        return bool(rows)

    def claim_admin(self, user_openid: str) -> None:
        if not self.is_admin(user_openid):
            self._insert("xp_admins", {"user_openid": user_openid})
        if not self.is_admin(user_openid):
            raise RuntimeError("CloudBase MySQL 管理员写入校验失败")

    def get_setting(self, key: str) -> Optional[str]:
        rows = self._query("xp_settings", filters={"key": f"eq.{key}"}, limit=1)
        return str(rows[0].get("value") or "") if rows else None

    def set_setting(self, key: str, value: str) -> None:
        rows = self._query("xp_settings", filters={"key": f"eq.{key}"}, limit=1)
        if rows:
            self._update("xp_settings", {"value": value}, {"key": f"eq.{key}"})
        else:
            self._insert("xp_settings", {"key": key, "value": value})

    def get_main_group(self) -> Optional[str]:
        return self.get_setting("main_group_openid")

    def set_main_group(self, group_openid: str) -> None:
        self.set_setting("main_group_openid", group_openid)

    def start_draft(self, admin_openid: str, show_code: str, mode: str = "upsert"):
        show_code = show_code.strip().upper()
        payload = {
            "show_code": show_code,
            "mode": mode,
            "chunks_json": "[]",
            "updated_at": _now_sql(),
        }
        rows = self._query(
            "xp_ingest_drafts",
            filters={"admin_openid": f"eq.{admin_openid}"},
            limit=1,
        )
        if rows:
            self._update(
                "xp_ingest_drafts", payload, {"admin_openid": f"eq.{admin_openid}"}
            )
        else:
            payload["admin_openid"] = admin_openid
            self._insert("xp_ingest_drafts", payload)
        saved = self.get_draft(admin_openid)
        if not saved or str(getattr(saved, "show_code", "")).upper() != show_code:
            raise RuntimeError("CloudBase MySQL 草稿写入校验失败")
        return saved

    def get_draft(self, admin_openid: str):
        rows = self._query(
            "xp_ingest_drafts",
            filters={"admin_openid": f"eq.{admin_openid}"},
            limit=1,
        )
        return SimpleNamespace(**rows[0]) if rows else None

    def append_draft_chunk(self, admin_openid: str, content: str) -> int:
        row = self.get_draft(admin_openid)
        if not row:
            raise ValueError("当前没有正在录入的恋综")
        chunks = _json_load(getattr(row, "chunks_json", "[]"), [])
        chunks.append(content)
        encoded = json.dumps(chunks, ensure_ascii=False)
        self._update(
            "xp_ingest_drafts",
            {"chunks_json": encoded, "updated_at": _now_sql()},
            {"admin_openid": f"eq.{admin_openid}"},
        )
        saved = self.get_draft(admin_openid)
        if not saved or str(getattr(saved, "chunks_json", "")) != encoded:
            raise RuntimeError("CloudBase MySQL 草稿内容写入校验失败")
        return len(chunks)

    def cancel_draft(self, admin_openid: str) -> None:
        if self.get_draft(admin_openid):
            self._delete("xp_ingest_drafts", {"admin_openid": f"eq.{admin_openid}"})

    def draft_payload(self, admin_openid: str) -> tuple[str, list[str]]:
        row = self.get_draft(admin_openid)
        if not row:
            raise ValueError("当前没有正在录入的恋综")
        chunks = _json_load(getattr(row, "chunks_json", "[]"), [])
        return str(row.show_code), chunks

    def get_show_by_code(self, code: str) -> Optional[HTTPShowRecord]:
        code = code.strip().upper()
        rows = self._query("xp_shows", filters={"code": f"eq.{code}"}, limit=1)
        return self._show(rows[0]) if rows else None

    def list_shows(self) -> list[HTTPShowRecord]:
        rows = self._query("xp_shows", order="updated_at.desc")
        return [self._show(row) for row in rows]

    def upsert_show(
        self,
        *,
        code: str,
        structured: dict,
        raw_text: str,
        raw_chunks: list[str],
    ) -> HTTPShowRecord:
        code = code.strip().upper()
        tags = structured.get("tags") or []
        deadlines = structured.get("deadlines") or {}
        days = structured.get("days") or []
        cards = structured.get("identity_cards") or []
        schedule = {"deadlines": deadlines, "days": days}
        existing = self.get_show_by_code(code)
        version = (existing.version + 1) if existing else 1
        payload = {
            "series": str(structured.get("series") or ""),
            "title": str(structured.get("title") or ""),
            "full_name": str(structured.get("full_name") or code),
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "schedule_json": json.dumps(schedule, ensure_ascii=False),
            "identity_cards_json": json.dumps(cards, ensure_ascii=False),
            "summary": str(structured.get("summary") or ""),
            "metadata_json": json.dumps(structured, ensure_ascii=False),
            "raw_text": raw_text,
            "raw_chunks_json": json.dumps(raw_chunks, ensure_ascii=False),
            "version": version,
            "updated_at": _now_sql(),
        }
        if existing:
            self._update("xp_shows", payload, {"code": f"eq.{code}"})
        else:
            payload["code"] = code
            self._insert("xp_shows", payload)

        # Never announce success from the request alone. Re-read the persistent
        # row and verify the exact raw archive + version actually landed.
        saved = self.get_show_by_code(code)
        if saved is None:
            raise RuntimeError(f"CloudBase MySQL 落库校验失败：{code} 写入后查不到")
        if saved.version != version or saved.raw_text != raw_text:
            raise RuntimeError(f"CloudBase MySQL 落库校验失败：{code} 读回内容/版本不一致")
        return saved

    def save_application(
        self,
        *,
        show_code: str,
        structured: dict,
        raw_text: str,
        raw_chunks: list[str],
    ) -> HTTPApplicationRecord:
        show_code = show_code.strip().upper()
        applicant_name = str(structured.get("applicant_name") or "").strip()
        filters = {"show_code": f"eq.{show_code}"}
        if applicant_name:
            filters["applicant_name"] = f"eq.{applicant_name}"
            rows = self._query("xp_applications", filters=filters, limit=1, order="id.desc")
        else:
            rows = []
        existing = self._application(rows[0]) if rows else None
        version = (existing.version + 1) if existing else 1
        payload = {
            "show_code": show_code,
            "applicant_name": applicant_name,
            "gender": str(structured.get("gender") or ""),
            "age": str(structured.get("age") or ""),
            "preferred_card": str(structured.get("preferred_card") or ""),
            "tags_json": json.dumps(structured.get("tags") or [], ensure_ascii=False),
            "summary": str(structured.get("summary") or ""),
            "parsed_json": json.dumps(structured, ensure_ascii=False),
            "raw_text": raw_text,
            "raw_chunks_json": json.dumps(raw_chunks, ensure_ascii=False),
            "version": version,
            "updated_at": _now_sql(),
        }
        if existing:
            self._update("xp_applications", payload, {"id": f"eq.{existing.id}"})
            expected_id = existing.id
        else:
            self._insert("xp_applications", payload)
            # Query back the newest form for this show. The exact raw_text is verified
            # immediately below, without placing a potentially huge form into the URL.
            verify_filters = {"show_code": f"eq.{show_code}"}
            saved_rows = self._query("xp_applications", filters=verify_filters, limit=1, order="id.desc")
            if not saved_rows:
                raise RuntimeError("CloudBase MySQL 一表落库校验失败：写入后查不到")
            expected_id = int(saved_rows[0].get("id") or 0)

        saved_rows = self._query("xp_applications", filters={"id": f"eq.{expected_id}"}, limit=1)
        if not saved_rows:
            raise RuntimeError("CloudBase MySQL 一表落库校验失败：按 ID 读回失败")
        saved = self._application(saved_rows[0])
        if saved.raw_text != raw_text or saved.version != version:
            raise RuntimeError("CloudBase MySQL 一表落库校验失败：读回内容/版本不一致")
        return saved

    def list_applications(self, show_code: str | None = None) -> list[HTTPApplicationRecord]:
        filters = {"show_code": f"eq.{show_code.strip().upper()}"} if show_code else None
        rows = self._query("xp_applications", filters=filters, order="updated_at.desc")
        return [self._application(row) for row in rows]

    def get_application_by_id(self, application_id: int) -> Optional[HTTPApplicationRecord]:
        rows = self._query("xp_applications", filters={"id": f"eq.{application_id}"}, limit=1)
        return self._application(rows[0]) if rows else None

    def application_context(self, max_chars: int = 50000) -> str:
        rows = self.list_applications()
        if not rows:
            return "（还没有录入一表。）"
        blocks: list[str] = []
        total = 0
        for row in rows:
            parsed = _json_load(row.parsed_json, {})
            lines = [f"【一表#{row.id}｜{row.show_code}｜{row.applicant_name or '未识别名称'}｜v{row.version}】"]
            if row.preferred_card:
                lines.append("意向身份牌：" + row.preferred_card)
            tags = _json_load(row.tags_json, [])
            if tags:
                lines.append("关键词：" + " / ".join(str(x) for x in tags[:10]))
            prefs = parsed.get("preferences") or []
            if prefs:
                lines.append("偏好：" + " / ".join(str(x) for x in prefs[:8]))
            bounds = parsed.get("boundaries") or []
            if bounds:
                lines.append("边界：" + " / ".join(str(x) for x in bounds[:8]))
            if row.summary:
                lines.append("概括：" + row.summary.strip())
            fields = parsed.get("fields") or []
            compact_fields = []
            for item in fields[:12]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "").strip()
                value = str(item.get("value") or "").strip().replace("\n", " ")
                if label and value:
                    compact_fields.append(f"{label}={value[:180]}")
            if compact_fields:
                lines.append("表内字段：" + "；".join(compact_fields))
            block = "\n".join(lines)
            if total + len(block) > max_chars:
                break
            blocks.append(block)
            total += len(block) + 2
        return "\n\n".join(blocks)

    def delete_draft_after_save(self, admin_openid: str) -> None:
        self.cancel_draft(admin_openid)

    def add_history(self, key: str, role: str, content: str) -> None:
        self._insert(
            "xp_ai_history",
            {"conversation_key": key, "role": role, "content": content},
        )

    def get_history(self, key: str, limit: int):
        rows = self._query(
            "xp_ai_history",
            filters={"conversation_key": f"eq.{key}"},
            limit=limit,
            order="id.desc",
        )
        rows.reverse()
        return [SimpleNamespace(**row) for row in rows]

    def archive_context(self, max_chars: int = 70000) -> str:
        shows = self.list_shows()
        if not shows:
            return "（目前还没有录入任何恋综档案。）"

        blocks: list[str] = []
        total = 0
        for show in shows:
            tags = _json_load(show.tags_json, [])
            schedule = _json_load(show.schedule_json, {})
            cards = _json_load(show.identity_cards_json, [])

            lines = [f"【{show.code}｜{show.full_name or show.title or show.code}】"]
            if tags:
                lines.append("TAG：" + " / ".join(str(x) for x in tags))
            if show.summary:
                lines.append("概况：" + show.summary.strip())

            deadlines = schedule.get("deadlines") or {}
            if deadlines:
                compact = "；".join(f"{k}={v}" for k, v in deadlines.items() if v)
                if compact:
                    lines.append("时间：" + compact)

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
                        lines.append("  原文摘录：" + raw[:450].replace("\n", " "))

            block = "\n".join(lines)
            if total + len(block) > max_chars:
                break
            blocks.append(block)
            total += len(block) + 2
        return "\n\n".join(blocks)
