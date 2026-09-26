"""Application-wide estimated spend ledger; no patient content or credentials."""
import asyncio
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from . import media_storage, centers

KST = timezone(timedelta(hours=9))
# USD per million tokens. Verified 2026-09-26; unknown models fail closed.
RATES = {'gpt-4.1': ('2', '0.5', '8'), 'gpt-4.1-2025-04-14': ('2', '0.5', '8')}


def enabled():
    return os.getenv('BUDGET_STORAGE') == 's3'


def month_now():
    return datetime.now(KST).strftime('%Y-%m')


def fresh(month):
    return dict(month=month, limit_krw=int(os.getenv('BUDGET_MONTHLY_KRW', '50000')),
                overhead_krw=int(os.getenv('BUDGET_OVERHEAD_KRW', '10000')),
                usd_krw=os.getenv('BUDGET_USD_KRW', '1500'),
                tax_multiplier=os.getenv('BUDGET_TAX_MULTIPLIER', '1.10'),
                entries={}, approvals=[])


@contextmanager
def client():
    try:
        s3 = media_storage.s3_client()
        try:
            yield s3
        finally:
            s3.close()
    except (BotoCoreError, ClientError, ValueError, KeyError, TypeError):
        raise HTTPException(503, '비용 기록 저장소를 확인할 수 없습니다. AI 요청 전 연결을 확인해주세요.')


def read(s3, month):
    try:
        response = s3.get_object(Bucket=os.environ['MEDIA_S3_BUCKET'], Key=f'budget/{month}.json')
    except s3.exceptions.NoSuchKey:
        return fresh(month), None
    with response['Body'] as body:
        raw = body.read(4_000_001)
    if len(raw) > 4_000_000:
        raise HTTPException(503, '월 비용 기록이 너무 큽니다. 관리자 확인이 필요합니다.')
    return json.loads(raw), response['ETag']


def change(month, operation):
    with client() as s3:
        for attempt in range(6):
            ledger, etag = read(s3, month)
            result = operation(ledger)
            body = json.dumps(ledger, separators=(',', ':')).encode()
            if len(body) > 4_000_000:
                raise HTTPException(503, '월 비용 기록을 정리한 뒤 다시 요청해주세요.')
            try:
                s3.put_object(Bucket=os.environ['MEDIA_S3_BUCKET'], Key=f'budget/{month}.json',
                              Body=body, ContentType='application/json', ServerSideEncryption='AES256',
                              **({'IfMatch': etag} if etag else {'IfNoneMatch': '*'}))
                return result
            except ClientError as error:
                if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') not in (409, 412):
                    raise
                time.sleep(0.02*(attempt+1))
        raise HTTPException(409, '다른 비용 기록이 갱신 중입니다. 잠시 후 다시 시도해주세요.')


def view(ledger):
    entries = list(ledger['entries'].values())
    ai = sum(e['krw'] for e in entries if e['state'] == 'settled')
    pending = sum(e['krw'] for e in entries if e['state'] == 'pending')
    total = ai+pending+ledger['overhead_krw']
    limit = ledger['limit_krw']
    return dict(enabled=True, month=ledger['month'], limit_krw=limit,
                ai_estimated_krw=ai, pending_krw=pending,
                overhead_estimated_krw=ledger['overhead_krw'], estimated_total_krw=total,
                remaining_krw=max(0, limit-total),
                level='decision' if total>=limit else 'warning' if total*10>=limit*9 else 'notice' if total*10>=limit*7 else 'normal',
                usd_krw=ledger['usd_krw'], tax_multiplier=ledger['tax_multiplier'],
                settled_calls=sum(e['state']=='settled' for e in entries),
                pending_calls=sum(e['state']=='pending' for e in entries),
                stages={stage:sum(e['krw'] for e in entries if e['stage']==stage and e['state']=='settled')
                        for stage in ('extraction', 'interpretation')},
                notice='앱 AI 사용량의 추정액 + 서버·저장소 예비비입니다. 실제 청구서가 아니며 다른 앱 사용료는 포함하지 않습니다.')


def status():
    if not enabled():
        return dict(enabled=False)
    with client() as s3:
        ledger, _ = read(s3, month_now())
        return view(ledger)


def price(model, usage, ledger):
    if model not in RATES:
        raise HTTPException(503, '이 AI 모델의 비용 단가가 등록되지 않았습니다.')
    inp, cached, out = map(Decimal, RATES[model])
    total_in = int(usage['input_tokens'])
    total_out = int(usage['output_tokens'])
    cached_n = int(usage.get('input_tokens_details', {}).get('cached_tokens', 0))
    if min(total_in, total_out, cached_n)<0 or cached_n>total_in:
        raise ValueError('Invalid usage')
    usd = ((total_in-cached_n)*inp+cached_n*cached+total_out*out)/Decimal(1_000_000)
    return int((usd*Decimal(ledger['usd_krw'])*Decimal(ledger['tax_multiplier'])).to_integral_value(rounding=ROUND_CEILING))


def reservation_usage(payload):
    # Conservative working allowance, not a provider token counter or billing cap.
    text_bytes = len(payload.get('instructions', '').encode('utf-8'))
    text_bytes += len(json.dumps(payload.get('text', {}), ensure_ascii=False).encode('utf-8'))
    images = 0
    for message in payload.get('input', []):
        for part in message.get('content', []):
            if part.get('type') == 'input_image':
                images += 1
            else:
                text_bytes += len(part.get('text', '').encode('utf-8'))
    return dict(input_tokens=text_bytes+images*5000, output_tokens=payload['max_output_tokens'])


def reserve(payload, stage):
    month = month_now()
    request_id = uuid.uuid4().hex
    def operation(ledger):
        cost = price(payload['model'], reservation_usage(payload), ledger)
        state = view(ledger)
        if state['estimated_total_krw']+cost > ledger['limit_krw']:
            if centers.center_id():
                raise HTTPException(402,'이번 달 사용 예산을 확인해야 합니다. MPS 본부에 추가 사용 승인을 요청해주세요.')
            raise HTTPException(402, dict(code='budget_decision_required', budget=state,
                request_allowance_krw=cost, message='이번 AI 요청의 예비비가 남은 예산을 넘습니다. 추가 예산 승인 또는 보류를 선택해주세요.'))
        ledger['entries'][request_id] = dict(state='pending', krw=cost, stage=stage,
            model=payload['model'], created=datetime.now(timezone.utc).isoformat(),
            center=(centers.current.get() or {}).get('center'), completed=False)
        return (month, request_id)
    return change(month, operation)


def settle(reservation, payload):
    month, request_id = reservation
    def operation(ledger):
        entry = ledger['entries'][request_id]
        if entry['state'] == 'settled':
            return
        usage = payload['usage']
        entry.update(state='settled', krw=price(entry['model'], usage, ledger),
                     input_tokens=int(usage['input_tokens']), output_tokens=int(usage['output_tokens']),
                     cached_tokens=int(usage.get('input_tokens_details', {}).get('cached_tokens', 0)))
    change(month, operation)


def approve(month, expected_limit, new_limit):
    if not enabled():
        raise HTTPException(503, '비용 관리 연결이 필요합니다.')
    if month != month_now():
        raise HTTPException(409, '월이 변경되었습니다. 비용 화면을 새로고침해주세요.')
    def operation(ledger):
        if ledger['limit_krw'] == new_limit:
            return view(ledger)  # Retried approval is idempotent.
        if ledger['limit_krw'] != expected_limit or new_limit <= expected_limit:
            raise HTTPException(409, '예산이 변경되었습니다. 현재 금액을 다시 확인해주세요.')
        ledger['approvals'].append(dict(previous_krw=expected_limit, approved_krw=new_limit,
                                        at=datetime.now(timezone.utc).isoformat(),
                                        approved_by=(centers.current.get() or {}).get('username','legacy')))
        ledger['limit_krw'] = new_limit
        return view(ledger)
    return change(month, operation)


def release_rejected(reservation, code):
    month, request_id = reservation
    def operation(ledger):
        entry = ledger['entries'][request_id]
        if entry['state'] != 'pending': return
        entry.update(state='rejected', reserved_krw=entry['krw'], krw=0,
                     rejection_code=code, completed=False)
    change(month, operation)


def rate_rejection(response):
    if response.status_code != 429: return None
    try:
        error = response.json().get('error', {})
        code = error.get('code') or error.get('type')
        if code not in {'rate_limit_exceeded','rate_limit_error','insufficient_quota'}: return None
        message = str(error.get('message',''))
        counts = {label:int(match.group(1).replace(',','')) for label in ('Limit','Requested')
                  if (match:=re.search(r'\b'+label+r'\s*:?\s*([\d,]+)',message,re.I))}
        oversized = counts.get('Requested',0)>counts.get('Limit',float('inf'))
        return code, oversized
    except (ValueError,AttributeError,TypeError): return None


async def post_ai(http_client, *, payload, headers, stage):
    if centers.enabled() and not enabled():
        raise HTTPException(503,'센터 사용량 기록 저장소 연결이 필요합니다. 본부에 문의해주세요.')
    for attempt in range(2):
        reservation = await run_in_threadpool(reserve, payload, stage) if enabled() else None
        # Network failures remain uncertain; explicit provider rejection is different.
        response = await http_client.post('https://api.openai.com/v1/responses', headers=headers, json=payload)
        if reservation: response.extensions['growthai_reservation'] = reservation
        rejection = rate_rejection(response)
        if rejection:
            code, oversized = rejection
            if reservation: await run_in_threadpool(release_rejected, reservation, code)
            if attempt == 0 and code != 'insufficient_quota' and not oversized:
                await asyncio.sleep(61)
                continue
        if reservation and response.status_code == 200:
            data = response.json()
            if isinstance(data,dict) and isinstance(data.get('usage'),dict):
                await run_in_threadpool(settle,reservation,data)
        return response


async def completed(response):
    reservation = getattr(response,'extensions',{}).get('growthai_reservation')
    if reservation:
        def operation(ledger):
            ledger['entries'][reservation[1]]['completed']=True
        await run_in_threadpool(change,reservation[0],operation)


def monthly(month, center_id=None):
    if not re.fullmatch(r'20[0-9]{2}-(0[1-9]|1[0-2])',month):
        raise HTTPException(422,'조회 월을 YYYY-MM 형식으로 선택해주세요.')
    if not enabled():
        raise HTTPException(503,'사용량 기록 저장소가 연결되지 않았습니다.')
    with client() as s3:
        ledger,_=read(s3,month)
    catalog={c['id']:c for c in centers.registry()['centers']}
    entries=list(ledger['entries'].values())
    for entry in entries:
        c=entry.get('center')
        if c:catalog.setdefault(c['id'],c)
    rows={}
    def blank(c):
        return dict(**c,extraction_calls=0,interpretation_calls=0,completed_interpretations=0,
                    completed_extractions=0,pending_calls=0,ai_estimated_krw=0,pending_krw=0)
    for key,c in catalog.items():
        if center_id is None or key==center_id:rows[key]=blank(c)
    for entry in entries:
        c=entry.get('center')
        key=c['id'] if c else 'unassigned'
        if center_id is not None and key!=center_id:continue
        if key not in rows:rows[key]=blank(dict(id=key,name='센터 지정 전 사용',region='미지정'))
        row=rows[key]
        stage=entry['stage']
        row[stage+'_calls']+=1
        if entry.get('completed'):
            row['completed_interpretations' if stage=='interpretation' else 'completed_extractions']+=1
        if entry['state']=='pending':
            row['pending_calls']+=1
            row['pending_krw']+=entry['krw']
        else:row['ai_estimated_krw']+=entry['krw']
    regions={}
    for row in rows.values():
        region=row['region']
        if region not in regions:regions[region]=blank(dict(id=region,name=region,region=region))
        for field in row:
            if field not in ('id','name','region'):regions[region][field]+=row[field]
    return dict(month=month,timezone='Asia/Seoul',centers=list(rows.values()),regions=list(regions.values()),
                notice='호출 기준 통계입니다. 재판독도 별도 집계하며 환자 수가 아닙니다. 완료는 응답 형식 검증 통과 기준이며 의료진 최종 확정 건수가 아닙니다. 비용은 AI 추정액이며 서버·저장소 요금은 제외됩니다.')
