import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '声轨对时台'
SLUG = 'sound-drift'
KEY = '声轨片段'
FIELDS = ('采样率赫兹', '允许漂移ppm', '锚点', '片段始样本', '片段末样本')
ROLE = '口述历史音频整理员'
UNIT = '毫秒'
RULE_VERSION = 'sound-drift-1.0'
SIGNATURE = '对齐锚段'
TABS = {'intake': '录音来源', 'contract': '锚点字段', 'quality': '时码异常', 'domain': '双锚校时', 'reconcile': '制作勾稽', 'runs': '片段批次', 'review': '校时复核'}
