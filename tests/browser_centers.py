"""Loopback-only synthetic multi-center browser verification. No cloud calls."""
import os
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
BASE='http://127.0.0.1:8099'
PASSWORD='test-only-password-2026'

if '--serve' in sys.argv:
    from backend import centers
    hashed=centers.hash_password(PASSWORD)
    config=dict(centers=centers.DEFAULT_CENTERS,users=[dict(username=u,role=r,center_id=c,password_hash=hashed) for u,r,c in [('hq','headquarters',None),('seoul','center','seoul-rnd'),('dongtan','center','gyeonggi-dongtan')]])
    os.environ.update(APP_ENV='local',APP_CENTER_AUTH_JSON=json.dumps(config),APP_SESSION_SECRET='test-only-session-secret-'+('x'*32),APP_USERNAME='',APP_PASSWORD='',OPENAI_API_KEY='',MEDIA_STORAGE='',VERCEL='',BUDGET_STORAGE='s3',MEDIA_S3_BUCKET='test',BUDGET_MONTHLY_KRW='50000',BUDGET_OVERHEAD_KRW='10000')
    from backend import server,budget,media_storage
    from backend.web_access import WebAccess
    from test_budget import Store
    store=Store();media_storage.s3_client=lambda:store
    server.ACCESS=WebAccess(False,frozenset({'127.0.0.1'}),'','')
    def seed(ledger):
        for i,c in enumerate(centers.DEFAULT_CENTERS):
            ledger['entries'][str(i)]=dict(center=c,stage='interpretation',state='settled',krw=100*(i+1),completed=True)
    budget.change(budget.month_now(),seed)
    import uvicorn
    uvicorn.run(server.app,host='127.0.0.1',port=8099,log_level='warning')
else:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1360,'height':950})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def login(user):
            page.goto(BASE+'/#login');page.fill('#username',user);page.fill('#password',PASSWORD);page.click('#login-button')
        login('hq');page.wait_for_url('**/headquarters');page.wait_for_selector('#center-rows tr')
        assert page.locator('#center-rows tr').count()==2
        assert '서울R&D센터' in page.locator('#center-rows').inner_text()
        assert '경기화성동탄센터' in page.locator('#center-rows').inner_text()
        assert page.locator('#region-rows tr').count()==2
        with page.expect_download() as download:page.click('#download')
        assert download.value.suggested_filename.startswith('MPS-GrowthAI-')
        page.fill('#month','2020-01');page.click('#refresh');page.wait_for_function("document.querySelector('#status').textContent.includes('2020-01')")
        assert '0회' in page.locator('#totals').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(Path(__file__).resolve().parents[1]/'artifacts/centers-mobile.png'),full_page=True)
        page.click('#logout');page.wait_for_url('**/?logged_out=1')
        for user,name in [('seoul','서울R&D센터'),('dongtan','경기화성동탄센터')]:
            login(user);page.wait_for_url('**/workspace');page.wait_for_function("document.querySelector('#budget-panel').textContent.includes('센터')")
            assert name in page.locator('#budget-panel').inner_text()
            assert page.locator('#budget-approve').count()==0
            assert page.request.get(BASE+'/headquarters').status==403
            assert len(page.request.get(BASE+'/api/usage/monthly').json()['centers'])==1
            page.request.post(BASE+'/api/auth/logout')
        assert not errors,errors
        browser.close()
    print('PASS: HQ month/region/CSV, mobile layout, two center logins and cross-role denial; no cloud calls.')
