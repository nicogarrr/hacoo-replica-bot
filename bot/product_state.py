"""Strict observed SSR product presence, not global deletion or stock."""
import json
import re
from bs4 import BeautifulSoup

def classify_product_html(html, expected_id):
    """Return present/unavailable/unknown and precise reason.

    Unavailability is scoped to the fetched website/region, never global deletion.
    Errors and inconsistent IDs fail unknown. Generic metadata is not evidence.
    """
    if not isinstance(html,str) or len(html) > 2_000_000:
        return 'unknown','respuesta no interpretable'
    soup=BeautifulSoup(html,'html.parser')
    script=soup.select_one('script#__F_STATE__')
    try:
        scripts=soup.select('script#__F_STATE__')
        if len(scripts) != 1:
            return 'unknown','estado de producto ausente o ambiguo'
        state=json.loads(script.string or script.get_text()) if script else {}
        detail=state.get('detail',{})
        if not isinstance(detail,dict) or str(detail.get('itemId')) != str(expected_id):
            return 'unknown','estado sin ID de producto coincidente'
        if detail.get('errorCode'):
            return 'unknown','la web declaró un error, no prueba de borrado'
        item=detail.get('itemDetail')
        if isinstance(item,dict) and str(item.get('id'))==str(expected_id):
            if (type(item.get('status')) is int and item.get('status')==1
                    and detail.get('isAbnormalItem') is not True
                    and isinstance(item.get('title'),str) and item['title'].strip()):
                return 'present','ficha de producto presente en web ES; stock no verificado'
            return 'unknown','estado de venta no confirmado'
        text=soup.get_text(' ',strip=True).lower()
        explicit = any(marker in text for marker in (
            'este producto no está disponible','this product is not available'))
        if item is None and detail.get('isAbnormalItem') is True and explicit:
            return 'unavailable','la web muestra producto no disponible en esta región'
        return 'unknown','sin datos suficientes de producto'
    except (ValueError,TypeError,AttributeError):
        return 'unknown','estado de producto no interpretable'
