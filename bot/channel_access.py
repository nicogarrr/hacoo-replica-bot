"""Membership-gated private search for subscribers of Nico's channel.

No subscriber-facing feature is enabled until the numeric channel ID is verified
and PUBLIC_SEARCH_ENABLED=1 is explicitly set at deployment.
"""
import time
from telegram.constants import ChatMemberStatus


class SubscriberGate:
    def __init__(self, channel_id: int, enabled: bool, cooldown_seconds: int = 5):
        self.channel_id = channel_id
        self.enabled = enabled
        self.cooldown_seconds = cooldown_seconds
        self._last = {}

    async def allowed(self, bot, user_id: int) -> bool:
        if not self.enabled or not self.channel_id:
            return False
        try:
            member = await bot.get_chat_member(self.channel_id, user_id)
        except Exception:
            # Telegram errors (including missing admin rights) fail closed.
            return False
        return member.status in (
            ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
        ) or (member.status == ChatMemberStatus.RESTRICTED and member.is_member)

    def throttle(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._last.get(user_id)
        if last is not None and now - last < self.cooldown_seconds:
            return True
        self._last[user_id] = now
        # bounded memory even if the public bot gets widely shared
        if len(self._last) > 10000:
            self._last = {uid: ts for uid, ts in self._last.items()
                          if now - ts < self.cooldown_seconds}
        return False
