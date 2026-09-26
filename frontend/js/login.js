'use strict';
const form=document.querySelector('#login-form');
const password=document.querySelector('#password');
const toggle=document.querySelector('#toggle-password');
const button=document.querySelector('#login-button');
const error=document.querySelector('#login-error');
const notice=document.querySelector('#login-notice');
const dialog=document.querySelector('#login-dialog');
function openLogin(){if(!dialog.open)dialog.showModal();}
document.querySelectorAll('[data-open-login]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();openLogin();}));
document.querySelector('#close-login').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
const query=new URLSearchParams(location.search);
if(query.has('login')||query.has('logged_out')||location.hash==='#login')openLogin();
if(query.has('login')){notice.textContent='로그인 후 성장 평가를 이용할 수 있습니다.';notice.hidden=false;}
if(query.has('logged_out')){notice.textContent='로그아웃되었습니다.';notice.hidden=false;}
toggle.addEventListener('click',()=>{
 const visible=password.type==='password';
 password.type=visible?'text':'password';toggle.textContent=visible?'숨기기':'보기';
 toggle.setAttribute('aria-label',visible?'비밀번호 숨기기':'비밀번호 표시');
 toggle.setAttribute('aria-pressed',String(visible));
});
form.addEventListener('submit',async event=>{
 event.preventDefault();if(button.disabled)return;
 error.hidden=true;notice.hidden=true;button.disabled=true;button.firstElementChild.textContent='로그인 중…';
 try{
  const response=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:form.elements.username.value.trim(),password:password.value})});
  const data=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(typeof data?.detail==='string'?data.detail:'로그인할 수 없습니다. 입력한 정보와 연결 상태를 확인해주세요.');
  if(!['/workspace','/headquarters'].includes(data?.redirect))throw new Error('로그인 응답을 확인하지 못했습니다. 다시 시도해주세요.');
  password.value='';window.location.assign(data.redirect);
 }catch(problem){error.textContent=problem instanceof TypeError?'서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.':problem.message;error.hidden=false;}
 finally{button.disabled=false;button.firstElementChild.textContent='로그인하고 시작하기';}
});
