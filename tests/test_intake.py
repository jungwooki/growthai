import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from fastapi.testclient import TestClient
from backend.server import app,Patient,calculate,ai_patient_context
client=TestClient(app)
BASE=dict(name='가상대상',sex=1,birth='2013-10-17',exam='2026-09-23',height=158.8,weight=48.2,visit_number=2,father_height=171,mother_height=160,body_fat=14.1,ecw_ratio=.378,previous_bone_age_months=152,previous_stage='Stage 2',previous_predicted_height=174.5)
def test_previous_visit_is_not_current_bone_age():
 r=client.post('/api/evaluate',data={'patient':json.dumps(BASE)}).json()
 assert r['patient']['previous_bone_age_months']==152
 assert r['patient']['previous_stage']=='Stage 2'
 assert r['metrics']['bone_difference'] is None
 assert r['metrics']['velocity'] is None
 assert r['patient']['body_fat']==14.1 and r['patient']['ecw_ratio']==.378

def test_structured_identity_and_labeled_memo_identity_excluded():
 p=Patient(**BASE,intake_memo='이름: 가상대상\n생년월일: 2013-10-17\n현재 키: 158.8 cm\n메모: 기록 검토')
 context=ai_patient_context(p,calculate(p));t=json.dumps(context,ensure_ascii=False)
 assert '가상대상' not in t and '2013-10-17' not in t
 assert context['previous_visit']['bone_age_months']==152
 assert context['bone_age'] is None
 assert '기록 검토' in context['pasted_memo']

def image_bytes():
 d=fitz.open();p=d.new_page(width=80,height=60);p.insert_text((5,20),'TEST')
 return p.get_pixmap().tobytes('png')
def test_fifteen_site_images_and_extra_supported():
 raw=image_bytes();groups=['ulna']*5+['radius']*5+['femur']*5+['extra']
 files=[('files',(f'image-{i}.png',raw,'image/png')) for i in range(16)]
 r=client.post('/api/evaluate',data={'patient':json.dumps(BASE),'file_groups':json.dumps(groups)},files=files)
 assert r.status_code==200,r.text
 data=r.json();assert len(data['files'])==16
 assert [f['group'] for f in data['files']]==groups
 assert data['ai'] is None

def test_group_overflow_and_mismatches_rejected():
 raw=image_bytes()
 files=[('files',(f'image-{i}.png',raw,'image/png')) for i in range(6)]
 for groups in [['ulna']*6,['radius'],['unknown']*6]:
  r=client.post('/api/evaluate',data={'patient':json.dumps(BASE),'file_groups':json.dumps(groups)},files=files)
  assert r.status_code==422

def test_exam_date_required():
 p={k:v for k,v in BASE.items() if k!='exam'}
 assert client.post('/api/evaluate',data={'patient':json.dumps(p)}).status_code==422
