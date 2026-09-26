const {test} = require('node:test');
const assert = require('node:assert/strict');
const media = require('../frontend/js/media-upload.js');

test('direct upload retries failures, retains successful files and sends only metadata to API', async () => {
 const attempts = [], calls = [], progress = [];
 let failSecond = true;
 const previous = global.XMLHttpRequest;
 global.XMLHttpRequest = class {
  upload = {};
  open(method, url) {assert.equal(method, 'POST'); this.url = url;}
  send(body) {
   assert.equal(body.get('file').name, 'original');
   attempts.push(this.url);
   queueMicrotask(() => {
    this.upload.onprogress({lengthComputable: true, loaded: 3, total: 3});
    this.status = this.url.endsWith('/1') && failSecond ? 503 : 204;
    this.onload();
   });
  }
 };
 const entries = [0,1].map(i => ({file: new File(['abc'], `scan-${i}.png`), group: 'ulna'}));
 const api = async (url, options) => {
  calls.push(url);
  const body = JSON.parse(options.body);
  assert.equal(body.files.length, 2);
  assert.equal(body.files[0].sha256, 'ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=');
  assert.ok(options.body.length < 1000);
  return {ticket: 'signed-ticket', upload_expires_in: 900,
   uploads: entries.map((_,i) => ({url: `https://storage.test/${i}`, fields: {key: `random-${i}`}}))};
 };
 try {
  await assert.rejects(media.prepare(entries, api, p => progress.push(p)));
  assert.deepEqual(attempts, ['https://storage.test/0','https://storage.test/1','https://storage.test/1','https://storage.test/1']);
  failSecond = false;
  assert.equal(await media.prepare(entries, api, p => progress.push(p)), 'signed-ticket');
  assert.equal(attempts.filter(x => x.endsWith('/0')).length, 1);
  assert.equal(calls.length, 1);
  assert.equal(progress.at(-1).loaded, 6);
  assert.equal(progress.at(-1).completed, 2);
  media.reset();
  await media.prepare(entries, api);
  assert.equal(calls.length, 2);
 } finally {global.XMLHttpRequest = previous; media.reset();}
});
