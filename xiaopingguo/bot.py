\
from __future__ import annotations

import traceback

import botpy
from botpy import logging
from botpy.message import GroupMessage, C2CMessage

from .commands import CommandContext, CommandRouter

_log = logging.get_logger()


class AppleBot(botpy.Client):
    def __init__(self, *, router: CommandRouter, **kwargs):
        super().__init__(**kwargs)
        self.router = router

    async def on_ready(self):
        _log.info(f"小苹果上线：{self.robot.name}")

    async def _send_proactive_groups(self, messages: list[tuple[str, str]] | None):
        if not messages:
            return
        for group_openid, content in messages:
            try:
                # 不带 msg_id 属于主动消息，QQ 平台可能有频率/额度限制。
                await self.api.post_group_message(
                    group_openid=group_openid,
                    msg_type=0,
                    content=content,
                )
            except Exception as exc:
                _log.error(f"主动群消息发送失败 group={group_openid}: {exc}")

    async def on_group_at_message_create(self, message: GroupMessage):
        try:
            user_openid = getattr(message.author, "member_openid", None) or getattr(
                message.author, "user_openid", ""
            )
            ctx = CommandContext(
                user_openid=user_openid,
                group_openid=message.group_openid,
                text=message.content or "",
            )
            result = await self.router.handle(ctx)
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=result.text,
            )
            await self._send_proactive_groups(result.proactive_group_messages)
        except Exception:
            _log.error(traceback.format_exc())
            try:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=0,
                    msg_id=message.id,
                    content="小苹果刚才处理失败了，错误已经记进日志。",
                )
            except Exception:
                pass

    async def on_c2c_message_create(self, message: C2CMessage):
        try:
            user_openid = getattr(message.author, "user_openid", "")
            ctx = CommandContext(
                user_openid=user_openid,
                text=message.content or "",
            )
            result = await self.router.handle(ctx)
            await message._api.post_c2c_message(
                openid=user_openid,
                msg_type=0,
                msg_id=message.id,
                content=result.text,
            )
            await self._send_proactive_groups(result.proactive_group_messages)
        except Exception:
            _log.error(traceback.format_exc())
            try:
                await message._api.post_c2c_message(
                    openid=getattr(message.author, "user_openid", ""),
                    msg_type=0,
                    msg_id=message.id,
                    content="小苹果刚才处理失败了，错误已经记进日志。",
                )
            except Exception:
                pass
