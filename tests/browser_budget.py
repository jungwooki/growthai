"""Local synthetic budget UI verification; does not call AWS or OpenAI."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = 'http://127.0.0.1:8098'
if '--serve' in sys.argv:
    os.environ.update(APP_ENV='development', APP_USERNAME='', APP_PASSWORD='', OPENAI_API_KEY='',
                      MEDIA_STORAGE='', VERCEL='', BUDGET_STORAGE='s3',
                      MEDIA_S3_BUCKET='test', BUDGET_MONTHLY_KRW='50000', BUDGET_OVERHEAD_KRW='45000')
    import uvicorn
    from backend import server, budget, media_storage
    from backend.web_access import WebAccess
    from test_budget import Store
    store = Store()
    media_storage.s3_client = lambda: store
    server.ACCESS = WebAccess(False, frozenset({'127.0.0.1'}), '', '')
    @server.app.post('/test/attempt')
    def attempt():
        return budget.reserve(dict(model='gpt-4.1', input=[], max_output_tokens=1_000_000), 'interpretation')
    @server.app.get('/test/approvals')
    def approvals():
        ledger, _ = budget.read(store, budget.month_now())
        return {'count':len(ledger['approvals'])}
    uvicorn.run(server.app, host='127.0.0.1', port=8098, log_level='warning')
else:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        errors=[];page.on('pageerror', lambda error:errors.append(str(error)))
        page.goto(BASE+'/workspace')
        page.wait_for_selector('[data-budget-total]')
        assert '45,000원' in page.locator('[data-budget-total]').inner_text()
        assert '90%' in page.locator('[data-budget-warning]').inner_text()
        page.evaluate("api('test/attempt',{method:'POST'}).catch(()=>{})")
        page.wait_for_function("document.querySelector('#budget-panel details').open")
        assert '예비비' in page.locator('[data-budget-warning]').inner_text()
        page.fill('#budget-new-limit', '60000')
        page.click('#budget-approve')
        page.wait_for_function("document.querySelector('[data-budget-total]').textContent.includes('60,000원')")
        assert page.request.get(BASE+'/api/budget').json()['limit_krw'] == 60000
        assert page.request.get(BASE+'/test/approvals').json()['count'] == 1
        page.reload()
        page.wait_for_selector('[data-budget-total]')
        assert '60,000원' in page.locator('[data-budget-total]').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        browser.close()
        print('PASS: warning, decision prompt, explicit increase, reload persistence, mobile, no browser errors; no external calls.')
