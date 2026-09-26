'use strict';
const BudgetUI=(()=>{
 let api,state;
 const money=value=>Number(value).toLocaleString('ko-KR')+'원';
 function render(){
  const panel=document.querySelector('#budget-panel');if(!panel)return;
  if(state?.center_only){
   const c=state.usage.centers[0];panel.replaceChildren();
   const title=document.createElement('strong');title.textContent=c?.name||'센터 사용 현황';panel.append(title);
   const info=document.createElement('p');info.textContent=state.usage.month+' · 판독 완료 '+(c?.completed_interpretations||0)+'회 · 결과지 읽기 완료 '+(c?.completed_extractions||0)+'회';panel.append(info);
   const note=document.createElement('p');note.textContent='추가 사용 예산은 MPS 본부에서 승인합니다. 재판독은 별도로 집계됩니다.';const details=document.createElement('details');details.innerHTML='<summary>안내</summary>';details.append(note);panel.append(details);return;
  }
  if(!state?.enabled){panel.innerHTML='<strong>월 예산 관리</strong><p>비용 관리 저장소가 아직 연결되지 않았습니다. 사용액을 0원으로 간주하지 마세요.</p>';return;}
  panel.innerHTML='<h2>이번 달 예산</h2><p data-budget-total></p><p data-budget-breakdown></p><p data-budget-warning role="status"></p>'+
   '<details><summary>추가 사용 여부 결정</summary><p>예산을 늘려도 판독이 자동 실행되지는 않습니다. 보류하려면 금액을 변경하지 않으면 됩니다. 기존 자료는 삭제하지 않습니다.</p>'+
   '<label>이번 달 총 예산 (원) <input id="budget-new-limit" type="number" min="1" max="1000000" step="1000"></label>'+
   '<button type="button" class="button secondary" id="budget-approve">입력한 총 예산 승인</button><p id="budget-action-status" role="status"></p></details>'+
   '<p class="chart-note" data-budget-notice></p>';
  panel.querySelector('[data-budget-total]').textContent=state.month+' · 추정 합계 '+money(state.estimated_total_krw)+' / 승인 예산 '+money(state.limit_krw);
  panel.querySelector('[data-budget-breakdown]').textContent='AI '+money(state.ai_estimated_krw)+' · 처리 중/확인 대기 예비금 '+money(state.pending_krw)+' · 서버·저장소 월 예비비 '+money(state.overhead_estimated_krw);
  panel.querySelector('[data-budget-warning]').textContent=({normal:'예산 범위 안입니다.',notice:'예산의 70% 이상입니다. 이번 달 추가 사용량을 확인해주세요.',warning:'예산의 90% 이상입니다. 추가 예산 또는 새 판독 보류를 결정해주세요.',decision:'추가 사용 여부를 결정해주세요.'})[state.level];
  panel.querySelector('[data-budget-notice]').textContent=state.notice+' 환산 기준: 1달러 '+state.usd_krw+'원, 세금 계수 '+state.tax_multiplier+'. 예비금에는 실패·시간초과로 사용량을 확인하지 못한 요청도 포함됩니다. 앱 밖에서는 알림을 보내지 않습니다.';
  if(panel.classList.contains('budget-notice')){const details=panel.querySelector('details');details.querySelector('summary').textContent='상세 · 예산 관리';details.prepend(panel.querySelector('[data-budget-breakdown]'));details.append(panel.querySelector('[data-budget-notice]'));}
  const input=panel.querySelector('#budget-new-limit');input.value=state.limit_krw;
  panel.querySelector('#budget-approve').onclick=async()=>{
   const output=panel.querySelector('#budget-action-status'),amount=Number(input.value);
   if(!Number.isInteger(amount)||amount<=state.limit_krw||amount>1000000){output.textContent='현재 예산보다 큰 총액을 입력해주세요. 최대 100만 원입니다.';return;}
   const button=panel.querySelector('#budget-approve');button.disabled=true;
   try{
    state=await api('api/budget/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({month:state.month,expected_limit_krw:state.limit_krw,new_limit_krw:amount})});
    render();panel.querySelector('#budget-action-status').textContent='이번 달 총 예산 '+money(amount)+'을 승인했습니다. 원하실 때 판독을 다시 요청해주세요.';
   }catch(error){output.textContent=error.message;button.disabled=false;}
  };
 }
 async function refresh(){
  try{state=await api('api/budget');render();}
  catch{const panel=document.querySelector('#budget-panel');if(panel)panel.textContent='현재 비용을 확인하지 못했습니다. 연결을 확인해주세요.';}
 }
 function decision(detail){
  if(!detail?.budget)return;
  state=detail.budget;render();
  const panel=document.querySelector('#budget-panel');
  panel.querySelector('[data-budget-warning]').textContent='이번 요청 예비비 '+money(detail.request_allowance_krw)+'가 남은 예산을 넘습니다. 총 예산을 늘리거나 요청을 보류해주세요.';
  panel.querySelector('details').open=true;
  panel.scrollIntoView({behavior:'smooth',block:'center'});
 }
 return {init(fn){api=fn;refresh();},refresh,decision};
})();
