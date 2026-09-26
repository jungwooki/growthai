'use strict';
// Keep clinical data in this page's memory only; never localStorage.
const ResultReview=(()=>{
 let state=null, entries=[], urls=[];
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const same=files=>files.length===entries.length&&files.every((e,i)=>e.file===entries[i].file&&e.group===entries[i].group);
 function release(){urls.forEach(u=>URL.revokeObjectURL(u));urls=[];}
 function reset(){release();state=null;entries=[];}
 function start(extraction,files){reset();entries=files.map(e=>({...e}));state={original:structuredClone(extraction),review:null};}
 function current(files){if(state&&!same(files))reset();return state;}
 function payload(files){return current(files)?.review||null;}
 function audit(files){const s=current(files);return s?structuredClone(s):null;}
 function render(container,files,onConfirm,onReadAgain){
  const s=current(files);if(!s)return;release();
  const docs=s.review?.documents||s.original.documents;
  container.innerHTML='<h2>검사 결과지 숫자 확인</h2><p>초음파 판독 전 단계입니다. 원본과 대조하여 숫자·단위·검사일을 수정하세요. 확인이 어려운 항목은 포함을 해제하세요. 직접 입력한 신장·체중은 자동으로 덮어쓰지 않습니다.</p>';
  const panel=document.createElement('div');panel.className='record-review';
  panel.innerHTML=docs.map((doc,di)=>{
   const entry=files[Number(doc.file_id.slice(1))-1],url=URL.createObjectURL(entry.file);urls.push(url);
   return '<section class="report-section"><h3>'+escape(entry.file.name)+'</h3><a href="'+url+'" target="_blank" rel="noopener">원본 열기 · 대조</a>'+
    doc.warnings.map(w=>'<p class="limitation">'+escape(w)+'</p>').join('')+
    (!doc.measurements.length?'<p class="error">읽은 수치가 없습니다. 원본을 확인하고 필요한 항목을 추가하세요.</p>':'')+
    '<div style="overflow:auto"><table><thead><tr><th>포함</th><th>항목</th><th>원래 읽은 값</th><th>확인한 값</th><th>단위</th><th>검사일</th><th>위치·참고범위·주의</th></tr></thead><tbody data-doc="'+di+'">'+
    doc.measurements.map((row,ri)=>rowHTML(row,di,ri,s.original.documents[di]?.measurements[ri])).join('')+
    '</tbody></table></div><button type="button" data-add-row="'+di+'" class="button secondary">누락 항목 추가</button></section>';
  }).join('')+
   '<label><input type="checkbox" id="records-confirmed"> 포함한 수치를 원본과 대조했습니다. 제외한 값은 판독에 사용하지 않습니다.</label>'+
   '<p role="alert" id="records-error" class="error" hidden></p>'+
   '<div class="report-actions"><button type="button" class="button primary" id="records-continue">확인한 수치로 초음파·종합 판독</button>'+
   '<button type="button" class="button secondary" id="records-reread">결과지 다시 읽기</button></div>'+
   '<p class="chart-note">확인값은 이 화면에서 재사용됩니다. 새 검사·새로고침 시 초기화됩니다. 완료 보고서 JSON에는 읽은 값과 수정값을 함께 보관합니다.</p>';
  container.append(panel);
  panel.querySelectorAll('[data-add-row]').forEach(button=>button.onclick=()=>{
   const body=panel.querySelector('[data-doc="'+button.dataset.addRow+'"]'),ri=body.children.length;
   body.insertAdjacentHTML('beforeend',rowHTML({item:'',value:'',unit:'',exam_date:'',location:'',reference:'',note:'의료진 직접 전사',status:'needs_review'},Number(button.dataset.addRow),ri));
  });
  panel.querySelector('#records-reread').onclick=()=>{reset();onReadAgain();};
  panel.querySelector('#records-continue').onclick=()=>{
   const error=panel.querySelector('#records-error');
   if(!panel.querySelector('#records-confirmed').checked){error.textContent='원본 대조 확인란을 선택해주세요.';error.hidden=false;return;}
   const documents=docs.map((doc,di)=>({...doc,measurements:[...panel.querySelector('[data-doc="'+di+'"]').children].map((tr,ri)=>{
    const original=doc.measurements[ri]||{item:'',value:null,unit:'',exam_date:'',location:'',reference:'',note:'의료진 직접 전사',status:'needs_review'};
    const row={...original,include:tr.querySelector('[data-field="include"]').checked};
    for(const key of ['item','value','unit','exam_date','location'])row[key]=tr.querySelector('[data-field="'+key+'"]').value.trim();
    row.status=row.include?'read':original.status;
    return row;
   })}));
   if(documents.some(d=>d.measurements.some(row=>!row.item||(row.include&&!row.value)))){
    error.textContent='항목명을 입력하고, 포함할 항목의 값을 확인해주세요. 읽지 못한 값은 포함을 해제하세요.';error.hidden=false;return;
   }
   s.review={confirmed:true,fingerprints:s.original.fingerprints,documents};release();onConfirm();
  };
 }
 function rowHTML(row,di,ri,original){
  const text=(key,max)=>'<input aria-label="'+escape(row.item||'추가 항목')+' '+key+'" data-field="'+key+'" value="'+escape(row[key])+'" maxlength="'+max+'" style="min-width:90px;width:100%">';
  return '<tr><td><input type="checkbox" aria-label="'+escape(row.item||'추가 항목')+' 포함" data-field="include" '+((row.include??row.status==='read')?'checked':'')+'></td>'+
   '<td>'+text('item',160)+'</td><td>'+escape(original?(original.value??'읽기 불명확'):(row.value??'읽기 불명확'))+(row.status==='needs_review'?'<br><strong>확인 필요</strong>':'')+'</td>'+
   '<td>'+text('value',100)+'</td><td>'+text('unit',60)+'</td><td>'+text('exam_date',40)+'</td><td>'+text('location',160)+
   '<small>'+escape(row.reference)+' '+escape(row.note)+'</small></td></tr>';
 }
 return {reset,start,current,payload,audit,render};
})();
