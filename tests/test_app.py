import sys, json, io
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,fitz
from fastapi.testclient import TestClient
from backend.server import app,Patient,calculate,age_months,table_comparison,AIResult,verify_findings,GROWTH
client=TestClient(app)
BASE=dict(code='TEST',sex=1,birth='2014-09-23',exam='2026-09-23',height=151.2,weight=42.5)
def test_preview_calculates_without_ai_or_images():
 result=client.post('/api/preview',json=BASE)
 assert result.status_code==200
 assert result.json()['metrics']['bmi']['value']>0
 assert 'ai' not in result.json()
@pytest.mark.parametrize('error,expected',[
 ({'code':'insufficient_quota'},'크레딧 또는 지출 한도 부족'),
 ({'code':'rate_limit_exceeded','message':'org-private Limit: 30000, Requested: 42000 sk-secret'},'한 번의 요청이 허용량을 초과'),
 ({'type':'rate_limit_error','message':'Limit 30000 Used 29000 Requested 2000'},'잠시 기다린 뒤'),
 ({'message':'sk-secret org-private'},'상세 원인을 확인할 수 없습니다'),
])
def test_api_limit_error_is_actionable_and_redacted(error,expected):
 from backend.server import ai_failure_message
 class Response:
  status_code=429
  headers={'x-ratelimit-limit-tokens':'30000'}
  def json(self):return {'error':error}
 result=ai_failure_message(Response())
 assert expected in result
 assert 'sk-secret' not in result and 'org-private' not in result

def evaluate(data=None,files=None):return client.post('/api/evaluate',data={'patient':json.dumps(data or BASE)},files=files)
def test_month_boundary():
 assert age_months(date(2014,9,23),date(2026,9,22))==143
 assert age_months(date(2014,9,23),date(2026,9,23))==144
@pytest.mark.parametrize('sex',[1,2])
def test_exact_median_matches_original_table(sex):
 row=next(r for r in GROWTH['연령별 신장']['rows'] if r['sex']==sex and r['months']==144)
 result=table_comparison('연령별 신장',sex,144,row['values'][6])
 assert result['band']=='50백분위 표 값과 일치'
 assert result['row']==row['row']
def test_outside_table_does_not_extrapolate():
 assert not table_comparison('연령별 신장',1,228,170)['available']
def test_comparison_and_no_fake_ai():
 r=evaluate().json();assert r['ai'] is None
 assert r['metrics']['height']['available']
 assert r['metrics']['bmi']['value']==18.59
 assert '판단 보류' in r['banding']
def test_dates_and_incomplete_prior_pair():
 for update in [dict(birth='2027-01-01'),dict(previous_date='2026-09-23',previous_height=148),dict(previous_height=148),dict(bone_age=12),dict(height=float('nan'))]:
  assert evaluate({**BASE,**update}).status_code==422
def test_velocity():
 m=calculate(Patient(**{**BASE,'previous_date':'2025-09-23','previous_height':145.2}))
 assert m['velocity']['days']==365
 assert abs(m['velocity']['value']-6)<.02
def test_citation_mismatch_filtered():
 selected=[dict(id='R01:p1',text='이 문장은 인용 검증을 위한 충분히 긴 문장입니다.')]
 good=dict(title='t',assessment='a',source_id='R01:p1',quote='이 문장은 인용 검증을 위한 충분히 긴 문장입니다.',limitation='l')
 bad={**good,'quote':'원문에는 존재하지 않는 잘못된 인용문입니다.'}
 from backend import server
 original=server.source_view
 server.source_view=lambda p: {'id':p['id']}
 try:
  valid,rejected=verify_findings(AIResult(summary='',extracted_records=[],findings=[good,bad,{**good,'source_id':'madeup'}],missing=[],review_questions=[]),selected)
  assert len(valid)==1 and rejected==2
 finally:server.source_view=original
def test_missing_key_is_explicit(monkeypatch):
 monkeypatch.delenv('OPENAI_API_KEY',raising=False)
 r=evaluate({**BASE,'use_ai':True,'consent':True}).json()
 assert r['ai'] is None and 'OPENAI_API_KEY' in r['ai_error']
def test_file_parse_and_invalid_file():
 d=fitz.open();p=d.new_page();p.insert_text((72,72),'Test report height 151.2 cm. '*8)
 r=evaluate(files=[('files',('report.pdf',d.tobytes(),'application/pdf'))])
 assert r.status_code==200 and r.json()['files'][0]['detail']=='1페이지 · 스캔 0페이지'
 assert evaluate(files=[('files',('bad.pdf',b'not a pdf','application/pdf'))]).status_code==422
 assert evaluate(files=[('files',('bad.html',b'<script/>','text/html'))]).status_code==422
def test_local_access_and_sensitive_paths():
 assert client.get('/.env').status_code==404
 assert client.get('/server.py').status_code==404
 assert client.get('/',headers={'host':'evil.example'}).status_code==400
 assert client.post('/api/evaluate',headers={'origin':'https://evil.example'}).status_code==403
 assert client.get('/api/library').status_code==200
 assert len(client.get('/api/library').json())==11
 assert client.get('/api/sources/R01').status_code==200
def test_ai_contract_with_mocked_response(monkeypatch):
 from backend import server
 from clinical_fixture import blank_report
 monkeypatch.setenv('OPENAI_API_KEY','test-only-not-a-real-key')
 selected=server.search_pages('초음파 골단')
 mock_result=blank_report()
 class FakeResponse:
  status_code=200
  def json(self):return dict(status='completed',output=[dict(content=[dict(type='output_text',text=json.dumps(mock_result))])])
 class FakeClient:
  def __init__(self,**kw):pass
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def post(self,url,headers,json):
   assert url=='https://api.openai.com/v1/responses'
   assert json['store'] is False
   texts=[__import__('json').loads(c['text']) for c in json['input'][0]['content'] if c['type']=='input_text' and c['text'].startswith('{')]
   context={k:v for item in texts for k,v in item.items()}
   assert json['max_output_tokens']==6000
   assert 'code' not in context['patient'] and 'birth' not in context['patient']
   assert context['reference_pages'][0]['category']
   assert json['text']['format']['strict'] is True
   assert json['text']['format']['name']=='growth_image_report'
   return FakeResponse()
 monkeypatch.setattr(server.httpx,'AsyncClient',FakeClient)
 monkeypatch.setattr(server,'render_references',lambda *args: [])
 import asyncio
 result=asyncio.run(server.ask_ai(Patient(**{**BASE,'consent':True}),calculate(Patient(**BASE)),selected,[]))
 assert result['clinical_report']['bone_age']['center'] is None
 assert result['analysis_passes']==1
