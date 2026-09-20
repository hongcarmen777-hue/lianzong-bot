from __future__ import annotations

import traceback

import botpy
from botpy import logging
from botpy.message import C2CMessage, GroupMessage

from .commands import CommandContext, CommandRouter

_log = logging.get_logger()


class AppleBot(botpy.Client):
    def __init__(self, *, router: CommandRouter, **kwargs):
        super().__init__(**kwargs)
        self.router = router

    async def on_ready(self):
        _log.info(f"小苹果 v0.2.7 上线：{self.robot.name}")

    async def on_group_at_message_create(self, message: GroupMessage):
        try:
            user_openid = getattr(message.author, "member_openid", None) or getattr(
                message.author, "user_openid", ""
            )
            result = await self.router.handle(
                CommandContext(
                    user_openid=user_openid,
                    group_openid=message.group_openid,
                    raw_text=message.content or "",
                )
            )
            if not result.text:
                return
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=result.text,
            )
        except Exception:
            _log.error(traceback.format_exc())
            try:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=0,
                    msg_id=message.id,
                    content="我刚才卡了一下，日志里已经留下错误了。",
                )
            except Exception:
                pass

    async def on_c2c_message_create(self, message: C2CMessage):
        try:
            user_openid = getattr(message.author, "user_openid", "")
            result = await self.router.handle(
                CommandContext(
                    user_openid=user_openid,
                    raw_text=message.content or "",
                )
            )
            if not result.text:
                return
            await message._api.post_c2c_message(
                openid=user_openid,
                msg_type=0,
                msg_id=message.id,
                content=result.text,
            )
        except Exception as exc:
            _log.error(traceback.format_exc())
            try:
                await message._api.post_c2c_message(
                    openid=getattr(message.author, "user_openid", ""),
                    msg_type=0,
                    msg_id=message.id,
                    content=f"这次没有成功落库。数据库报错：{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
