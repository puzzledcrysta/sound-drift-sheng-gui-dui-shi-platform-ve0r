from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from unicodedata import normalize
from app.errors import DataError


def number(raw, minimum=None, maximum=None):
    value = normalize('NFKC', raw).strip()
    if not re.fullmatch(r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?', value) or len(value)>28:
        raise DataError('NUMBER', f'数字格式无效 {raw[:80]}')
    try:
        parsed = Decimal(value.replace(',',''))
    except InvalidOperation as error:
        raise DataError('NUMBER',f'数字格式无效 {raw[:80]}') from error
    if (minimum is not None and parsed < minimum) or (maximum is not None and parsed > maximum):
        raise DataError('RANGE',f'数字越界 {raw[:80]}')
    return parsed


def whole(raw, minimum=None, maximum=None):
    parsed = number(raw,minimum,maximum)
    if parsed != parsed.to_integral_value():
        raise DataError('NUMBER',f'需要整数 {raw[:80]}')
    return int(parsed)


def instant(value):
    try:
        if 'T' not in value:
            raise ValueError('无时间')
        stamp = datetime.fromisoformat(value)
        if stamp.utcoffset() is None:
            raise ValueError('无偏移')
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise DataError('TIMESTAMP',f'需要带偏移的时间 {value[:80]}') from error


def parts(text):
    if text == '无':
        return []
    values = [value.strip() for value in text.split(';')]
    if not all(values) or len(values) > 240:
        raise DataError('BUSINESS','复合字段含空项或超出 240 项')
    return values
