from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8093');page.wait_for_function("!document.querySelector('#connection').textContent.includes('확인 중')")
 page.screenshot(path=str(ROOT/'artifacts/desktop.png'),full_page=True)
 page.click('#sample');page.uncheck('#use-ai');page.click('#analyze');page.wait_for_selector('.report-top')
 page.wait_for_selector('#growth-chart svg');assert page.locator('.metric').count()==4
 assert 'AI 미실행' in page.locator('#result').inner_text()
 page.screenshot(path=str(ROOT/'artifacts/result.png'),full_page=True)
 page.fill('[name=height]','155');assert page.locator('.result-empty').count()==1
 page.set_input_files('#file-input',{'name':'test.txt','mimeType':'text/plain','buffer':'테스트 기록. 신장 155cm'.encode()})
 assert page.locator('.file-row').count()==1
 page.uncheck('#use-ai');page.click('#analyze');page.wait_for_selector('.report-top');assert 'test.txt' in page.locator('#result').inner_text()
 page.click('[data-view=library]');assert page.locator('.library-item').count()==11
 page.fill('#search-query','골단');page.click('#search-form button');page.wait_for_selector('.search-hit')
 page.set_viewport_size({'width':390,'height':844});page.click('[data-view=assessment]')
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 page.screenshot(path=str(ROOT/'artifacts/mobile.png'),full_page=True)
 assert not errors,errors
 browser.close()
 print('Browser checks passed: desktop, mobile, sample, input invalidation, attachment, evaluation, library, search; no JS errors.')
