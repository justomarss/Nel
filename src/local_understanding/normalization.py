import re
import unicodedata


def normalize_text(text):
    value = unicodedata.normalize("NFKC", text).casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def remove_azerbaijani_diacritics(text):
    return text.translate(str.maketrans("əçğıöşüƏÇĞİÖŞÜ", "ecgiosuECGIOSU"))
