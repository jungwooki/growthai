from pathlib import Path
from datetime import date
from typing import Optional, Literal
import base64, json, os, re, time
import fitz, httpx
from dotenv import load_dotenv
from .growth_history import compute_history
from .web_access import WebAccess
from .vision_report import ClinicalReport, PROMPT, select_references, render_references, strict_schema, validate_report
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
MANIFEST=json.loads((ROOT/'data/manifest.json').read_text())
PAGES=json.loads((ROOT/'data/pages.json').read_text())
GROWTH=json.loads((ROOT/'data/growth.json').read_text())
SOURCES={r['id']:r for r in MANIFEST}
PAGE_MAP={r['id']:r for r in PAGES}
app=FastAPI(title='MPS Growth · 의료진 검토 워크스페이스',docs_url=None,redoc_url=None)

app.mount('/frontend',StaticFiles(directory=ROOT/'frontend'),name='frontend')

ACCESS=WebAccess.from_env()

@app.middleware('http')
async def access_control(request: Request, call_next):
    blocked=ACCESS.check(request)
    response=blocked if blocked is not None else await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    if ACCESS.production and request.url.scheme=='https':
        response.headers['Strict-Transport-Security']='max-age=31536000'
    return response

@app.get('/healthz')
def health():return {'status':'ok'}

class Patient(BaseModel):
    code: str=Field(default='',max_length=60)
    name: str=Field(default='',max_length=60)
    visit_number: int=Field(default=1,ge=1,le=99)
    intake_memo: str=Field(default='',max_length=16000)
    father_height: Optional[float]=Field(default=None,ge=100,le=230,allow_inf_nan=False)
    mother_height: Optional[float]=Field(default=None,ge=100,le=230,allow_inf_nan=False)
    body_fat: Optional[float]=Field(default=None,ge=0,le=100,allow_inf_nan=False)
    ecw_ratio: Optional[float]=Field(default=None,ge=0,le=1,allow_inf_nan=False)
    previous_bone_age_months: Optional[int]=Field(default=None,ge=0,le=240)
    previous_stage: str=Field(default='',max_length=100)
    previous_predicted_height: Optional[float]=Field(default=None,ge=40,le=250,allow_inf_nan=False)
    sex: Literal[1,2]
    birth: date
    exam: date
    height: float=Field(ge=40,le=230,allow_inf_nan=False)
    weight: Optional[float]=Field(default=None,ge=1,le=250,allow_inf_nan=False)
    bone_age: Optional[float]=Field(default=None,ge=0,le=20,allow_inf_nan=False)
    bone_method: str=Field(default='',max_length=100)
    previous_height: Optional[float]=Field(default=None,ge=40,le=230,allow_inf_nan=False)
    previous_date: Optional[date]=None
    observations: str=Field(default='',max_length=12000)
    growth_history_text: str=Field(default='',max_length=4000)
    question: str=Field(default='',max_length=2000)
    use_ai: bool=False
    consent: bool=False

    @model_validator(mode='after')
    def dates(self):
        if self.birth>self.exam or self.exam>date.today():raise ValueError('생년월일·검사일의 순서를 확인해주세요. 미래 검사일은 사용할 수 없습니다.')
        if self.previous_date and not self.birth<=self.previous_date<self.exam:raise ValueError('이전 측정일은 생일 이후, 검사일 이전이어야 합니다.')
        if (self.previous_height is None)!=(self.previous_date is None):raise ValueError('이전 신장과 측정일을 함께 입력해주세요.')
        if self.bone_age is not None and not self.bone_method.strip():raise ValueError('골연령을 입력하면 판독 방법·출처도 입력해주세요.')
        compute_history(self.growth_history_text,self.birth,self.exam,self.height)
        return self

def age_months(birth,exam):
    return (exam.year-birth.year)*12+exam.month-birth.month-(exam.day<birth.day)

def table_comparison(sheet,sex,months,value):
    table=GROWTH[sheet]
    candidates=[r for r in table['rows'] if r['sex']==sex and r['months']==months]
    if len(candidates)!=1:return dict(available=False,reason='해당 월령의 단일 기준행이 없어 계산하지 않았습니다.')
    r=candidates[0]; pairs=[(p,v) for p,v in zip(table['percentiles'],r['values']) if isinstance(v,(float,int))]
    if value<pairs[0][1]:band=f'{pairs[0][0]}백분위 미만'
    elif value>pairs[-1][1]:band=f'{pairs[-1][0]}백분위 초과'
    else:
        exact=[p for p,v in pairs if v==value]
        if exact:band=f'{exact[0]}백분위 표 값과 일치'
        else:
            lo=max((p for p,v in pairs if v<value));hi=min(p for p,v in pairs if v>value)
            band=f'{lo}–{hi}백분위 구간'
    return dict(available=True,band=band,median=r['values'][6],source=table['source'],sheet=sheet,row=r['row'],months=months,method='검사일 기준 완료 월령의 표 값을 직접 비교. 백분위 보간·골성숙도 추정 없음.')

def calculate(p):
    months=age_months(p.birth,p.exam)
    result=dict(months=months,age=f'{months//12}세 {months%12}개월',height=table_comparison('연령별 신장',p.sex,months,p.height),bmi=None,velocity=None,bone_difference=None)
    if p.weight:
        bmi=p.weight/(p.height/100)**2
        result['bmi']=dict(value=round(bmi,2),comparison=table_comparison('연령별 체질량지수',p.sex,months,bmi))
    if p.previous_date:
        days=(p.exam-p.previous_date).days
        result['velocity']=dict(value=round((p.height-p.previous_height)*365.2425/days,2),days=days,change=round(p.height-p.previous_height,2),note='두 측정치 차이의 연환산 값. 짧은 측정 간격·측정 오차를 검토하세요.')
    if p.bone_age is not None:
        age=(p.exam-p.birth).days/365.2425
        result['bone_difference']=dict(value=round(p.bone_age-age,2),method=p.bone_method,note='입력된 판독 골연령 − 역연령. 성숙군 분류 기준으로 자동 사용하지 않음.')
    history=compute_history(p.growth_history_text,p.birth,p.exam,p.height)
    if history:
        result['history']=history
        if history['overall']:result['velocity']=history['overall']
    return result

def search_pages(query,limit=12):
    terms=set(re.findall(r'[a-z0-9가-힣]{2,}',query.lower()))
    if not terms:terms={'초음파','골단','성장','maturity','ultrasound'}
    scored=[]
    for p in PAGES:
        if not p['readable']:continue
        text=p['text'].lower()
        score=sum(min(text.count(t),5)*(2 if len(t)>3 else 1) for t in terms)
        if score:scored.append((score,p))
    scored.sort(key=lambda x:x[0],reverse=True)
    # Diversify by document; keep exact, unabridged source pages.
    selected=[]; counts={}
    for _,p in scored:
        if counts.get(p['source'],0)>=4:continue
        selected.append(p);counts[p['source']]=counts.get(p['source'],0)+1
        if len(selected)>=limit:break
    return selected

def source_view(p):
    return dict(id=p['id'],source=p['source'],name=SOURCES[p['source']]['name'],page=p['page'],excerpt=p['text'][:700],url=f'api/sources/{p["source"]}#page={p["page"]}')

@app.get('/')
def index():return FileResponse(ROOT/'index.html')
@app.get('/workspace.css')
def workspace_css():return FileResponse(ROOT/'frontend/css/workspace.css')
@app.get('/mps-symbol.png')
def mps_logo():return FileResponse(ROOT/'frontend/assets/mps-symbol.png')
@app.get('/clinical-report.js')
def report_js():return FileResponse(ROOT/'frontend/js/clinical-report.js')
@app.get('/memo-parser.js')
def memo_js():return FileResponse(ROOT/'frontend/js/memo-parser.js')
@app.get('/app.js')
def js():return FileResponse(ROOT/'frontend/js/app.js')
@app.get('/styles.css')
def css():return FileResponse(ROOT/'frontend/css/styles.css')
@app.get('/api/status')
def status():return dict(hosted=ACCESS.production,ai_configured=bool(os.getenv('OPENAI_API_KEY')),model=os.getenv('OPENAI_MODEL','gpt-4.1'),source_count=len(MANIFEST),page_count=len(PAGES),text_pages=sum(p['readable'] for p in PAGES))
@app.get('/api/library')
def library():return MANIFEST
@app.get('/api/sources/{sid}')
def source(sid:str):
    if sid not in SOURCES:raise HTTPException(404,'근거 파일을 찾을 수 없습니다.')
    return FileResponse(ROOT/'data/sources'/SOURCES[sid]['name'])
@app.get('/api/search')
def search(q:str='초음파 골단 성장'):return [source_view(p) for p in search_pages(q)]
@app.get('/api/chart')
def chart(sex:int=1):
    if sex not in (1,2):raise HTTPException(422,'성별 값 오류')
    t=GROWTH['연령별 신장']
    return dict(source=t['source'],sheet=t['sheet'],rows=[dict(months=r['months'],p3=r['values'][1],p50=r['values'][6],p97=r['values'][11]) for r in t['rows'] if r['sex']==sex and r['months']>=36])

GROUPS={'ulna':'척골','radius':'요골','femur':'대퇴골 원위부','extra':'추가자료'}

def validate_groups(files,groups):
    if len(groups)!=len(files) or any(g not in GROUPS for g in groups):raise HTTPException(422,'파일과 검사 부위 정보가 일치하지 않습니다.')
    if len(files)>25:raise HTTPException(422,'전체 자료는 최대 25개입니다.')
    for group in GROUPS:
        if groups.count(group)>(10 if group=='extra' else 5):raise HTTPException(422,f'{GROUPS[group]} 자료 수를 줄여주세요. 부위별 5장, 추가자료 10개까지 가능합니다.')
    for f,group in zip(files,groups):
        if group!='extra' and Path(f.filename or '').suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:raise HTTPException(422,'초음파 부위에는 이미지 파일만 넣어주세요. PDF는 추가자료에 넣을 수 있습니다.')

async def parse_files(files,groups=None):
    content=[]; summary=[]; total=0; visual_count=0
    groups=groups if groups is not None else ['extra']*len(files)
    validate_groups(files,groups)
    for file_index,(f,group) in enumerate(zip(files,groups),1):
        file_id=f'F{file_index:02d}'
        before_visual=visual_count
        raw=await f.read(15*1024*1024+1);total+=len(raw)
        if len(raw)>15*1024*1024 or total>120*1024*1024:raise HTTPException(413,'파일당 15MB, 전체 120MB 이하로 올려주세요.')
        ext=Path(f.filename or '').suffix.lower(); name=Path(f.filename or '자료').name
        content.append(dict(type='input_text',text=f'PATIENT_FILE {file_id} | group={group} | 부위: {GROUPS[group]} | 파일명: {name} | 현재 검사 자료'))
        try:
            if ext=='.pdf':
                d=fitz.open(stream=raw,filetype='pdf')
                if d.needs_pass:raise ValueError('암호화 PDF는 지원하지 않습니다.')
                if len(d)>40:raise ValueError('검진 PDF는 40페이지 이하로 나누어 올려주세요.')
                texts=[];scans=0
                for n,page in enumerate(d,1):
                    t=page.get_text();texts.append(f'검진파일 {name} p.{n}\n{t}')
                    if len(t.strip())<60 or page.get_images():
                        scans+=1;visual_count+=1
                        if visual_count>30:raise ValueError('이미지·스캔 페이지 합계는 30개 이하로 나누어 올려주세요.')
                        pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2))
                        content.extend([dict(type='input_text',text=f'검진파일 {name} p.{n}. 현재 검진 페이지입니다. 보이는 구조와 계측 표기를 참고영상과 비교하고, 불명확하면 판독 한계를 명시하세요.'),dict(type='input_image',image_url='data:image/png;base64,'+base64.b64encode(pix.tobytes('png')).decode(),detail='high')])
                text='\n'.join(texts)
                if len(text)>80000:raise ValueError('검진 PDF 텍스트가 너무 많습니다. 필요한 부분만 올려주세요.')
                content.append(dict(type='input_text',text=text)); summary.append(dict(name=name,detail=f'{len(d)}페이지 · 스캔 {scans}페이지'))
            elif ext in {'.png','.jpg','.jpeg','.webp'}:
                # Validate format and bound decoded dimensions; strip EXIF by rendering.
                d=fitz.open(stream=raw)
                page=d[0]
                if page.rect.width*page.rect.height>40_000_000:raise ValueError('이미지 해상도를 줄여주세요.')
                scale=min(1,1800/max(page.rect.width,page.rect.height))
                pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale))
                visual_count+=1
                if visual_count>30:raise ValueError('이미지·스캔 페이지 합계는 최대 30개입니다.')
                content.extend([dict(type='input_text',text=f'검진파일 {name}: 현재 환자 영상입니다. 부위와 영상 적합성을 먼저 확인하고 참고영상과 대조해 형태를 관찰하세요. 관찰 불가능한 구조·수치를 지어내지 마세요.'),dict(type='input_image',image_url='data:image/png;base64,'+base64.b64encode(pix.tobytes('png')).decode(),detail='high')])
                summary.append(dict(name=name,detail='이미지 · AI 영상 비교 대상'))
            elif ext=='.txt':
                text=raw.decode('utf-8-sig')
                if len(text)>30000:raise ValueError('텍스트는 30,000자 이하로 올려주세요.')
                content.append(dict(type='input_text',text=f'검진파일 {name}\n{text}'));summary.append(dict(name=name,detail='텍스트 기록'))
            else:raise ValueError('검진자료는 PDF, JPG, PNG, WEBP, TXT를 지원합니다.')
            summary[-1].update(id=file_id,group=group,group_label=GROUPS[group],visual=visual_count>before_visual)
        except HTTPException:raise
        except Exception as e:raise HTTPException(422,f'{name}: 파일을 읽지 못했습니다. {str(e)[:160]}')
    return content,summary

class Finding(BaseModel):
    title:str
    assessment:str
    source_id:str
    quote:str
    limitation:str
class AIResult(BaseModel):
    summary:str
    extracted_records:list[str]
    findings:list[Finding]
    missing:list[str]
    review_questions:list[str]

def normalize(s):return re.sub(r'\s+','',s).lower()

def verify_findings(result,selected):
    allowed={p['id']:p for p in selected};valid=[];rejected=0
    for finding in result.findings:
        p=allowed.get(finding.source_id)
        if not p or len(normalize(finding.quote))<12 or normalize(finding.quote) not in normalize(p['text']):rejected+=1;continue
        item=finding.model_dump();item['source']=source_view(p);valid.append(item)
    return valid,rejected

def ai_patient_context(p,metrics):
    memo='\n'.join(line for line in p.intake_memo.splitlines() if not re.match(r'^\s*(이름|성명|생년월일|대상자\s*코드)\s*[:：]',line))
    if p.name:memo=memo.replace(p.name,'[이름 제외]')
    return dict(age=metrics['age'],sex=p.sex,height=p.height,weight=p.weight,bone_age=p.bone_age,bone_method=p.bone_method,visit_number=p.visit_number,father_height=p.father_height,mother_height=p.mother_height,body_fat=p.body_fat,ecw_ratio=p.ecw_ratio,previous_visit=dict(bone_age_months=p.previous_bone_age_months,stage=p.previous_stage,predicted_height=p.previous_predicted_height),pasted_memo=memo,observations=p.observations,question=p.question,calculations=metrics)

def ai_failure_message(response):
    """Expose actionable limits, never the provider's raw message or identifiers."""
    prefix=f'AI 영상 판독 요청 실패 (HTTP {response.status_code}): '
    if response.status_code!=429:
        return prefix+{401:'API 키 인증 실패',403:'모델 접근 권한 확인 필요',413:'요청 이미지 용량 초과'}.get(response.status_code,'모델·연결 상태를 확인해주세요.')
    try:
        error=response.json().get('error',{})
        if not isinstance(error,dict):error={}
    except (ValueError,AttributeError):error={}
    code=error.get('code'); kind=error.get('type')
    if code=='insufficient_quota' or kind=='insufficient_quota':
        return prefix+'API 크레딧 또는 지출 한도 부족 (insufficient_quota). OpenAI API의 Billing과 프로젝트 사용 한도를 확인하세요. 반복 요청으로 해결되지 않습니다.'
    message=str(error.get('message',''))
    counts={label:int(match.group(1).replace(',','')) for label in ('Limit','Requested','Used') if (match:=re.search(r'\b'+label+r'\s*:?\s*([\d,]+)',message,re.I))}
    if code=='rate_limit_exceeded' or kind=='rate_limit_error' or code=='slow_down':
        detail='요청량 제한 (rate_limit_exceeded). '
        if counts.get('Requested',0)>counts.get('Limit',float('inf')):
            detail+='한 번의 요청이 허용량을 초과했습니다. 기다려도 같은 요청은 실패할 수 있습니다. 모델 사용 한도 상향 또는 자료를 나누어 처리하는 구성이 필요합니다. '
        else:
            detail+='잠시 기다린 뒤 다시 실행하세요. 반복되면 OpenAI API의 모델별 Limits를 확인하세요. '
        if counts:detail+=' / '.join(f'{label} {value:,}' for label,value in counts.items())+'. '
        headers=getattr(response,'headers',{})
        limit=str(headers.get('x-ratelimit-limit-tokens',''))
        if limit.isdigit():detail+=f'분당 토큰 한도 {int(limit):,}. '
        return prefix+detail
    return prefix+'429 응답의 상세 원인을 확인할 수 없습니다. API Billing과 모델별 Limits를 확인하세요. 결제 부족으로 단정할 수 없습니다.'

async def ask_ai(p,metrics,selected,attachments,file_summary=None):
    started=time.perf_counter()
    key=os.getenv('OPENAI_API_KEY')
    if not key:raise HTTPException(503,'AI 연결 전입니다. 서버 .env에 OPENAI_API_KEY를 설정하고 다시 시작하세요.')
    if not p.consent:raise HTTPException(422,'AI 영상 판독 요청에는 자료의 OpenAI 전송 확인이 필요합니다.')
    selected,visual=select_references(PAGES,p.sex,selected)
    file_summary=file_summary or []
    context=ai_patient_context(p,metrics)
    reference_content=render_references(selected,visual,SOURCES,ROOT)
    # Static source prefix first permits provider prompt caching across evaluations.
    # Visual pages retain their full images; avoid also sending duplicate OCR text.
    reference_pages=[{**page,'text':'' if page['id'] in visual else page['text'],
        'filename':SOURCES[page['source']]['name'],'category':SOURCES[page['source']]['category']} for page in selected]
    content=[dict(type='input_text',text=json.dumps(dict(reference_pages=reference_pages),ensure_ascii=False,separators=(',',':')))]+reference_content
    content += [dict(type='input_text',text=json.dumps(dict(patient=context,files=file_summary),ensure_ascii=False,separators=(',',':')))]+attachments
    try:
        async with httpx.AsyncClient(timeout=240) as client:
            response=await client.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}'},json=dict(model=os.getenv('OPENAI_MODEL','gpt-4.1'),store=False,instructions=PROMPT,input=[dict(role='user',content=content)],text={'format':{'type':'json_schema','name':'growth_image_report','strict':True,'schema':strict_schema()}},max_output_tokens=8000))
        if response.status_code!=200:
            raise HTTPException(502,ai_failure_message(response))
        payload=response.json()
        elapsed=round(time.perf_counter()-started,2)
        if payload.get('status')!='completed':raise HTTPException(502,'AI 판독 응답이 완료되지 않았습니다. 파일 수를 줄여 다시 시도해주세요.')
        output=''.join(c.get('text','') for item in payload.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
        if not output:raise HTTPException(502,'AI가 판독 보고서를 반환하지 않았습니다. 영상과 요청 내용을 확인해주세요.')
        clinical=ClinicalReport.model_validate_json(output)
        report,rejected,warnings=validate_report(clinical,selected,visual,file_summary,source_view)
        return dict(duration_seconds=elapsed,usage={k:payload.get('usage',{}).get(k,0) for k in ['input_tokens','output_tokens','total_tokens']},cached_tokens=payload.get('usage',{}).get('input_tokens_details',{}).get('cached_tokens',0),clinical_report=report,rejected_citations=rejected,model=os.getenv('OPENAI_MODEL','gpt-4.1'),reference_images=len(reference_content)//2,patient_images=sum(f.get('visual',False) for f in file_summary),analysis_passes=1,sources=[source_view(s) for s in selected],notice='AI 영상 비교 판독 초안입니다. 임상 정확도는 검증되지 않았으며 의료진의 원본 대조와 최종 판독이 필요합니다. 수치 범위는 검증된 신뢰구간이 아닙니다.')
    except HTTPException:raise
    except httpx.TimeoutException:raise HTTPException(504,'영상 판독 시간이 초과되었습니다. 파일 수를 줄여 다시 시도해주세요.')
    except (httpx.HTTPError,ValidationError,ValueError):raise HTTPException(502,'AI 연결 또는 판독 보고서 형식 오류입니다. 다시 시도해주세요.')

@app.post('/api/preview')
def preview(patient:Patient):
    return dict(metrics=calculate(patient))

@app.post('/api/evaluate')
async def evaluate(patient:str=Form(...),files:list[UploadFile]=File(default=[]),file_groups:str=Form(default='')):
    try:p=Patient.model_validate_json(patient)
    except (ValidationError,ValueError) as e:raise HTTPException(422,'입력값을 확인해주세요. '+str(e).split('\n')[1][:220])
    try:groups=json.loads(file_groups) if file_groups else ['extra']*len(files)
    except (ValueError,TypeError):raise HTTPException(422,'검사 부위 정보를 읽을 수 없습니다.')
    if not isinstance(groups,list) or any(not isinstance(g,str) for g in groups):raise HTTPException(422,'검사 부위 정보 형식이 올바르지 않습니다.')
    attachments,file_summary=await parse_files(files,groups)
    metrics=calculate(p);selected=search_pages('초음파 골단 성장 maturity ultrasound '+p.observations+' '+p.question+' '+p.bone_method)
    result=dict(patient=p.model_dump(mode='json',exclude={'consent'}),metrics=metrics,files=file_summary,sources=[source_view(s) for s in selected],ai=None,ai_error=None,banding='판단 보류 · AI 영상 판독 미실행',created=date.today().isoformat(),coverage=dict(total=411,searchable=268))
    if p.use_ai:
        try:result['ai']=await ask_ai(p,metrics,selected,attachments,file_summary)
        except HTTPException as e:result['ai_error']=e.detail
    if result['ai']:
        result['sources']=result['ai']['sources']
        result['banding']=result['ai']['clinical_report']['phv']['label']
    return result
