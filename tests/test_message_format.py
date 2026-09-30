import asyncio
import sys
from pathlib import Path
from html.parser import HTMLParser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from message_format import html_messages,reply_html,MAX_MESSAGE

def test_split_only_complete_blocks_no_broken_html():
    blocks=['<b>Header</b>']+[f'<b>{"title"*100}</b> <a href="https://hacoo.app/detail/{i}">Abrir</a>' for i in range(10)]
    result=html_messages(blocks)
    assert len(result)>1 and all(len(x)<=MAX_MESSAGE for x in result)
    assert all(x.count('<a ')==x.count('</a>') and x.count('<b>')==x.count('</b>') for x in result)
    assert sum(x.count('Abrir') for x in result)==10

def test_huge_href_or_html_is_omitted_not_truncated():
    text=html_messages(['<a href="https://hacoo.app/?sig='+'x'*10000+'">Abrir</a>'])
    assert len(text)==1 and 'omitido' in text[0]
    assert '<a' not in text[0]

def test_async_reply_args_and_no_empty_message():
    class Message:
        def __init__(self):self.calls=[]
        async def reply_text(self,t,**kw):self.calls.append((t,kw))
    m=Message();asyncio.run(reply_html(m,[]));assert not m.calls
    asyncio.run(reply_html(m,['<b>A</b>','B']))
    assert m.calls[0][1]=={'parse_mode':'HTML','disable_web_page_preview':True}

def test_non_bmp_unicode_cannot_exceed_telegram_utf16_units():
    from message_format import telegram_units
    blocks=['<b>'+'😀'*950+'</b>' for _ in range(3)]
    messages=html_messages(blocks)
    assert len(messages)==3 # two blocks look short in Python but >3800 UTF16
    assert all(telegram_units(t)<=MAX_MESSAGE for t in messages)
    assert sum(t.count('😀') for t in messages)==2850
    assert telegram_units('a😀')==3

def test_giant_emoji_block_omitted_intact():
    from message_format import telegram_units
    messages=html_messages(['<b>'+'😀'*2000+'</b>'])
    assert 'omitido' in messages[0] and '<b>' not in messages[0]
    assert telegram_units(messages[0])<=MAX_MESSAGE
