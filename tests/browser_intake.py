from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
initial='이름: 가상검증대상\n성별: 남\n생년월일: 2013-10-17\n아버님 키: 171 cm\n어머님 키: 160 cm\n현재 키: 154.2 cm\n현재 체중: 43.6 kg\n체지방률: 12.5%\nECW-Ratio: 0.385'
followup=initial.replace('154.2','158.8').replace('43.6','48.2').replace('12.5%','14.1%').replace('0.385','0.378')+'\n이전 회차 골연령: 12년 8개월\n이전 회차 성장단계: Stage 2\n이전 회차 예측키: 174.5 cm'
doc=fitz.open();p=doc.new_page(width=100,height=70);p.insert_text((10,25),'TEST IMAGE');raw=p.get_pixmap().tobytes('png')
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1050})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8093/workspace');page.wait_for_selector('#intake-memo')
 page.fill('#intake-memo',followup)
 assert page.input_value('[name=height]')=='158.8'
 assert page.input_value('[name=previous_bone_age_months]')=='152'
 assert page.input_value('[name=visit_number]')=='2'
 assert page.input_value('[name=bone_age]')==''
 assert page.input_value('[name=exam]')==''
 page.fill('[name=exam]','2026-09-23')
 for group in ['ulna','radius','femur']:
  page.set_input_files(f'#file-input-{group}',[{'name':f'{group}-{i}.png','mimeType':'image/png','buffer':raw} for i in range(5)])
  assert page.locator('#count-'+group).inner_text()=='5 / 5장'
 page.set_input_files('#file-input',{'name':'extra.txt','mimeType':'text/plain','buffer':'추가 가상 기록'.encode()})
 assert page.locator('.file-row').count()==16
 page.uncheck('#use-ai');page.click('#analyze');page.wait_for_selector('.report-top');page.wait_for_selector('#growth-chart svg')
 result=page.locator('#result').inner_text()
 assert '이전 회차 기록' in result and '12년 8개월' in result and 'Stage 2' in result
 assert '이번 검진자료 16개' in result and '대퇴골 원위부' in result
 page.screenshot(path=str(ROOT/'artifacts/memo-followup.png'),full_page=True)
 # Replacing the memo clears the prior visit fields rather than carrying them over.
 page.fill('#intake-memo',initial)
 assert page.input_value('[name=previous_bone_age_months]')==''
 assert page.input_value('[name=previous_stage]')==''
 assert page.input_value('[name=visit_number]')=='1'
 assert page.locator('.result-empty').count()==1
 page.fill('[name=exam]','2026-09-23')
 page.uncheck('#use-ai');page.click('#analyze');page.wait_for_selector('.report-top')
 assert page.locator('.previous-record').count()==0
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 page.screenshot(path=str(ROOT/'artifacts/memo-mobile.png'),full_page=True)
 page.on('dialog',lambda dialog:dialog.accept())
 page.click('#new-exam')
 assert page.locator('.file-row').count()==0
 assert page.input_value('#intake-memo')==''
 assert page.input_value('[name=name]')==''
 assert page.input_value('[name=exam]')==''
 assert page.locator('.result-empty').count()==1
 assert not errors,errors
 browser.close()
 print('PASS: paste first/followup, no previous/current mix, 15 site images + extra, local evaluation, replacement clears prior fields, mobile, no JS errors. No AI requests made.')
