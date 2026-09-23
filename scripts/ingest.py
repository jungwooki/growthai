"""Import only explicitly supplied reference files; never patient archives."""
from pathlib import Path
import sys, shutil, json, hashlib
import fitz, openpyxl
ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv)>1 else Path('/Users/jungwooklee/내 드라이브(jungwookii@gmail.com)/[MPS] - 개발팀/S-TEST/S 초음파 학습근거')
dest = ROOT/'data/sources'; dest.mkdir(parents=True, exist_ok=True)
manifest=[]; pages=[]; growth={}
for i,f in enumerate(sorted(p for p in SOURCE.iterdir() if p.suffix.lower() in {'.pdf','.ppt','.xlsx','.jpeg','.png'}),1):
 sid=f'R{i:02d}'; target=dest/f.name
 if f.resolve()!=target.resolve(): shutil.copy2(f,target)
 entry=dict(id=sid,name=f.name,size=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),kind=f.suffix[1:],pages=0,text_pages=0)
 entry['category'] = ('논문·특허 합본' if f.name.startswith('01 ') else '강의·사례 자료' if f.name.startswith('02 ') else '연구 제안 발표자료' if f.name.startswith('03') else '성장도표 기준 데이터' if f.suffix=='.xlsx' else '골성숙도 교육자료' if f.name.startswith('08.') else '한국인 골연령 연구논문' if f.name.startswith('09.') else '참고 이미지')
 if f.suffix=='.pdf':
  doc=fitz.open(f);entry['pages']=len(doc)
  for n,p in enumerate(doc,1):
   t=p.get_text().strip(); readable=len(t)>60
   entry['text_pages']+=int(readable)
   pages.append(dict(id=f'{sid}:p{n}',source=sid,page=n,text=t,readable=readable))
 elif f.suffix=='.xlsx':
  w=openpyxl.load_workbook(f,data_only=True)
  for title in ['연령별 신장','연령별 체중','연령별 체질량지수']:
   s=w[title]; rows=[]
   for n,r in enumerate(s.values,1):
    if n<3 or r[0] not in (1,2) or not isinstance(r[2],(int,float)):continue
    rows.append(dict(sex=r[0],months=r[2],L=r[3],M=r[4],S=r[5],values=list(r[6:19]),row=n))
   growth[title]=dict(source=sid,sheet=title,percentiles=[1,3,5,10,15,25,50,75,85,90,95,97,99],rows=rows)
  entry['sheets']=w.sheetnames
 elif f.suffix=='.ppt':entry['note']='동명 PDF를 검색·분석에 사용. PPT 원본은 보관.'
 else:entry['note']='참고 이미지 · 자동 검색용 텍스트 없음'
 manifest.append(entry)
for name,data in [('manifest',manifest),('pages',pages),('growth',growth)]:
 (ROOT/f'data/{name}.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
print(f'{len(manifest)} files, {len(pages)} PDF pages, {sum(p["readable"] for p in pages)} searchable pages')
