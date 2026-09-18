\
from __future__ import annotations

from openai import AsyncOpenAI

from .config import Settings
from .db import Database, NPCProfile, Show, GroupBinding


APPLE_SYSTEM_PROMPT = """你是“小苹果”，《离开伊甸以后》系列演绎恋综的群助手。
你的定位是清楚、可靠、轻松，不抢戏，不替骰主擅自修改规则或宣布结果。
遇到需要程序判定、随机、心动信、投票、配对、数值等确定性操作时，提醒用户使用小苹果的对应指令；
不要自行伪造抽签、投票、数据库结果。
回答群内问题时尽量简洁。"""


class AIService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.client = (
            AsyncOpenAI(api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com")
            if settings.deepseek_api_key
            else None
        )

    async def reply(
        self,
        *,
        conversation_key: str,
        user_text: str,
        show: Show | None = None,
        binding: GroupBinding | None = None,
        npc: NPCProfile | None = None,
    ) -> str:
        if not self.client:
            return "小苹果还没有配置 DeepSeek API Key，所以现在只能使用规则功能。"

        context = []
        if show:
            context.append(f"当前恋综：{show.name}（{show.code}）")
        if binding:
            context.append(f"当前群类型：{binding.group_type}；群标签：{binding.label or '未命名'}")

        if npc:
            system = (
                f"你正在扮演恋综中的 NPC「{npc.name}」。\n"
                f"以下是骰主设置的人设与约束：\n{npc.prompt}\n\n"
                "必须保持角色内表达；不知道的信息不要自行补成既定事实。"
            )
        else:
            system = APPLE_SYSTEM_PROMPT

        if context:
            system += "\n\n" + "\n".join(context)

        history = self.db.get_history(conversation_key, self.settings.ai_history_limit)
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": row.role, "content": row.content} for row in history)
        messages.append({"role": "user", "content": user_text})

        response = await self.client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=messages,
            stream=False,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            content = "小苹果刚才没组织好语言，再问一次吧。"

        self.db.add_history(conversation_key, "user", user_text)
        self.db.add_history(conversation_key, "assistant", content)
        return content
