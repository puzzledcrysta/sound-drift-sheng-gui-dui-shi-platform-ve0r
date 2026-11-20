"""复核沿用判定。

剪辑已确认过的校时稿，在补录锚点挪动时码后，逐片段判定能否沿用原确认：
- 校准起止时码与已采信指纹一致才能沿用，时长相同但时码已变必须重审；
- 晚到的旧修订号不能冲掉已采信的补正；
- 同一补正重试（指纹相同）幂等沿用，不重复挂起复核；
- 原稿行号、原始字段与批次指纹随结论保留，可追溯。
"""
import json
from hashlib import sha256
from app.store import connection
from app.errors import DataError
from app.modules.runs.repository import lookup
from app.pipeline import stages

CARRY = 'CARRY_OVER'
REVIEW_TIMECODE = 'REVIEW_TIMECODE'
REVIEW_STALE_REVISION = 'REVIEW_STALE_REVISION'
REVIEW_QUARANTINED = 'REVIEW_QUARANTINED'
REVIEW_NEW_KEY = 'REVIEW_NEW_KEY'

VERDICTS = (CARRY, REVIEW_TIMECODE, REVIEW_STALE_REVISION, REVIEW_QUARANTINED, REVIEW_NEW_KEY)


def fingerprint(row):
    """片段时码指纹：起止校准毫秒、修订号与原始来源字段，任一挪动即变化。"""
    payload = '|'.join((row['key'], str(row['revision']),
                        row['start_ms'], row['end_ms'], *row['raw']))
    return sha256(payload.encode()).hexdigest()


def _confirmed_run_ids(db):
    return {row['run_id'] for row in db.execute(
        "SELECT DISTINCT run_id FROM reviews WHERE decision='确认'").fetchall()}


def resolve_baseline(db, baseline_id):
    """确认基准批次：显式指定须存在且有确认结论；否则取最近一条确认所在批次。"""
    if baseline_id is not None:
        lookup(db, baseline_id)
        if baseline_id not in _confirmed_run_ids(db):
            raise DataError('BASELINE_UNCONFIRMED', '指定批次尚无确认结论，不能作为沿用基准', 422)
        return baseline_id
    row = db.execute(
        "SELECT run_id FROM reviews WHERE decision='确认' "
        'ORDER BY version DESC, changed DESC LIMIT 1').fetchone()
    if row is None:
        raise DataError('BASELINE_NONE', '还没有任何确认批次，先完成一次校时复核', 422)
    return row['run_id']


def _index(rows):
    return {row['key']: row for row in rows}


def _quarantine_index(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['key'], []).append(row)
    return grouped


def _verdict(row, code, detail):
    return {'key': row['key'], 'line': row['line'], 'revision': row['revision'],
            'start_ms': row.get('start_ms'), 'end_ms': row.get('end_ms'),
            'amount': row.get('amount'), 'code': code, 'detail': detail,
            'fingerprint': fingerprint(row) if 'start_ms' in row else None}


def assess(candidate, baseline_id):
    """对候选批次与已确认基准逐片段出判定。"""
    with connection() as db:
        stored = json.loads(lookup(db, baseline_id)['result'])
    base = _index(stored['accepted'])
    current = _index(candidate['accepted'])
    quarantined = _quarantine_index(candidate['rejected'])
    verdicts = []
    for key in sorted(base.keys() | current.keys()):
        old, new, bad_rows = base.get(key), current.get(key), quarantined.get(key, [])
        # 仅当确认过的片段在候选批次完全没有可采信行时才判隔离；
        # 同键另有坏行但仍有采信行的，以采信行为准走时码判定。
        if bad_rows and new is None and old is not None:
            reasons = '；'.join(f"{bad['code']}：{bad['detail']}" for bad in bad_rows)
            first = bad_rows[0]
            verdicts.append(_verdict(
                {'key': key, 'line': first['line'], 'revision': first.get('revision'),
                 'raw': first['raw']},
                REVIEW_QUARANTINED,
                f'候选批次隔离（{reasons}），原确认不能沿用'))
            continue
        if old is None:
            verdicts.append(_verdict(new, REVIEW_NEW_KEY, '确认基准没有此片段，按新片段复核'))
            continue
        if new is None:
            verdicts.append(_verdict(old, REVIEW_QUARANTINED,
                                     '候选批次未采信此片段（隔离或被版本替换），原确认不能沿用'))
            continue
        if new['revision'] < old['revision']:
            verdicts.append(_verdict(new, REVIEW_STALE_REVISION,
                                     f"晚到修订 {new['revision']} 低于已采信修订 {old['revision']}，补正仍有效"))
            continue
        if fingerprint(new) == fingerprint(old):
            verdicts.append(_verdict(new, CARRY,
                                     f'时码指纹一致，沿用批次 {baseline_id[:9]} 的确认'))
        elif (new['start_ms'], new['end_ms']) != (old['start_ms'], old['end_ms']):
            verdicts.append(_verdict(new, REVIEW_TIMECODE,
                                     f"校准起止时码 {old['start_ms']}–{old['end_ms']} → "
                                     f"{new['start_ms']}–{new['end_ms']}，须重新复核"))
        else:
            verdicts.append(_verdict(new, REVIEW_TIMECODE, '片段来源内容已变化，须重新复核'))
    return verdicts


def judge(source, baseline_id=None):
    """跑候选来源并与已确认基准对账，返回逐片段沿用判定与汇总。"""
    candidate = stages(source)
    suppressed = candidate['quality']['suppressed']
    with connection() as db:
        base_id = resolve_baseline(db, baseline_id)
    verdicts = assess(candidate, base_id)
    summary = {code: sum(item['code'] == code for item in verdicts) for code in VERDICTS}
    return {'baseline_run_id': base_id,
            'candidate': {'accepted': len(candidate['accepted']),
                          'quarantine': len(candidate['rejected']),
                          'suppressed': len(suppressed)},
            'summary': summary, 'verdicts': verdicts}
