from decimal import Decimal as D
from app.errors import DataError
from .values import number, whole, parts

QUANTUM = D('0.001')


def anchor_points(row):
    """解析并校验锚点，返回 (锚点序列, 采样率, 始样本, 末样本)。"""
    rate = whole(row['采样率赫兹'], 1, 384000)
    max_ppm = number(row['允许漂移ppm'], 0, 100000)
    start = whole(row['片段始样本'], 0, 10**16)
    end = whole(row['片段末样本'], start+1, 10**16)
    anchors = {}
    for item in parts(row['锚点']):
        count, sep, milliseconds = item.partition(':')
        if not sep:
            raise DataError('SOUND_ANCHOR', '锚点须包含样本编号与参考毫秒')
        count, milliseconds = whole(count, 0, 10**16), number(milliseconds, 0, 10**16)
        if count in anchors and anchors[count] != milliseconds:
            raise DataError('SOUND_ANCHOR', f'样本 {count} 有不同参考时间')
        anchors[count] = milliseconds
    points = sorted(anchors.items())
    if len(points) < 2 or not points[0][0] <= start < end <= points[-1][0]:
        raise DataError('SOUND_COVERAGE', '片段超出锚点覆盖区间')
    for (a, t1), (b, t2) in zip(points, points[1:]):
        if t2 <= t1:
            raise DataError('SOUND_REWIND', f'锚点 {a}→{b} 出现时钟回退')
        ppm = ((t2-t1)*rate / ((b-a)*1000)-1)*10**6
        if abs(ppm) > max_ppm:
            raise DataError('SOUND_PPM', f'锚点 {a}→{b} 漂移超限')
    return points, rate, start, end


def calibrate(points, sample):
    """按包住样本位置的锚点线性求值，返回参考毫秒。"""
    for (a, t1), (b, t2) in zip(points, points[1:]):
        if a <= sample <= b:
            return (t1 + (t2-t1)*(sample-a)/(b-a)).quantize(QUANTUM)
    raise DataError('SOUND_COVERAGE', f'样本 {sample} 超出锚点覆盖区间')


def evaluate(row):
    points, rate, start, end = anchor_points(row)
    duration, proof = D(0), []
    for (a, t1), (b, t2) in zip(points, points[1:]):
        ppm = ((t2-t1)*rate / ((b-a)*1000)-1)*10**6
        left, right = max(a, start), min(b, end)
        if left < right:
            slope = (t2-t1)/(b-a)
            duration += slope*(right-left)
            proof.append((f'{left}–{right} 样本', f'{slope*(right-left):.3f}', '毫秒'))
            proof.append((f'{a}–{b} 锚段', f'{ppm:.3f}', 'ppm'))
    return duration.quantize(QUANTUM), proof


def timecodes(row):
    """校准片段起止时码（毫秒），与时长共用同一套锚点与漂移校验。"""
    points, _, start, end = anchor_points(row)
    return calibrate(points, start), calibrate(points, end)
