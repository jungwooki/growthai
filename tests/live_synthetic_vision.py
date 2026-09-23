"""Opt-in smoke test: only synthetic blank pixels/text, NO patient or reference files."""
from pathlib import Path
import sys,base64,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
import httpx,fitz
from backend.vision_report import PROMPT,ClinicalReport,strict_schema,validate_report
ROOT=Path(__file__).resolve().parents[1]
env=dotenv_values(ROOT/'.env')
d=fitz.open();page=d.new_page(width=240,height=140);page.insert_text((20,50),'SYNTHETIC TEST - NO ULTRASOUND')
image=base64.b64encode(page.get_pixmap().tobytes('png')).decode()
context=dict(patient={'age':'12세 0개월','sex':1,'height':150,'weight':40,'observations':'실제 환자가 없는 기능 검증용 가상 정보'},reference_pages=[],files=[dict(id='F01',group='ulna',name='synthetic-blank.png',visual=True)])
body=dict(model=env.get('OPENAI_MODEL','gpt-4.1'),store=False,instructions=PROMPT,input=[dict(role='user',content=[dict(type='input_text',text=json.dumps(context,ensure_ascii=False)),dict(type='input_text',text='PATIENT_FILE F01 | group=ulna | 실제 의료영상이 아닌 가상 빈 이미지. 근거와 영상 부족 시 판단 보류.'),dict(type='input_image',image_url='data:image/png;base64,'+image,detail='high')])],text={'format':{'type':'json_schema','name':'growth_image_report','strict':True,'schema':strict_schema()}},max_output_tokens=6000)
try:
 with httpx.Client(timeout=180) as c:r=c.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+env['OPENAI_API_KEY']},json=body)
 print('HTTP',r.status_code,flush=True)
 if r.status_code!=200:
  print('Error code:',r.json().get('error',{}).get('code'));sys.exit(1)
 payload=r.json();print('Completion:',payload.get('status'),flush=True)
 text=''.join(c.get('text','') for i in payload.get('output',[]) for c in i.get('content',[]) if c.get('type')=='output_text')
 report=ClinicalReport.model_validate_json(text)
 result,_,_=validate_report(report,[],set(),context['files'],lambda p:p)
 assert all(result[k]['status']=='insufficient' for k in ['bone_age','phv','adult_height'])
 assert all(i['quality']=='unusable' for i in result['image_readings'])
 (ROOT/'artifacts/synthetic-vision-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('PASS: real API image input + structured nine-section report; synthetic non-medical image not assigned bone age, PHV or final height.')
except Exception as e:
 print('Test error type:',type(e).__name__);sys.exit(1)
