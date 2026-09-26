'use strict';
// Originals go directly to private storage; only the signed ticket reaches the API.
const MediaUpload = (() => {
 let cached = null;
 async function checksum(file) {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return btoa(String.fromCharCode(...new Uint8Array(digest)));
 }
 function send(target, file, progress) {
  return new Promise((resolve, reject) => {
   const xhr = new XMLHttpRequest(), body = new FormData();
   Object.entries(target.fields).forEach(([key, value]) => body.append(key, value));
   // Avoid sending the original filename to storage, including multipart metadata.
   body.append('file', file, 'original');
   xhr.open('POST', target.url);
   xhr.timeout = 120000;
   xhr.upload.onprogress = event => progress(event.lengthComputable ? Math.min(file.size, event.loaded / event.total * file.size) : 0);
   xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('저장소 업로드가 거절되었습니다. 연결 및 저장소 설정을 확인해주세요.'));
   xhr.onerror = () => reject(new Error('파일 업로드 연결이 끊겼습니다. 네트워크 연결을 확인하고 다시 요청해주세요.'));
   xhr.ontimeout = () => reject(new Error('파일 업로드 시간이 초과되었습니다. 다시 요청해주세요.'));
   xhr.send(body);
  });
 }
 async function prepare(entries, api, progress = () => {}) {
  const same = cached && Date.now() < cached.expires && cached.entries.length === entries.length &&
   entries.every((entry, i) => cached.entries[i].file === entry.file && cached.entries[i].group === entry.group);
  if (!same) {
   const records = [];
   for (const {file, group} of entries) {
    progress({stage: 'checksum', name: file.name, completed: records.length, count: entries.length});
    records.push({name: file.name, size: file.size, group, sha256: await checksum(file)});
   }
   const batch = await api('api/uploads', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({files: records})});
   cached = {entries: entries.map(e => ({...e})), batch, done: new Set(), expires: Date.now() + (batch.upload_expires_in - 30) * 1000};
  }
  const state = cached, total = entries.reduce((sum, e) => sum + e.file.size, 0);
  let loaded = entries.reduce((sum, e, i) => sum + (state.done.has(i) ? e.file.size : 0), 0);
  for (let i = 0; i < entries.length; i++) {
   if (state.done.has(i)) continue;
   const {file} = entries[i];
   for (let attempt = 1; attempt <= 3; attempt++) {
    try {
     await send(state.batch.uploads[i], file, bytes => progress({stage: 'upload', name: file.name, completed: state.done.size, count: entries.length, loaded: loaded + bytes, total, attempt}));
     state.done.add(i); loaded += file.size;
     progress({stage: 'upload', name: file.name, completed: state.done.size, count: entries.length, loaded, total, attempt});
     break;
    } catch (error) {
     if (attempt === 3) throw error;
     await new Promise(resolve => setTimeout(resolve, attempt * 500));
    }
   }
  }
  return state.batch.ticket;
 }
 return {prepare, reset() {cached = null;}};
})();
if (typeof module !== 'undefined') module.exports = MediaUpload;
