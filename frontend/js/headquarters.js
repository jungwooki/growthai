'use strict';
let usage=null;
const month=document.querySelector('#month'),status=document.querySelector('#status');
month.value=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit'}).format(new Date());
async function api(path,options){const response=await fetch('/'+path.replace(/^\//,''),options);const data=await response.json();if(!response.ok){if(response.status===401)location.assign('/?login=required');throw new Error(typeof data.detail==='string'?data.detail:'연결을 확인해주세요.');}return data;}
function cell(row,value){const el=document.createElement('td');el.textContent=value;row.append(el);}
const count=n=>Number(n).toLocaleString('ko-KR');
async function refresh(){
 document.querySelector('#download').disabled=true;usage=null;status.textContent='사용 현황을 불러오는 중…';
 document.querySelector('#totals').innerHTML='<div class="metric">등록·집계 센터<strong>—</strong></div><div class="metric">판독 완료<strong>—</strong></div><div class="metric">AI 비용 추정<strong>—</strong></div>';
 for(const id of ['center-rows','region-rows'])document.getElementById(id).replaceChildren();
 try{
  const data=await api('api/usage/monthly?month='+encodeURIComponent(month.value));usage=data;
  for(const c of data.centers){const row=document.createElement('tr');[c.region,c.name,count(c.completed_extractions),count(c.completed_interpretations),count(c.extraction_calls+c.interpretation_calls),count(c.pending_calls),count(c.ai_estimated_krw)+'원'].forEach(v=>cell(row,v));document.querySelector('#center-rows').append(row);}
  for(const c of data.regions){const row=document.createElement('tr');[c.region,count(c.completed_interpretations),count(c.extraction_calls+c.interpretation_calls),count(c.ai_estimated_krw)+'원'].forEach(v=>cell(row,v));document.querySelector('#region-rows').append(row);}
  document.querySelector('#totals').replaceChildren();
  const totals=[['등록·집계 센터',data.centers.length+'곳'],['판독 완료',count(data.centers.reduce((n,c)=>n+c.completed_interpretations,0))+'회'],['AI 비용 추정',count(data.centers.reduce((n,c)=>n+c.ai_estimated_krw,0))+'원']];
  for(const [label,value] of totals){const card=document.createElement('div');card.className='metric';card.textContent=label;const strong=document.createElement('strong');strong.textContent=value;card.append(strong);document.querySelector('#totals').append(card);}
  document.querySelector('#usage-notice').textContent=data.notice;status.textContent=data.month+' · 한국 시간 기준';document.querySelector('#download').disabled=false;
 }catch(error){status.textContent=error.message;}
}
document.querySelector('#refresh').onclick=refresh;
document.querySelector('#logout').onclick=async()=>{await api('api/auth/logout',{method:'POST'});location.assign('/?logged_out=1');};
document.querySelector('#download').onclick=()=>{
 if(!usage)return;
 const safe=v=>'"'+String(v).replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';
 const rows=[['월','지역','센터','결과지 읽기 완료','판독 완료','전체 AI 요청','사용량 확인 대기','AI 추정 원']];
 for(const c of usage.centers)rows.push([usage.month,c.region,c.name,c.completed_extractions,c.completed_interpretations,c.extraction_calls+c.interpretation_calls,c.pending_calls,c.ai_estimated_krw]);
 const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.map(r=>r.map(safe).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='MPS-GrowthAI-'+usage.month+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
if(location.protocol==='file:'){status.textContent='디자인 미리보기 · 실제 사용량은 운영 서버에서 본부 로그인 후 확인할 수 있습니다.';document.querySelector('#refresh').disabled=true;document.querySelector('#logout').disabled=true;}else{refresh();BudgetUI.init(api);}
