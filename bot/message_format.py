"""Bounded Telegram HTML, split only between complete generated blocks."""
import html

MAX_MESSAGE = 3800

def html_messages(blocks):
    messages=[]
    current=''
    for block in blocks:
        if len(block)>MAX_MESSAGE:
            # Never truncate inside a tag or href; fail without invalid HTML.
            block='Un resultado era demasiado largo para mostrarlo con seguridad. Se ha omitido su enlace.'
        proposed=current+'\n\n'+block if current else block
        if len(proposed)>MAX_MESSAGE:
            messages.append(current);current=block
        else:current=proposed
    if current:messages.append(current)
    return messages

async def reply_html(message,blocks):
    for text in html_messages(blocks):
        await message.reply_text(text,parse_mode='HTML',disable_web_page_preview=True)
