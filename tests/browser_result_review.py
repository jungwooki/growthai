"""Synthetic browser integration. --serve starts a loopback-only mocked AI app."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PORT = 8097
BASE = f'http://127.0.0.1:{PORT}'

if '--serve' in sys.argv:
    os.environ.update(APP_ENV='development', APP_USERNAME='', APP_PASSWORD='',
                      OPENAI_API_KEY='synthetic-test-only', MEDIA_STORAGE='', VERCEL='')
    import uvicorn
    from fastapi import HTTPException
    from backend import server, result_extraction
    from backend.web_access import WebAccess
    server.ACCESS = WebAccess(False, frozenset({'127.0.0.1'}), '', '')
    server.MANIFEST = []  # Fake stages do not read reference PDFs.
    counts = dict(extract=0, synthesize=0)
    async def extract(content, summaries):
        counts['extract'] += 1
        assert sum(c['type'] == 'input_image' for c in content) == 1
        return dict(documents=[dict(file_id='F02', measurements=[
            dict(item='Weight', value='55.5', unit='kg', exam_date='2026-09-05',
                 location='Current result', reference='', note='', status='read'),
            dict(item='Unclear', value=None, unit='%', exam_date='',
                 location='Row 2', reference='', note='Unreadable', status='needs_review')],
            warnings=['Synthetic only'])], fingerprints=result_extraction.fingerprints(summaries),
            model='synthetic', usage={'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2})
    async def synthesize(p, metrics, selected, content, summaries):
        counts['synthesize'] += 1
        assert sum(c['type'] == 'input_image' for c in content) == 1
        text = next(c['text'] for c in content if c.get('text', '').startswith('REVIEWED_RESULT'))
        assert '56.0' in text and 'Unclear' not in text
        raise HTTPException(502, 'SYNTHETIC SYNTHESIS VERIFIED')
    server.result_extraction.extract = extract
    server.ask_ai = synthesize
    @server.app.get('/test-state')
    def state(): return counts
    uvicorn.run(server.app, host='127.0.0.1', port=PORT, log_level='warning')
else:
    import fitz
    from playwright.sync_api import sync_playwright
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=70)
        page.insert_text((10, 25), 'SYNTHETIC')
        raw = page.get_pixmap().tobytes('png')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE+'/workspace')
        page.wait_for_function("typeof ResultReview !== 'undefined' && status !== null")
        page.click('#sample')
        page.check('#use-ai')
        page.check('#consent')
        page.set_input_files('#file-input-ulna', {'name': 'ulna.png', 'mimeType': 'image/png', 'buffer': raw})
        page.set_input_files('#file-input', {'name': 'sheet.png', 'mimeType': 'image/png', 'buffer': raw})
        page.click('#analyze')
        page.wait_for_selector('.record-review')
        assert page.request.get(BASE+'/test-state').json() == {'extract': 1, 'synthesize': 0}
        page.click('#analyze')  # Reopen pending review without paying for another read.
        assert page.request.get(BASE+'/test-state').json() == {'extract': 1, 'synthesize': 0}
        assert page.locator('[data-field=include]').nth(0).is_checked()
        assert not page.locator('[data-field=include]').nth(1).is_checked()
        assert page.locator('.record-review a').get_attribute('href').startswith('blob:')
        page.click('#records-continue')
        assert page.locator('#records-error').is_visible()
        page.locator('[data-field=value]').nth(0).fill('56.0')
        page.check('#records-confirmed')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.click('#records-continue')
        page.wait_for_selector('.report-top')
        assert 'SYNTHETIC SYNTHESIS VERIFIED' in page.locator('#result').inner_text()
        result = page.evaluate('report')
        assert result['record_extraction']['original']['documents'][0]['measurements'][0]['value'] == '55.5'
        assert result['reviewed_records'][0]['measurements'][0]['value'] == '56.0'
        assert len(result['reviewed_records'][0]['measurements']) == 1
        page.click('#analyze')
        page.wait_for_selector('.report-top')
        assert page.request.get(BASE+'/test-state').json() == {'extract': 1, 'synthesize': 2}
        page.get_by_role('button', name='검사 결과지 수치 다시 확인').click()
        assert page.locator('[data-field=value]').nth(0).input_value() == '56.0'
        page.set_input_files('#file-input', {'name': 'changed.png', 'mimeType': 'image/png', 'buffer': raw})
        assert page.evaluate('ResultReview.current(files)') is None
        assert page.locator('.record-review').count() == 0
        page.on('dialog', lambda dialog: dialog.accept())
        page.click('#new-exam')
        assert page.evaluate('ResultReview.current(files)') is None
        assert page.locator('.record-review').count() == 0
        assert not errors, errors
        browser.close()
        print('PASS: extraction gate, original link, correction, exclusion, mobile, audit, retry reuse, new-exam reset; no paid AI calls.')
