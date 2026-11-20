from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_split_clock(cases):
    actual, proof = evaluate(cases['split_clock'])
    assert actual == Decimal('1497.500')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['8000–9000 样本'])) == Decimal('249.500')


def test_single_span(cases):
    actual, proof = evaluate(cases['single_span'])
    assert actual == Decimal('500.200')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['0–4000 锚段'])) == Decimal('400.000')


def test_unit_scale(cases):
    actual, proof = evaluate(cases['unit_scale'])
    assert actual == Decimal('1000.000')
    assert proof


def test_exact_anchor(cases):
    actual, proof = evaluate(cases['exact_anchor'])
    assert actual == Decimal('100.000')
    assert proof


def test_leading_offset(cases):
    actual, proof = evaluate(cases['leading_offset'])
    assert actual == Decimal('250.000')
    assert proof


def test_large_index(cases):
    # TRAP-09
    actual, proof = evaluate(cases['large_index'])
    assert actual == Decimal('50.000')
    assert proof


def test_rewound(cases):
    # TRAP-108
    with pytest.raises(DataError) as error:
        evaluate(cases['rewound'])
    assert error.value.code == 'SOUND_REWIND'


def test_too_much_ppm(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['too_much_ppm'])
    assert error.value.code == 'SOUND_PPM'


def test_outside(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['outside'])
    assert error.value.code == 'SOUND_COVERAGE'
