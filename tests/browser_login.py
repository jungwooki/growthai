"""Run against a local server started with the preview-only credentials below."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8097/',wait_until='networkidle')
 assert not page.locator('#login-dialog').is_visible()
 assert page.locator('.service-card').count()==3
 assert page.locator('.brand-badge img').evaluate('(img)=>img.complete && img.naturalWidth>0')
 page.screenshot(path=str(ROOT/'artifacts/landing-desktop.png'),full_page=True)
 for width,height in [(390,844),(320,568)]:
  page.set_viewport_size({'width':width,'height':height})
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  if width==390:page.screenshot(path=str(ROOT/'artifacts/landing-mobile.png'),full_page=True)
 page.locator('.guide-card summary').click()
 assert page.locator('.guide-content').is_visible()
 page.locator('[data-open-login]').first.click()
 assert page.locator('#login-dialog').is_visible()
 page.keyboard.press('Escape')
 assert not page.locator('#login-dialog').is_visible()
 page.locator('[data-open-login]').last.click()
 page.set_viewport_size({'width':390,'height':844})
 page.screenshot(path=str(ROOT/'artifacts/login-mobile.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':1000})
 page.screenshot(path=str(ROOT/'artifacts/login-desktop.png'),full_page=True)
 page.fill('#username','preview-clinician');page.fill('#password','wrong-password')
 page.click('#toggle-password');assert page.locator('#password').get_attribute('type')=='text'
 page.click('#toggle-password');assert page.locator('#password').get_attribute('type')=='password'
 page.click('#login-button');page.wait_for_selector('#login-error:not([hidden])')
 assert '아이디 또는 비밀번호' in page.locator('#login-error').inner_text()
 page.fill('#password','preview-password-12345');page.click('#login-button')
 page.wait_for_url('**/workspace');page.wait_for_selector('#assessment-form')
 assert page.evaluate('localStorage.length')==0
 cookie=next(c for c in page.context.cookies() if c['name']=='growthai_session')
 assert cookie['httpOnly'] and cookie['sameSite']=='Strict'
 page.click('#sample');page.uncheck('#use-ai');page.click('#analyze')
 page.wait_for_selector('.report-top');page.wait_for_selector('#growth-chart svg')
 page.get_by_role('button',name='로그아웃',exact=True).click()
 page.wait_for_url('**/?logged_out=1');page.wait_for_selector('#login-notice:not([hidden])')
 assert not any(c['name']=='growthai_session' for c in page.context.cookies())
 page.goto('http://127.0.0.1:8097/workspace');page.wait_for_url('**/?login=required')
 assert not errors,errors
 browser.close()
 print('PASS: desktop/mobile login, wrong password, visibility toggle, successful session, evaluation, logout, protected workspace')
