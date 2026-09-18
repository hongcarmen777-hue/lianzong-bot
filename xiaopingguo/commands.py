\
from __future__ import annotations

from dataclasses import dataclass
import random
import re
from typing import Optional

from .config import Settings
from .db import Database, Show, GroupBinding
from .ai import AIService


GROUP_TYPES = {
    "主群": "main",
    "大群": "main",
    "后台群": "backstage",
    "后台": "backstage",
    "个人群": "personal",
    "小群": "small",
    "地点群": "location",
    "游戏群": "game",
    "复盘群": "review",
    "其他": "other",
}

GROUP_TYPE_CN = {
    "main": "主群",
    "backstage": "后台群",
    "personal": "个人群",
    "small": "小群",
    "location": "地点群",
    "game": "游戏群",
    "review": "复盘群",
    "other": "其他群",
}


@dataclass
class CommandContext:
    user_openid: str
    text: str
    group_openid: Optional[str] = None

    @property
    def is_group(self) -> bool:
        return bool(self.group_openid)


@dataclass
class CommandResult:
    text: str
    proactive_group_messages: list[tuple[str, str]] | None = None


def normalize_text(text: str) -> str:
    text = re.sub(r"<@!?[^>]+>", "", text or "")
    text = text.replace("\u3000", " ").strip()
    if text.startswith("/"):
        text = text[1:].strip()
    if text.startswith("小苹果"):
        text = text[len("小苹果"):].lstrip(" ，,：:")
    return text.strip()


class CommandRouter:
    def __init__(self, settings: Settings, db: Database, ai: AIService):
        self.settings = settings
        self.db = db
        self.ai = ai

    def _show_from_group(self, group_openid: Optional[str]) -> tuple[Optional[Show], Optional[GroupBinding]]:
        if not group_openid:
            return None, None
        binding = self.db.get_group_binding(group_openid)
        if not binding:
            return None, None
        return self.db.get_show(binding.show_id), binding

    def _resolve_show(self, ctx: CommandContext) -> tuple[Optional[Show], Optional[GroupBinding]]:
        show, binding = self._show_from_group(ctx.group_openid)
        if show:
            return show, binding
        return self.db.get_active_show_for_user(ctx.user_openid), None

    def _require_admin(self, ctx: CommandContext) -> Optional[CommandResult]:
        if not self.db.is_admin(ctx.user_openid):
            return CommandResult("这个操作只有骰主可以用。先私聊小苹果完成“认主”。")
        return None

    def _help(self, admin: bool) -> str:
        base = """小苹果 v0.1

普通功能：
帮助
恋综列表
切换 <恋综代号>
登记我 <嘉宾序号/名字>
嘉宾列表
随机嘉宾 <人数>
心动信 <目标序号/名字> <内容>
挂心愿 <内容>
心愿墙
摘心愿 <编号>

AI / NPC：
问 <问题>
NPC退出

群里使用时请 @小苹果 再输入指令。私聊不用 @。"""

        if admin:
            base += """

骰主功能：
新建恋综 <代号> | <名称>
绑定 <恋综代号> <主群/后台群/个人群/小群/地点群/游戏群/复盘群> [标签或嘉宾]
群列表
嘉宾添加 <恋综代号> <序号> | <姓名>
小群成员 <嘉宾1> <嘉宾2> ...
NPC设置 <名字> | <人设>
NPC进入 <名字>
公告 <本群/主群/个人群/全部> <内容>

首次认主（只能私聊）：
认主 <CLAIM_TOKEN>"""
        return base

    async def handle(self, ctx: CommandContext) -> CommandResult:
        text = normalize_text(ctx.text)
        is_admin = self.db.is_admin(ctx.user_openid)

        if not text:
            return CommandResult(self._help(is_admin))

        if text in {"帮助", "help", "菜单"}:
            return CommandResult(self._help(is_admin))

        if text.startswith("认主 "):
            if ctx.is_group:
                return CommandResult("认主口令不要发在群里。请私聊小苹果。")
            token = text.split(maxsplit=1)[1].strip()
            if token != self.settings.claim_token:
                return CommandResult("认主口令不对。")
            self.db.claim_admin(ctx.user_openid)
            return CommandResult("认主成功。以后你就是小苹果识别的骰主。")

        if text == "恋综列表":
            shows = self.db.list_shows()
            if not shows:
                return CommandResult("现在还没有建立任何恋综。")
            lines = [f"{s.code}｜{s.name}{'' if s.active else '（已结束）'}" for s in shows]
            return CommandResult("目前的小苹果恋综：\n" + "\n".join(lines))

        if text.startswith("切换 "):
            code = text.split(maxsplit=1)[1]
            show = self.db.get_show_by_code(code)
            if not show:
                return CommandResult("没找到这个恋综代号。")
            self.db.set_active_show(ctx.user_openid, show.id)
            return CommandResult(f"已把你的当前恋综切换为《{show.name}》。")

        if text.startswith("新建恋综 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            raw = text[len("新建恋综 "):].strip()
            if "|" not in raw:
                return CommandResult("格式：新建恋综 <代号> | <名称>\n例如：新建恋综 eden | 离开伊甸以后")
            code, name = [x.strip() for x in raw.split("|", 1)]
            if not code or not name:
                return CommandResult("代号和名称都不能为空。")
            try:
                show = self.db.create_show(code, name)
            except ValueError as e:
                return CommandResult(str(e))
            self.db.set_active_show(ctx.user_openid, show.id)
            return CommandResult(f"已建立《{show.name}》，代号 {show.code}。")

        if text.startswith("嘉宾添加 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            raw = text[len("嘉宾添加 "):].strip()
            parts = raw.split(maxsplit=2)
            if len(parts) < 3:
                return CommandResult("格式：嘉宾添加 <恋综代号> <序号> | <姓名>")
            code, rest = parts[0], raw[len(parts[0]):].strip()
            if "|" not in rest:
                return CommandResult("格式：嘉宾添加 <恋综代号> <序号> | <姓名>")
            slot, name = [x.strip() for x in rest.split("|", 1)]
            show = self.db.get_show_by_code(code)
            if not show:
                return CommandResult("没找到这个恋综。")
            try:
                player = self.db.add_player(show.id, slot, name)
            except Exception:
                return CommandResult("这个序号或姓名已经存在了。")
            return CommandResult(f"已加入嘉宾：{player.slot}｜{player.name}")

        if text.startswith("绑定 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            if not ctx.group_openid:
                return CommandResult("“绑定群”要在你准备绑定的那个 QQ 群里操作。")
            parts = text.split(maxsplit=3)
            if len(parts) < 3:
                return CommandResult("格式：绑定 <恋综代号> <群类型> [标签/嘉宾]")
            _, code, type_cn, *rest = parts
            show = self.db.get_show_by_code(code)
            if not show:
                return CommandResult("没找到这个恋综。")
            group_type = GROUP_TYPES.get(type_cn)
            if not group_type:
                return CommandResult("群类型支持：主群、后台群、个人群、小群、地点群、游戏群、复盘群。")

            label = rest[0].strip() if rest else None
            player_id = None
            if group_type == "personal":
                if not label:
                    return CommandResult("个人群需要写嘉宾序号或姓名，例如：绑定 eden 个人群 01")
                player = self.db.get_player(show.id, label)
                if not player:
                    return CommandResult("没找到这个嘉宾。先用“嘉宾添加”登记。")
                player_id = player.id
                label = f"{player.slot}｜{player.name}"

            binding = self.db.bind_group(
                group_openid=ctx.group_openid,
                show_id=show.id,
                group_type=group_type,
                label=label,
                player_id=player_id,
            )
            return CommandResult(
                f"绑定成功：本群 → 《{show.name}》/{GROUP_TYPE_CN.get(binding.group_type, binding.group_type)}"
                + (f"（{binding.label}）" if binding.label else "")
            )

        if text == "群列表":
            denied = self._require_admin(ctx)
            if denied:
                return denied
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先在已绑定的恋综群里使用，或私聊“切换 <恋综代号>”。")
            groups = self.db.list_group_bindings(show.id)
            if not groups:
                return CommandResult("这个恋综还没绑定群。")
            lines = []
            for g in groups:
                label = f"｜{g.label}" if g.label else ""
                lines.append(f"{GROUP_TYPE_CN.get(g.group_type, g.group_type)}{label}")
            return CommandResult(f"《{show.name}》已绑定：\n" + "\n".join(lines))

        if text.startswith("登记我"):
            show, binding = self._resolve_show(ctx)
            if not show:
                return CommandResult("我还不知道你属于哪个恋综。先让骰主建恋综并绑定群，或私聊“切换 <代号>”。")

            key = text[len("登记我"):].strip()
            player = None
            if binding and binding.group_type == "personal" and binding.player_id:
                players = self.db.list_players(show.id, active_only=False)
                player = next((p for p in players if p.id == binding.player_id), None)
            elif key:
                player = self.db.get_player(show.id, key)

            if not player:
                return CommandResult("没定位到你的嘉宾档案。可以写：登记我 01")
            if player.user_openid and player.user_openid != ctx.user_openid and not is_admin:
                return CommandResult("这个嘉宾位已经登记给其他账号了，请找骰主处理。")
            self.db.bind_player_user(player.id, ctx.user_openid)
            self.db.set_active_show(ctx.user_openid, show.id)
            return CommandResult(f"登记完成：你现在对应《{show.name}》的 {player.slot}｜{player.name}。")

        if text == "嘉宾列表":
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先切换到一个恋综，或者在已绑定群里问我。")
            players = self.db.list_players(show.id)
            if not players:
                return CommandResult("这个恋综还没有嘉宾。")
            return CommandResult("\n".join(f"{p.slot}｜{p.name}" for p in players))

        if text.startswith("随机嘉宾"):
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先切换到一个恋综，或者在已绑定群里操作。")
            parts = text.split()
            try:
                count = int(parts[1]) if len(parts) > 1 else 1
            except ValueError:
                return CommandResult("人数要写数字，例如：随机嘉宾 2")
            players = self.db.list_players(show.id)
            if count < 1 or count > len(players):
                return CommandResult(f"人数需要在 1 到 {len(players)} 之间。")
            picked = random.sample(players, count)
            return CommandResult("小苹果抽到：\n" + "\n".join(f"{p.slot}｜{p.name}" for p in picked))

        if text.startswith("心动信 "):
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("我还不知道你现在在哪个恋综。先“切换 <恋综代号>”。")
            sender = self.db.player_for_user_in_show(ctx.user_openid, show.id)
            if not sender:
                return CommandResult("你还没有登记嘉宾身份。先发送“登记我 <序号>”。")
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return CommandResult("格式：心动信 <目标序号/姓名> <内容>")
            target = self.db.get_player(show.id, parts[1])
            if not target:
                return CommandResult("没找到收信人。")
            if target.id == sender.id:
                return CommandResult("不能给自己寄心动信。")
            letter = self.db.add_heart_letter(show.id, sender.id, target.id, parts[2], anonymous=True)

            proactive = []
            target_groups = [
                g for g in self.db.list_group_bindings(show.id)
                if g.group_type == "personal" and g.player_id == target.id
            ]
            if target_groups:
                content = f"🍎 小苹果投递了一封心动信：\n\n{letter.content}"
                proactive.append((target_groups[0].group_openid, content))
            return CommandResult(
                f"心动信 #{letter.id} 已收下。"
                + ("小苹果会尝试投递到对方个人群。" if proactive else "对方个人群还没绑定，信先保存在后台。"),
                proactive_group_messages=proactive or None,
            )

        if text.startswith("挂心愿 "):
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先切换到一个恋综。")
            player = self.db.player_for_user_in_show(ctx.user_openid, show.id)
            if not player:
                return CommandResult("你还没有登记嘉宾身份。")
            content = text[len("挂心愿 "):].strip()
            if not content:
                return CommandResult("心愿内容不能为空。")
            wish = self.db.add_wish(show.id, player.id, content)
            return CommandResult(f"心愿 #{wish.id} 已挂上。")

        if text == "心愿墙":
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先切换到一个恋综。")
            wishes = self.db.list_open_wishes(show.id)
            if not wishes:
                return CommandResult("现在心愿墙是空的。")
            # 默认不公开挂愿人，保留“摘挂心愿”的盲选感。
            return CommandResult("当前心愿墙：\n" + "\n".join(f"#{w.id}｜{w.content}" for w in wishes))

        if text.startswith("摘心愿 "):
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先切换到一个恋综。")
            player = self.db.player_for_user_in_show(ctx.user_openid, show.id)
            if not player:
                return CommandResult("你还没有登记嘉宾身份。")
            try:
                wish_id = int(text.split(maxsplit=1)[1])
                wish = self.db.pick_wish(wish_id, player.id)
            except (ValueError, TypeError) as e:
                return CommandResult(str(e) if str(e) else "心愿编号要写数字。")
            return CommandResult(f"已摘下心愿 #{wish.id}。")

        if text.startswith("小群成员 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            show, binding = self._resolve_show(ctx)
            if not show or not binding or binding.group_type != "small":
                return CommandResult("这条指令要在已经绑定为“小群”的群里使用。")
            keys = text[len("小群成员 "):].split()
            players = []
            for key in keys:
                p = self.db.get_player(show.id, key)
                if not p:
                    return CommandResult(f"没找到嘉宾：{key}")
                players.append(p)
            self.db.set_small_group_members(binding.id, [p.id for p in players])
            return CommandResult("小群成员已记录：\n" + "\n".join(f"{p.slot}｜{p.name}" for p in players))

        if text.startswith("NPC设置 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("先在已绑定群操作，或私聊切换到一个恋综。")
            raw = text[len("NPC设置 "):].strip()
            if "|" not in raw:
                return CommandResult("格式：NPC设置 <名字> | <完整人设与说话规则>")
            name, prompt = [x.strip() for x in raw.split("|", 1)]
            if not name or not prompt:
                return CommandResult("NPC 名字和人设都不能为空。")
            self.db.upsert_npc(show.id, name, prompt)
            return CommandResult(f"NPC「{name}」已保存。")

        if text.startswith("NPC进入 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            if not ctx.group_openid:
                return CommandResult("NPC模式要在群里开启。")
            show, _ = self._resolve_show(ctx)
            if not show:
                return CommandResult("本群还没绑定恋综。")
            name = text[len("NPC进入 "):].strip()
            npc = self.db.get_npc(show.id, name)
            if not npc:
                return CommandResult("没找到这个 NPC。先用“NPC设置”。")
            self.db.set_group_npc(ctx.group_openid, npc.id)
            return CommandResult(f"已进入 NPC「{npc.name}」模式。之后 @小苹果 的普通对话会由这个角色回应。")

        if text == "NPC退出":
            if not ctx.group_openid:
                return CommandResult("私聊里没有群 NPC 模式。")
            denied = self._require_admin(ctx)
            if denied:
                return denied
            self.db.set_group_npc(ctx.group_openid, None)
            return CommandResult("已退出 NPC 模式，小苹果回来啦。")

        if text.startswith("公告 "):
            denied = self._require_admin(ctx)
            if denied:
                return denied
            show, binding = self._resolve_show(ctx)
            if not show:
                return CommandResult("先在已绑定群操作，或私聊切换到一个恋综。")
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return CommandResult("格式：公告 <本群/主群/个人群/全部> <内容>")
            scope, content = parts[1], parts[2].strip()
            groups = self.db.list_group_bindings(show.id)
            selected = []
            if scope == "本群" and ctx.group_openid:
                selected = [g for g in groups if g.group_openid == ctx.group_openid]
            elif scope == "主群":
                selected = [g for g in groups if g.group_type == "main"]
            elif scope == "个人群":
                selected = [g for g in groups if g.group_type == "personal"]
            elif scope == "全部":
                selected = groups
            else:
                return CommandResult("公告范围支持：本群、主群、个人群、全部。")
            if not selected:
                return CommandResult("这个范围里没有已绑定的群。")
            msgs = [(g.group_openid, f"🍎 小苹果公告\n\n{content}") for g in selected]
            return CommandResult(f"准备向 {len(msgs)} 个群发送公告。", proactive_group_messages=msgs)

        if text.startswith("问 "):
            if not self.settings.enable_ai_chat:
                return CommandResult("小苹果的 AI 问答目前关闭。")
            user_text = text[len("问 "):].strip()
            show, binding = self._resolve_show(ctx)
            npc = self.db.get_group_npc(ctx.group_openid) if ctx.group_openid else None
            key = f"group:{ctx.group_openid}" if ctx.group_openid else f"user:{ctx.user_openid}"
            reply = await self.ai.reply(
                conversation_key=key,
                user_text=user_text,
                show=show,
                binding=binding,
                npc=npc,
            )
            return CommandResult(reply)

        # NPC 模式下，未命中规则指令的普通消息直接进入角色。
        if ctx.group_openid:
            npc = self.db.get_group_npc(ctx.group_openid)
            if npc and self.settings.enable_ai_chat:
                show, binding = self._resolve_show(ctx)
                reply = await self.ai.reply(
                    conversation_key=f"group:{ctx.group_openid}:npc:{npc.id}",
                    user_text=text,
                    show=show,
                    binding=binding,
                    npc=npc,
                )
                return CommandResult(reply)

        # 普通 @ 也可以让小苹果回答，但不会替程序执行确定性操作。
        if self.settings.enable_ai_chat:
            show, binding = self._resolve_show(ctx)
            key = f"group:{ctx.group_openid}" if ctx.group_openid else f"user:{ctx.user_openid}"
            reply = await self.ai.reply(
                conversation_key=key,
                user_text=text,
                show=show,
                binding=binding,
                npc=None,
            )
            return CommandResult(reply)

        return CommandResult("没认出这条指令。发送“帮助”看看小苹果现在会什么。")
