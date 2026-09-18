from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .db import Database, ShowRecord
from .parser import parse_local_show


APPLE_SYSTEM_PROMPT = """你是“小苹果”，一个长期待在演绎恋综主群里的档案馆兼选本搭子。

你最重要的特点不是客服式“答题”，而是：看过历届恋综和身份牌，能听懂玩家到底想玩什么，再从真实档案里帮他们筛选、比较和推荐。

说话要求：
- 用自然的中文聊天，别像工单客服，别动不动说“根据资料库”。
- 一般控制在几段内，除非对方明确要详细分析。
- 可以有判断和口味，但要把“档案里的事实”和“你的理解/推荐理由”分开。
- 用户说“我想玩XX”“我在两个恋综之间纠结”时，如果偏好还不够明确，可以先反问1到2个真正有区分度的问题，例如关系状态、虐度、事业线浓度、是否接受婚姻/前任/强设定等；信息够了就直接推荐，不要无休止反问。
- 推荐只能来自下面的真实档案。绝对不能编造不存在的恋综、编号、身份牌、剧情或规则。
- 如果档案没有合适的，直接说没有完全匹配，再给最接近的选择。
- 对某个身份牌的解读可以深入，但不要把你的推断伪装成骰主写死的设定。
- 允许承接最近聊天上下文，比如对方上一条刚说过“不想太虐”，下一条不用再问。

下面是当前可用的恋综档案索引：
{archive_context}
"""



CURRENT_CAPABILITIES = """当前程序能力边界：
- 小苹果只绑定一个QQ主群，不支持后台群、个人群、小群等多群管理。
- 骰主可以在主群录入/覆盖历届恋综档案；原文和结构化信息都会保存。
- 普通聊天重点是基于真实档案做自然检索、比较、选本和身份牌推荐，可以反问偏好。
- 固定FAQ、一表格式、一表收集等计划交给QQ群管家，小苹果当前不负责。
- 不要声称自己拥有以上范围之外的命令或QQ群管理能力。
"""

EXTRACT_PROMPT = """你是恋综档案整理器。请把用户给出的完整恋综原文整理成严格 JSON，只提取原文明确支持的信息，不要补写不存在的设定。

返回对象字段：
{
  "series": "系列名，没有就空字符串",
  "title": "本期标题，没有就空字符串",
  "full_name": "完整名称",
  "tags": ["TAG1", "TAG2"],
  "summary": "用2-4句话概括这辆恋综的核心题材和关系气质，不添加原文之外的事实",
  "deadlines": {
    "first_form": "一表时间，没有则空字符串",
    "second_form": "二表/公知时间，没有则空字符串",
    "official_schedule": "正式日程，没有则空字符串"
  },
  "days": [
    {"day": "D0", "theme": "当天主题句", "activities": ["活动"], "heart_letter_rule": "心动信规则"}
  ],
  "identity_cards": [
    {
      "number": "01",
      "header": "身份牌标题行（不含编号）",
      "male_role": "男方身份，没有则空",
      "female_role": "女方身份，没有则空",
      "relationship": "关系状态",
      "quote": "引用句",
      "themes": ["用于检索的客观关键词，最多6个"],
      "summary": "2-4句概括矛盾核心，只依据原文"
    }
  ]
}

只输出 JSON，不要 Markdown，不要解释。编号以用户指定的 {code} 为准。
"""


class AIService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.client = (
            AsyncOpenAI(api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com")
            if settings.deepseek_api_key
            else None
        )

    @staticmethod
    def _parse_json_text(text: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("AI 返回的不是 JSON 对象")
        return data

    async def parse_show(self, *, code: str, raw_text: str) -> dict[str, Any]:
        local = parse_local_show(code, raw_text)
        if not self.client:
            local["summary"] = ""
            return local

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {"role": "system", "content": EXTRACT_PROMPT.format(code=code)},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0.1,
                stream=False,
            )
            ai_data = self._parse_json_text(response.choices[0].message.content or "")
        except Exception:
            local["summary"] = ""
            return local

        # 对标题/TAG/日程等允许 AI 补充结构；对身份牌原文必须用本地切片覆盖。
        merged = dict(local)
        for key in ("series", "title", "full_name", "tags", "summary", "deadlines", "days"):
            value = ai_data.get(key)
            if value not in (None, "", [], {}):
                merged[key] = value

        local_cards = {str(c.get("number")): c for c in local.get("identity_cards", [])}
        ai_cards = ai_data.get("identity_cards") if isinstance(ai_data.get("identity_cards"), list) else []
        cards: list[dict[str, Any]] = []
        seen: set[str] = set()
        for card in ai_cards:
            if not isinstance(card, dict):
                continue
            number = str(card.get("number") or "").zfill(2)
            if not number:
                continue
            base = dict(local_cards.get(number, {}))
            base.update({k: v for k, v in card.items() if k != "raw" and v not in (None, "")})
            if number in local_cards:
                base["raw"] = local_cards[number].get("raw", "")
                base.setdefault("header", local_cards[number].get("header", ""))
            base["number"] = number
            cards.append(base)
            seen.add(number)

        for number, card in local_cards.items():
            if number not in seen:
                cards.append(card)
        cards.sort(key=lambda x: str(x.get("number", "")))
        merged["identity_cards"] = cards
        merged["code"] = code.strip().upper()
        return merged

    def _specific_show_context(self, user_text: str) -> str:
        codes = []
        for m in re.finditer(r"(?i)(?:[A-Z][A-Z0-9_-]*-)?P\d+", user_text or ""):
            code = m.group(0).upper()
            if code not in codes:
                codes.append(code)
        blocks = []
        for code in codes[:3]:
            show = self.db.get_show_by_code(code)
            if show:
                blocks.append(f"【{show.code}完整原文】\n{show.raw_text}")
        return "\n\n".join(blocks)

    async def reply(
        self,
        *,
        conversation_key: str,
        user_text: str,
        admin_private: bool = False,
    ) -> str:
        if not self.client:
            return "我现在还没接上 DeepSeek，只能先收档案，暂时没法陪你聊推荐。"

        archive_context = self.db.archive_context(max_chars=80000)
        system = APPLE_SYSTEM_PROMPT.format(archive_context=archive_context)
        system += "\n\n" + CURRENT_CAPABILITIES
        if admin_private:
            system += (
                "\n当前这条消息来自已经认主的骰主私聊。可以正常聊天和回答程序能力问题，"
                "不要再要求对方认主，也不要机械地把每句话赶回主群。"
            )
        specific = self._specific_show_context(user_text)
        if specific:
            system += "\n\n用户这次点名了具体档案，下面附上原文；回答具体事实时以原文为准：\n" + specific

        history = self.db.get_history(conversation_key, self.settings.ai_history_limit)
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": row.role, "content": row.content} for row in history)
        messages.append({"role": "user", "content": user_text})

        response = await self.client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=messages,
            temperature=0.85,
            stream=False,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            content = "我刚才卡了一下。你换个说法再问我一次。"

        self.db.add_history(conversation_key, "user", user_text)
        self.db.add_history(conversation_key, "assistant", content)
        return content
