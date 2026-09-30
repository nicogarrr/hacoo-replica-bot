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
