import csv
import io
import pytest
from app.settings import FIELDS
from app.modules.carryover.service import (
    judge, assess, fingerprint, CARRY, REVIEW_TIMECODE, REVIEW_STALE_REVISION,
    REVIEW_QUARANTINED, REVIEW_NEW_KEY)


def _csv(rows, header=None):
    if header is None:
        header = ['声轨片段', '修订号', '提交时间', *FIELDS, '原始备注']
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows([header, *rows])
    return stream.getvalue().encode()


def _row(key, revision='1', start='3000', end='9000',
         anchors='8000:1998;0:0;4000:1000;12000:2996', note='原稿'):
    return [key, revision, '2026-11-18T09:30:00+08:00', '4000', '2000',
            anchors, start, end, note]


def _shifted_clock_rows():
    """锚点整体平移 100ms：段宽不变（时长一致），但起止时码全部挪动。"""
    return _row('00101', anchors='8000:2098;0:100;4000:1100;12000:3096')


def _confirm(client, run_id, note='逐笔核对'):
    resp = client.post(f'/api/review/{run_id}',
                       json={'version': 0, 'decision': '确认', 'note': note})
    assert resp.status_code == 200, resp.text


@pytest.fixture
def baseline_run(client):
    """建立一个已确认的基准批次。"""
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    _confirm(client, run_id)
    return run_id


def _by_key(report):
    return {item['key']: item for item in report['verdicts']}


# ---------- 规则一：时码指纹一致才能沿用，同补正重试幂等 ----------

def test_identical_reread_carries_confirmation(client, baseline_run):
    report = client.post('/api/carryover', json={}).json()
    item = _by_key(report)['00101']
    assert item['code'] == CARRY
    assert report['summary'][CARRY] >= 1
    # 同一补正重试：再判一次结论不变，不会重复挂起复核
    again = client.post('/api/carryover', json={}).json()
    assert again['verdicts'] == report['verdicts']


def test_carried_fragment_keeps_original_traceability(client, baseline_run):
    report = client.post('/api/carryover', json={}).json()
    item = _by_key(report)['00101']
    assert item['fingerprint'] and item['line'] == 2
    assert report['baseline_run_id'] == baseline_run


# ---------- 规则二：时长相同但起止时码变了，必须重审 ----------

def test_same_duration_shifted_timecode_requires_review(client, baseline_run):
    payload = _csv([_shifted_clock_rows()])
    report = client.post('/api/carryover', json={'data': payload.decode()}).json()
    item = _by_key(report)['00101']
    assert item['code'] == REVIEW_TIMECODE
    assert '时码' in item['detail']
    # 两版时长完全一致，证明判定依据是时码而非时长
    from app.pipeline import stages
    amounts = {row['key']: row['amount'] for row in stages(payload)['accepted']}
    base_amounts = {row['key']: row['amount']
                    for row in client.get(f'/api/runs/{baseline_run}').json()['accepted']
                    if row['key'] == '00101'}
    assert amounts['00101'] == base_amounts['00101']


def test_moved_sample_bounds_requires_review(client, baseline_run):
    payload = _csv([_row('00101', start='3100', end='9100')])
    report = client.post('/api/carryover', json={'data': payload.decode()}).json()
    assert _by_key(report)['00101']['code'] == REVIEW_TIMECODE


# ---------- 规则三：晚到的旧修订不能冲掉已采信补正 ----------

def test_late_old_revision_cannot_overwrite_accepted_fix(client, baseline_run):
    # 基准已采信 00102 修订 2（补正）；候选只回传修订 1 的旧稿
    old_fix = _row('00102', revision='1',
                   anchors='8000:1998;0:0;4000:1000;12000:2996')
    report = client.post('/api/carryover',
                         json={'data': _csv([old_fix]).decode()}).json()
    item = _by_key(report)['00102']
    assert item['code'] == REVIEW_STALE_REVISION
    assert '低于已采信修订 2' in item['detail']


# ---------- 规则四：候选批次隔离的片段要重审，原稿仍可追查 ----------

def test_quarantined_fragment_flagged_with_evidence(client, baseline_run):
    # 00103 在基准里已确认；候选锚点不再覆盖片段区间，触发 SOUND_COVERAGE
    broken = _row('00103', start='24000', end='72000',
                  anchors='0:10;1000:210')
    report = client.post('/api/carryover',
                         json={'data': _csv([broken]).decode()}).json()
    item = _by_key(report)['00103']
    assert item['code'] == REVIEW_QUARANTINED
    assert 'SOUND_COVERAGE' in item['detail'] and item['line'] == 2


# ---------- 规则五：新片段须复核 ----------

def test_new_fragment_requires_review(client, baseline_run):
    payload = _csv([_row('00777')])
    item = _by_key(client.post('/api/carryover',
                               json={'data': payload.decode()}).json())['00777']
    assert item['code'] == REVIEW_NEW_KEY


def test_unverified_latest_revision_blocks_carryover(client, baseline_run):
    # 同键一条完整行 + 一条最高修订未采信坏行：按 REV_BLOCKED 规则整键隔离，不能沿用
    good = _row('00101')
    bad = _row('00101')
    bad[7] = 'N/A'  # 末样本缺失 → REQUIRED，使最高修订没有可采信行
    report = client.post('/api/carryover',
                         json={'data': _csv([good, bad]).decode()}).json()
    item = _by_key(report)['00101']
    assert item['code'] == REVIEW_QUARANTINED
    assert 'REV_BLOCKED' in item['detail']


# ---------- 基准批次管理 ----------

def test_no_confirmed_baseline_rejected(client):
    resp = client.post('/api/carryover', json={})
    assert (resp.status_code, resp.json()['code']) == (422, 'BASELINE_NONE')


def test_explicit_unconfirmed_baseline_rejected(client):
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    resp = client.post(f'/api/carryover?baseline={run_id}', json={})
    assert (resp.status_code, resp.json()['code']) == (422, 'BASELINE_UNCONFIRMED')


def test_unknown_baseline_is_404(client, baseline_run):
    resp = client.post('/api/carryover?baseline=not-a-run', json={})
    assert (resp.status_code, resp.json()['code']) == (404, 'RUN_UNKNOWN')


def test_explicit_confirmed_baseline_used(client, baseline_run):
    report = client.post(f'/api/carryover?baseline={baseline_run}', json={}).json()
    assert report['baseline_run_id'] == baseline_run


def test_latest_confirmed_run_is_default_baseline(client, baseline_run):
    # 用一份与样例不同的来源建立第二个内容寻址批次，并确认它
    second_payload = _csv([_row('00777')])
    second = client.post('/api/runs', json={'data': second_payload.decode()}
                         ).json()['manifest']['run_id']
    assert second != baseline_run
    resp = client.post(f'/api/review/{second}',
                       json={'version': 0, 'decision': '确认', 'note': '二次确认'})
    assert resp.status_code == 200
    assert client.post('/api/carryover', json={}).json()['baseline_run_id'] == second
    # 一条只退回、未确认的批次不会被选作基准
    client.post(f'/api/review/{second}',
                json={'version': 1, 'decision': '退回', 'note': '退回不影响基准'})
    assert client.post('/api/carryover', json={}).json()['baseline_run_id'] == second


# ---------- 指纹与单元行为 ----------

def test_fragment_fingerprint_changes_with_timecode_only():
    from app.pipeline import stages
    first = stages(_csv([_row('00101')]))['accepted'][0]
    moved = stages(_csv([_shifted_clock_rows()]))['accepted'][0]
    assert first['amount'] == moved['amount']
    assert fingerprint(first) != fingerprint(moved)


def test_fingerprint_stable_under_identical_reread():
    from app.pipeline import stages
    payload = _csv([_row('00101')])
    assert fingerprint(stages(payload)['accepted'][0]) == \
           fingerprint(stages(payload)['accepted'][0])


def test_summary_covers_every_verdict(client, baseline_run):
    report = client.post('/api/carryover', json={}).json()
    assert sum(report['summary'].values()) == len(report['verdicts'])
    assert set(report['summary']) == {CARRY, REVIEW_TIMECODE,
                                      REVIEW_STALE_REVISION,
                                      REVIEW_QUARANTINED, REVIEW_NEW_KEY}
