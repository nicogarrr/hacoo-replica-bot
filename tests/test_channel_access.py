import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / "bot"))
from channel_access import SubscriberGate
from product_links import ProductLinks


def test_membership_gate_fails_closed_and_excludes_nonmember():
    class Bot:
        async def get_chat_member(self, chat_id, user_id):
            assert chat_id == -100123
            return SimpleNamespace(status="member" if user_id == 10 else "left")

    bot = Bot()
    assert not asyncio.run(SubscriberGate(-100123, False).allowed(bot, 10))
    assert not asyncio.run(SubscriberGate(0, True).allowed(bot, 10))
    gate = SubscriberGate(-100123, True)
    assert asyncio.run(gate.allowed(bot, 10))
    assert not asyncio.run(gate.allowed(bot, 11))
    assert not gate.throttle(10)
    assert gate.throttle(10)


def test_affiliate_mapping_opt_in_and_verified_ids(tmp_path):
    row = {"product_id": "123", "link": "https://hacoo.app/detail/123"}
    assert ProductLinks().for_result(row) == row["link"]
    mapping = tmp_path / "links.json"
    mapping.write_text('{"123":"https://hacoo.app/example-affiliate","bad":"http://x"}')
    assert ProductLinks(str(mapping)).for_result(row) == row["link"]
    mapping.write_text('{"123":"https://hacoo.app/example-affiliate"}')
    assert ProductLinks(str(mapping)).for_result(row) == "https://hacoo.app/example-affiliate"
