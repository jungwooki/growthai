import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from backend.mps_guidance import normalize_stage, sports_plan, STAGES, PHASES

@pytest.mark.parametrize('number',range(5))
def test_stage_names_are_canonical_not_free_form(number):
    stage=dict(status='estimated',mps_stage=number,phase=PHASES[number],label='Tanner Stage 3',system='wrong')
    normalize_stage(stage)
    assert stage['label']==f'Stage {number} · {STAGES[number]}'
    assert stage['system'].startswith('MPS')

@pytest.mark.parametrize('number,phase',[(None,'accelerating'),(2,'post_phv'),(3,'circa_phv')])
def test_ambiguous_or_inconsistent_stage_does_not_get_a_number(number,phase):
    stage=dict(status='estimated',mps_stage=number,phase=phase,label='Stage 2')
    normalize_stage(stage)
    assert stage['mps_stage'] is None and stage['status']=='insufficient'
    assert 'Stage 2' not in stage['label']


def test_insufficient_evidence_overrides_model_number():
    stage=dict(status='insufficient',mps_stage=2,phase='accelerating',label='Stage 2')
    normalize_stage(stage)
    assert stage['mps_stage'] is None

@pytest.mark.parametrize('number',[None,0,1,2,3,4])
def test_plan_is_three_paragraphs_without_invented_body_composition(number):
    stage=dict(status='estimated' if number is not None else 'insufficient',mps_stage=number,label=f'Stage {number}')
    p=SimpleNamespace(body_fat=14.1)
    plan=sports_plan(p,{'phv':stage})
    assert len(plan['paragraphs'])==3
    assert '3개월' in plan['paragraphs'][0]
    text=' '.join(plan['paragraphs'])
    assert '14.1%' in text
    assert '과도하지 않고' not in text and '근육량도 증가' not in text
    assert '의료진' in plan['basis']
    if number is None:assert '확정하기 어려워' in plan['paragraphs'][1]


def test_missing_body_fat_not_replaced_with_example_value():
    plan=sports_plan(SimpleNamespace(body_fat=None),{'phv':{'status':'insufficient'}})
    assert '14.1' not in str(plan)
    assert '%' not in plan['paragraphs'][2]
