import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datetime import date
from clinical_fixture import blank_report
from backend.vision_report import ClinicalReport,validate_report,select_references,strict_schema
from backend.growth_history import compute_history
from backend.server import PAGES,parse_files
import pytest,fitz,asyncio,io
from starlette.datastructures import UploadFile

@pytest.mark.parametrize('phase,expanded',[('pre_phv',True),('accelerating',True),('circa_phv',False),('post_phv',False),('uncertain',False)])
def test_height_policy_midpoint_and_phase_gate(phase,expanded):
 page=dict(id='R03:p46',text='reference')
 evidence=[dict(source_id=page['id'],kind='figure',quote='',explanation='comparison')]
 r=blank_report()
 r['phv'].update(status='estimated',phase=phase,evidence=evidence)
 r['adult_height'].update(status='estimated',basis='ai_synthesis',low=173.5,center=174,high=176.5,method='test synthesis',evidence=evidence)
 data,_,_=validate_report(ClinicalReport(**r),[page],{page['id']},[],lambda p:p)
 assert data['adult_height']['center']==175
 assert bool(data['adult_height']['operating_range'])==expanded
 if expanded:assert data['adult_height']['operating_range']=={'low':173.5,'high':180.5}

def test_reference_selection_covers_all_ages_and_correct_sex():
 male,visual=select_references(PAGES,1,[])
 assert all(f'R03:p{n}' in visual for n in range(39,50))
 assert 'R03:p50' not in visual
 female,visual=select_references(PAGES,2,[])
 assert all(f'R03:p{n}' in visual for n in range(50,61))
 assert 'R03:p46' not in visual
 assert 'R02:p28' in visual

def test_invalid_evidence_and_no_images_cannot_produce_estimate():
 r=blank_report();r['bone_age'].update(status='estimated',center=156,low=144,high=168,evidence=[dict(source_id='invented',kind='figure',quote='',explanation='fake')])
 data,rejected,_=validate_report(ClinicalReport(**r),[],set(),[],lambda p:p)
 assert data['bone_age']['status']=='insufficient' and data['bone_age']['center'] is None and rejected==1

def test_figure_citation_requires_sent_reference_image():
 page=dict(id='R03:p46',text='참고자료의 실제 설명입니다.')
 r=blank_report();r['phv'].update(status='estimated',label='성장시기 추정',evidence=[dict(source_id=page['id'],kind='figure',quote='',explanation='해당 표')])
 data,_,_=validate_report(ClinicalReport(**r),[page],set(),[],lambda p:p)
 assert data['phv']['status']=='insufficient'
 data,_,_=validate_report(ClinicalReport(**r),[page],{page['id']},[],lambda p:p)
 assert data['phv']['status']=='estimated'

def test_unknown_patient_image_and_wrong_group_excluded():
 r=blank_report();r['image_readings']=[dict(file_id='F01',group='ulna',quality='usable',observations=['test'],visible_measurements=[],limitation='test')]
 data,_,warnings=validate_report(ClinicalReport(**r),[],set(),[dict(id='F01',group='radius',visual=True,name='test.png')],lambda p:p)
 assert not data['image_readings'] and warnings

def test_actual_upload_markers_distinguish_reference_and_patient():
 d=fitz.open();p=d.new_page(width=80,height=60);raw=p.get_pixmap().tobytes('png')
 content,summary=asyncio.run(parse_files([UploadFile(io.BytesIO(raw),filename='synthetic.png')],['ulna']))
 assert 'PATIENT_FILE F01' in content[0]['text']
 assert summary[0]['visual'] and summary[0]['id']=='F01'
 assert any(x.get('type')=='input_image' and x['detail']=='high' for x in content)

def test_dated_history_is_computed_not_invented():
 h=compute_history('2026-04-30 154.2 cm\n2026-07-01 155.5 cm\n2026-08-19 156.9 cm',date(2013,10,17),date(2026,9,19),158.8)
 assert h['overall']['days']==142 and h['overall']['change']==4.6
 assert h['overall']['value']==11.83
 assert len(h['points'])==4 and len(h['intervals'])==3
 with pytest.raises(ValueError):compute_history('04-30 154.2',date(2013,10,17),date(2026,9,19),158.8)
 with pytest.raises(ValueError):compute_history('2026-09-19 150.0',date(2013,10,17),date(2026,9,19),158.8)

def test_schema_requires_all_report_sections():
 s=strict_schema()
 assert len(s['required'])==10 and s['additionalProperties'] is False
 assert set(s['required'])==set(s['properties'])
