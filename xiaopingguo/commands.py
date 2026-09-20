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
        base = """小苹果 v0.2.7

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

骰主后台（请私聊我）：
录入恋综 P1 —— 收完整恋综档案
录入一表 P1 —— 收这届的一张报名一表
（之后直接连续私聊发送正文，不用 @我）
录入完成
取消录入

重新录同一个恋综编号会覆盖旧档案并升版本；同一届同名一表会更新版本。
查看：档案列表 / 一表列表 / 一表列表 P1 / 查看一表 12
首次设置主群：在目标群里 @小苹果 发送“设为主群”。"""
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

    @staticmethod
    def _extract_application_code(text: str) -> Optional[str]:
        patterns = [
            r"^(?:开始)?录入一表\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
            r"^一表录入\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
            r"^收一表\s*([A-Za-z0-9_-]*P\d+|P\d+)$",
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
        status_aliases = {"版本", "数据库状态", "存储状态", "小苹果版本"}

        if text in status_aliases:
            backend = getattr(self.db, "backend_name", "未知")
            try:
                d = self.db.diagnostics()
                return CommandResult(
                    f"小苹果 v0.2.7｜数据库：{backend}｜恋综 {d.get('shows', 0)}｜一表 {d.get('applications', 0)}｜草稿 {d.get('drafts', 0)}"
                )
            except Exception:
                return CommandResult(f"小苹果 v0.2.7｜数据库：{backend}")

        # 私聊是骰主后台：认主、档案录入/覆盖、查看档案，以及后台自然聊天。
        if not ctx.is_group:
            if text.startswith("认主 "):
                token = text.split(maxsplit=1)[1].strip()
                if token != self.settings.claim_token:
                    return CommandResult("认主口令不对。")
                self.db.claim_admin(ctx.user_openid)
                return CommandResult("认主成功。以后恋综档案直接私聊我录入；主群只负责对外查询和推荐。")

            if text in help_aliases:
                return CommandResult(self._help(is_admin))

            if not is_admin:
                return CommandResult("我现在主要在主群营业。骰主第一次使用时可以在这里发“认主 <口令>”。")

            # 骰主正在私聊录入：除完成/取消外，其余消息都按原文作为资料片段保存。
            draft = self.db.get_draft(ctx.user_openid)
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
                    mode = str(getattr(draft, "mode", "upsert") or "upsert")
                    if mode == "application":
                        structured = await self.ai.parse_application(show_code=code, raw_text=raw_text)
                        record = self.db.save_application(
                            show_code=code,
                            structured=structured,
                            raw_text=raw_text,
                            raw_chunks=chunks,
                        )
                        self.db.delete_draft_after_save(ctx.user_openid)
                        name = record.applicant_name or "未识别名称"
                        card = f"｜意向 {record.preferred_card}" if record.preferred_card else ""
                        return CommandResult(
                            f"一表落库成功。#{record.id}｜{record.show_code}｜{name}{card}｜v{record.version}\n"
                            "原文和结构化索引都已经存进 MySQL。以后私聊我可以按这一表继续查。"
                        )

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
                        "已经写进共享档案库；主群现在就能从这份资料里查询和推荐。"
                    )

                chunk = (ctx.raw_text or "").strip()
                if not chunk:
                    return CommandResult("这条没有正文，我没存。")
                count = self.db.append_draft_chunk(ctx.user_openid, chunk)
                if str(getattr(draft, "mode", "")) == "application":
                    return CommandResult(f"收到一表第 {count} 段。继续直接私聊发，最后跟我说“录入完成”。")
                return CommandResult(f"收到第 {count} 段。继续直接私聊发，最后跟我说“录入完成”。")

            app_code = self._extract_application_code(text)
            if app_code:
                self.db.start_draft(ctx.user_openid, app_code, mode="application")
                show = self.db.get_show_by_code(app_code)
                known = f"（已关联到 {show.full_name or show.title or show.code}）" if show else "（这届恋综档案还没入库也没关系，可以先存一表）"
                return CommandResult(
                    f"好，开始收 {app_code} 的一表{known}。接下来直接把这张一表发给我，不用 @我；"
                    "可以分段，最后说“录入完成”。原文会完整保存。"
                )

            code = self._extract_ingest_code(text)
            if code:
                existing = self.db.get_show_by_code(code)
                self.db.start_draft(ctx.user_openid, code, mode="upsert")
                if existing:
                    return CommandResult(
                        f"好，开始收 {code} 的新版。现在库里是 v{existing.version}；这次“录入完成”后会覆盖并升一个版本。\n"
                        "接下来直接私聊把资料分段发给我，不用 @我；原文会完整保存。"
                    )
                return CommandResult(
                    f"好，开始收 {code}。接下来直接私聊把资料分段发给我，不用 @我；"
                    "最后说“录入完成”。原文会完整保存。"
                )

            if text in archive_aliases:
                shows = self.db.list_shows()
                if not shows:
                    return CommandResult("档案库现在还是空的。私聊我发“录入恋综 P1”就可以开始。")
                lines = [f"{sh.code}｜{sh.full_name or sh.title or sh.code}｜v{sh.version}" for sh in shows]
                return CommandResult("现在有这些：\n" + "\n".join(lines))

            app_list = re.match(r"^(?:一表列表|报名列表)(?:\s+([A-Za-z0-9_-]*P\d+|P\d+))?$", text, flags=re.I)
            if app_list:
                code_filter = app_list.group(1).upper() if app_list.group(1) else None
                rows = self.db.list_applications(code_filter)
                if not rows:
                    return CommandResult(f"{code_filter + ' ' if code_filter else ''}还没有录入一表。")
                lines = []
                for row in rows[:30]:
                    card = f"｜意向 {row.preferred_card}" if row.preferred_card else ""
                    lines.append(f"#{row.id}｜{row.show_code}｜{row.applicant_name or '未识别名称'}{card}｜v{row.version}")
                suffix = "\n（只显示最近30张）" if len(rows) > 30 else ""
                return CommandResult("已录入的一表：\n" + "\n".join(lines) + suffix)

            app_detail = re.match(r"^(?:查看一表|一表详情)\s*#?(\d+)$", text)
            if app_detail:
                row = self.db.get_application_by_id(int(app_detail.group(1)))
                if not row:
                    return CommandResult("没找到这张一表。")
                return CommandResult(
                    f"一表#{row.id}｜{row.show_code}｜{row.applicant_name or '未识别名称'}｜v{row.version}\n\n{row.raw_text}"
                )

            # 能确定回答的程序能力问题优先由代码回答；其他内容交给 AI 自然聊天。
            if re.search(r"后台群|个人群|小群|多个群", text):
                return CommandResult(
                    "不能设置后台群，也不需要另建后台群。现在骰主直接私聊我录入、覆盖和查看恋综档案；"
                    "主群只负责给嘉宾查询、聊天和推荐。"
                )

            # 防止 AI 沿用旧版本口径，错误地把骰主赶回主群录入。
            if (
                len(text) <= 160
                and re.search(r"录入|入库|落库", text)
                and re.search(r"怎么|如何|能不能|可以|需要|是不是|主群|私聊|小窗|这里", text)
            ):
                return CommandResult(
                    "可以直接在这个私聊里落库，不用回主群。完整恋综发“录入恋综 P1”；收到的一表发“录入一表 P1”。"
                    "然后连续把正文发给我，最后发“录入完成”。"
                )

            reply = await self.ai.reply(
                conversation_key=f"c2c:v027:{ctx.user_openid}",
                user_text=text,
                admin_private=True,
            )
            return CommandResult(reply)

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

        # 档案录入只走骰主私聊；主群保持干净，只负责查询、聊天和推荐。
        code = self._extract_ingest_code(text)
        app_code = self._extract_application_code(text)
        if code or app_code or text in {"录入完成", "取消录入"}:
            if not is_admin:
                return CommandResult("档案录入只有骰主能用。")
            return CommandResult("档案后台在私聊。完整恋综发“录入恋综 P1”；一表发“录入一表 P1”，然后连续发送正文，最后发“录入完成”。")

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
            conversation_key=f"group:v027:{ctx.group_openid}",
            user_text=text,
        )
        return CommandResult(reply)
