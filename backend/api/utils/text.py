import unicodedata
from typing import Optional
from api.utils.logging import log_warning

def fix_unicode(text: str) -> str:
    if not text:
        return text
    
    try:
        if '\\u' in text:
            text = text.encode('raw_unicode_escape').decode('unicode_escape')
    except:
        pass
    
    try:
        text = unicodedata.normalize('NFC', text)
    except:
        pass
    
    return text

def romanize_japanese(text: str) -> Optional[str]:
    if not text:
        return None
    
    has_japanese = any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in text)
    
    if not has_japanese:
        return None
    
    try:
        import pykakasi
        kakasi = pykakasi.kakasi()
        result = kakasi.convert(text)
        romanized = ' '.join([item['hepburn'] for item in result])
        return romanized
    except ImportError:
        return None
    except Exception as e:
        log_warning(f"Romanization failed: {e}")
        return None
