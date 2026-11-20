from app.errors import DataError
from app.evidence import finding
from app.settings import UNIT
from .rule import evaluate, timecodes


def calculate(records):
    accepted, rejected = [], []
    for record in records:
        try:
            amount, proof = evaluate(record['fields'])
            start_ms, end_ms = timecodes(record['fields'])
        except DataError as error:
            rejected.append(finding(record, error.code, str(error)))
            continue
        accepted.append({'key': record['key'], 'line': record['line'], 'revision': record['revision'],
                         'amount': format(amount, 'f'), 'unit': UNIT,
                         'start_ms': format(start_ms, 'f'), 'end_ms': format(end_ms, 'f'),
                         'raw': record['raw'],
                         'proof': [{'metric': label, 'value': str(value), 'unit': unit} for label, value, unit in proof]})
    return accepted, rejected
