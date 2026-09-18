from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from .ai import AIService
from .config import Settings
from .db import Database


@dataclass
class CommandContext:
    user_openid: str
    raw_text: str
    group_openid: Optional[str] = None

    @property
    def is_group(self) -> bool:
        return bool(self.group_openid)


@dataclass
class CommandResult:
    text: Optional[str]


def strip_bot_mentions(text: str) -> str:
    # QQ Bot SDK 群消息中的 @ 通常会以 <@...> / <@!...> 形式出现。
    return re.sub(r"<@!?[^>]+>\s*", "", text or "")


def normalize_text(text: str) -> str:
    text = strip_bot_mentions(text).replace("\u3000", " ").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if text.startswith("小苹果"):
        text = text[len("小苹果") :].lstrip(" ，,：:")
    return text.strip()


class CommandRouter:
    def __init__(self, settings: Settings, db: Database, ai: AIService):
        self.settings = settings
        self.db = db
        self.ai = ai

    @staticmethod
    def _help(admin: bool) -> str:
        base = """小苹果 v0.2

我现在主要干两件事：
1）记住历届恋综和身份牌；
2）根据真实档案陪你聊、帮你挑本和挑身份牌。

可以直接问我：
“我想玩女强男弱，但不想男方太废，推荐一个。”
“我在P1和P3之间纠结，你先问我几个问题。”
“有没有事业线重、感情不太狗血的身份牌？”

我会在信息不够时反问，再从已经录入的真实档案里推荐。"""
        if admin:
            base += """

骰主录入：
录入恋综 P1
（之后每一段资料都要 @小苹果 发给我）
录入完成
取消录入

首次设置主群：在目标群里 @小苹果 发送“设为主群”。
查看已有档案可发送“档案列表”。"""
        return base

    @staticmethod
    def _extract_ingest_code(text: str) -> Optional[str]:
        patterns = [
            r"^(?:开始)?录入(?:恋综)?\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
            r"^覆盖(?:恋综)?\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
            r"^录入这辆[，,\s]*编号\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
        ]
        for pattern in patterns:
            m = re.match(pattern, text, flags=re.I)
            if m:
                return m.group(1).upper()
        return None

    async def handle(self, ctx: CommandContext) -> CommandResult:
        text = normalize_text(ctx.raw_text)
        is_admin = self.db.is_admin(ctx.user_openid)

        help_aliases = {
            "帮助", "help", "菜单", "你会什么", "你能干什么", "你能干啥",
            "你能干嘛", "我能干点啥", "我能干什么", "怎么玩", "怎么用",
        }
        archive_aliases = {"档案列表", "查看档案", "查看恋综", "恋综列表", "已有恋综"}

        # 私聊用于首次认主和骰主调试；正式聊天仍以主群为主。
        if not ctx.is_group:
            if text.startswith("认主 "):
                token = text.split(maxsplit=1)[1].strip()
                if token != self.settings.claim_token:
                    return CommandResult("认主口令不对。")
                self.db.claim_admin(ctx.user_openid)
                return CommandResult("认主成功。回主群 @我，发“设为主群”就行。")

            if text in help_aliases:
                return CommandResult(self._help(is_admin))

            if text in archive_aliases and is_admin:
                shows = self.db.list_shows()
                if not shows:
                    return CommandResult("你已经认主成功了。档案库现在还是空的；先回主群 @我 发“设为主群”，再开始录入。")
                lines = [f"{s.code}｜{s.full_name or s.title or s.code}｜v{s.version}" for s in shows]
                return CommandResult("现在有这些：\n" + "\n".join(lines))

            if is_admin:
                return CommandResult(
                    "你已经认主成功了，没有失忆。只是正式功能放在主群。\n"
                    "回主群 @我 发“设为主群”；想看我会什么，私聊发“帮助”也可以。"
                )

            return CommandResult("我现在主要在主群营业。骰主第一次使用时可以在这里发“认主 <口令>”。")

        # 尚未设置主群时，只允许已认主的骰主完成绑定。
        main_group = self.db.get_main_group()
        if not main_group:
            if is_admin and text == "设为主群":
                self.db.set_main_group(ctx.group_openid or "")
                return CommandResult("好了，这里就是我的主群。以后我只在这里回应。")
            if is_admin:
                return CommandResult("我还没认主群。就在这个群里 @我 发送“设为主群”。")
            return CommandResult(None)

        # 非主群完全静默，避免机器人到处营业。
        if ctx.group_openid != main_group:
            if is_admin and text == "设为主群":
                self.db.set_main_group(ctx.group_openid or "")
                return CommandResult("主群已改到这里。原来的群我就不回应了。")
            return CommandResult(None)

        # 正在录入时，除了“录入完成/取消录入”之外，其余 @ 消息全部视为原始资料片段。
        draft = self.db.get_draft(ctx.user_openid) if is_admin else None
        if draft:
            if text == "取消录入":
                code = draft.show_code
                self.db.cancel_draft(ctx.user_openid)
                return CommandResult(f"取消了，{code} 这次还没写进正式档案。")

            if text == "录入完成":
                code, chunks = self.db.draft_payload(ctx.user_openid)
                if not chunks:
                    return CommandResult("你还没给我正文。至少发一段资料再说“录入完成”。")
                raw_text = "\n\n".join(chunks)
                structured = await self.ai.parse_show(code=code, raw_text=raw_text)
                record = self.db.upsert_show(
                    code=code,
                    structured=structured,
                    raw_text=raw_text,
                    raw_chunks=chunks,
                )
                self.db.delete_draft_after_save(ctx.user_openid)
                cards = structured.get("identity_cards") or []
                display = record.full_name or record.title or record.code
                return CommandResult(
                    f"收好了。{record.code}｜{display}\n"
                    f"现在是 v{record.version}，识别到 {len(cards)} 张身份牌。\n"
                    "原文也整份留着；以后重新录同一个编号，会直接覆盖成新版本。"
                )

            # 只剥掉 @小苹果 本身，其余文字按这条消息的原样保存。
            chunk = strip_bot_mentions(ctx.raw_text).strip()
            if not chunk:
                return CommandResult("这条没有正文，我没存。")
            count = self.db.append_draft_chunk(ctx.user_openid, chunk)
            return CommandResult(f"收到第 {count} 段。继续发，最后跟我说“录入完成”。")

        if text in help_aliases:
            return CommandResult(self._help(is_admin))

        if text == "设为主群":
            if not is_admin:
                return CommandResult("这个只能骰主设置。")
            self.db.set_main_group(ctx.group_openid or "")
            return CommandResult("这里已经是主群。")

        code = self._extract_ingest_code(text)
        if code:
            if not is_admin:
                return CommandResult("录入档案只有骰主能用。")
            existing = self.db.get_show_by_code(code)
            self.db.start_draft(ctx.user_openid, code, mode="upsert")
            if existing:
                return CommandResult(
                    f"好，开始收 {code} 的新版。现在库里是 v{existing.version}；这次“录入完成”后会覆盖并升一个版本。\n"
                    "资料可以拆成多条，每条都 @我；原文会保存。"
                )
            return CommandResult(
                f"好，开始收 {code}。资料可以拆成多条，每条都 @我；最后说“录入完成”。原文会保存。"
            )

        if text in archive_aliases:
            if not is_admin:
                return CommandResult("档案列表先只给骰主看。你直接告诉我想玩什么，我帮你找。")
            shows = self.db.list_shows()
            if not shows:
                return CommandResult("档案库还是空的。")
            lines = [f"{s.code}｜{s.full_name or s.title or s.code}｜v{s.version}" for s in shows]
            return CommandResult("现在有这些：\n" + "\n".join(lines))

        if not text:
            return CommandResult(self._help(is_admin))

        # 其余内容都当正常聊天。AI 会读取真实档案索引，必要时先反问偏好。
        reply = await self.ai.reply(
            conversation_key=f"group:{ctx.group_openid}",
            user_text=text,
        )
        return CommandResult(reply)
