from pathlib import Path
from datetime import date
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.server import app
from clinical_fixture import blank_report
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
patient=dict(code='DEMO-VISION-UI',sex=1,birth='2014-09-23',exam='2026-09-23',height=150,weight=40,use_ai=False)
with TestClient(app) as c:response=c.post('/api/evaluate',data={'patient':json.dumps(patient)}).json()
response['patient']['use_ai']=True
report=blank_report()
# UI fixture only: verifies estimated display independently from live clinical inference.
report['bone_age'].update(status='estimated',center=156,low=144,high=168,method='가상 UI 테스트 값',reasoning='실제 판독 결과가 아닌 화면 검증 데이터입니다.')
response['ai']=dict(clinical_report=report,notice='가상 UI 검증 응답 · 실제 환자 판독 아님',model='UI TEST',reference_images=18,patient_images=0,analysis_passes=1,rejected_citations=0)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1080});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/api/evaluate',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(response,ensure_ascii=False)))
 page.goto('http://127.0.0.1:8093');page.wait_for_function("document.querySelector('#connection').textContent.includes('설정됨')")
 page.click('#sample');page.check('#use-ai');page.check('#consent');page.click('#analyze');page.wait_for_selector('.clinical-report')
 assert page.locator('.clinical-section').count()==9
 assert '13세 0개월' in page.locator('.clinical-highlights').inner_text()
 page.locator('.clinical-disclosure summary').click()
 assert '실제 환자 판독 아님' in page.locator('.clinical-disclosure').inner_text()
 assert page.locator('.clinical-highlights').inner_text().count('판단 보류')==2
 page.screenshot(path=str(ROOT/'artifacts/vision-report-ui.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 assert not errors,errors
 browser.close();print('PASS: nine sections, estimated/withheld states, mobile overflow, no JS errors. API response mocked; no external call.')
