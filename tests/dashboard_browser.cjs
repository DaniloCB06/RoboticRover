// Optional browser regression test. Start Chrome with --remote-debugging-port=19222.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { pathToFileURL } = require('url');

(async () => {
  const tabs = await (await fetch('http://127.0.0.1:19222/json/list')).json();
  const tab = tabs.find(item => item.type === 'page' && item.webSocketDebuggerUrl);
  if (!tab) throw new Error('No Chrome page available for browser QA');
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise(resolve => ws.onopen = resolve);
  let id = 0;
  const requests = new Map();
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const request = requests.get(message.id);
    requests.delete(message.id);
    message.error ? request.reject(Error(message.error.message)) : request.resolve(message.result);
  };
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    requests.set(++id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const run = async expression => {
    const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const pause = () => new Promise(resolve => setTimeout(resolve, 100));
  await call('Page.enable');
  await call('Page.bringToFront');
  await call('Emulation.setFocusEmulationEnabled',{enabled:true});
  await call('Page.addScriptToEvaluateOnNewDocument', { source: `
    window.__sent=[]; window.__mode='SEGURO_ESPERA'; window.__manual=false;
    window.__receive=(type,data)=>window.__socket.onmessage({data:JSON.stringify({version:'1.0',timestamp:new Date().toISOString(),source:'browser-test',simulated:true,type,data})});
    window.WebSocket=class {static OPEN=1;readyState=1;constructor(){window.__socket=this;setTimeout(()=>this.onopen(),10);}close(){}
      send(payload){const p=JSON.parse(payload);window.__sent.push(p);setTimeout(()=>{
        if(p.kind==='mode'){window.__mode=p.mode;if(['BUSCA','APROXIMACAO'].includes(p.mode))window.__manual=false;}
        else if(p.action==='PARAR'){window.__mode='SEGURO_ESPERA';window.__manual=window.__manual||p.take_control===true;}
        window.__receive('state',{state:window.__mode,reason:'test',manual_enabled:window.__manual,control_target:p.target||'rover'});
        window.__receive('ack',{command_id:p.command_id,accepted:true,state:window.__mode,reason:'ACCEPTED',control_target:p.target||'rover'});
      },15);}};
    window.fetch=async()=>({ok:true,json:async()=>({history:[]})});
  ` });
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await call('Page.navigate', { url: pathToFileURL(path.resolve('apps/station/node-red/dashboard.html')).href });
  await new Promise(resolve => setTimeout(resolve, 500));
  await run(`__receive('status',{online:true});__receive('state',{state:'BUSCA',manual_enabled:false});`);
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>b.disabled)`));
  await run(`document.querySelector('[data-mode="CAPTURA_MANUAL"]').click();document.querySelector('[data-action="PARAR"]').click();for(const key of ['w','ArrowUp','Escape'])document.body.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}));`);
  assert.equal(await run('__sent.length'), 0, 'Locked UI must not send any manual command');
  await run(`__receive('state',{state:'APROXIMACAO',manual_enabled:false});`);
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>b.disabled)`));
  await run(`__manual=true;__mode='AGUARDANDO_PEGA';__receive('state',{state:'AGUARDANDO_PEGA',reason:'approach_completed',manual_enabled:true,control_target:'manipulator'});`);
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>!b.disabled)`));
  assert((await run(`document.getElementById('controlTargetButton').textContent`)).includes('braço'));
  await run(`document.querySelector('[data-action="AVANCAR"]').click()`);
  await pause();
  assert.deepEqual(await run(`({target:__sent.at(-1).target,action:__sent.at(-1).action})`), { target: 'manipulator', action: 'SUBIR' });
  await run(`document.getElementById('controlTargetButton').click()`);
  await pause();
  assert.equal(await run('__sent.at(-1).action'), 'PARAR');
  await run(`document.querySelector('[data-action="AVANCAR"]').focus();document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'w',bubbles:true,cancelable:true}));`);
  await pause();
  assert.deepEqual(await run(`({target:__sent.at(-1).target,action:__sent.at(-1).action})`), { target: 'rover', action: 'AVANCAR' });
  await run(`document.querySelector('[data-mode="BUSCA"]').click()`);
  await pause();
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>b.disabled)`));
  const count = await run('__sent.length');
  await run(`document.body.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true}));`);
  await pause();
  assert.equal(await run(`__sent[${count}].take_control`), true);
  assert.equal(await run(`document.getElementById('currentState').textContent`), 'Manual');
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>!b.disabled)`));
  const beforeHold = await run(`__sent.filter(p=>p.action==='AVANCAR').length`);
  await run(`document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true,cancelable:true}));`);
  await new Promise(resolve=>setTimeout(resolve,400));
  assert((await run(`__sent.filter(p=>p.action==='AVANCAR').length`))>=beforeHold+2,'Held key must renew bounded movement');
  await run(`document.body.dispatchEvent(new KeyboardEvent('keyup',{key:'ArrowUp',bubbles:true,cancelable:true}));`);
  await pause();
  assert.equal(await run(`__sent.at(-1).action`),'PARAR','Key release must stop');
  const afterRelease = await run('__sent.length');
  await new Promise(resolve=>setTimeout(resolve,350));
  assert.equal(await run('__sent.length'),afterRelease,'Release must cancel renewal');
  await run(`document.getElementById('controlHelpButton').click()`);
  assert.equal(await run(`document.getElementById('controlHelpModal').hidden`), false);
  const help = await run(`document.getElementById('controlHelpModal').textContent`);
  assert(help.includes('Pilotar Rover') && help.includes('Controlar braço') && help.includes('Espaço'));
  await run(`document.querySelector('#controlHelpModal [data-close]').click();__receive('telemetry',{battery_percent:87.5,temperature_c:41.3});document.getElementById('telemetryButton').click();`);
  assert.equal(await run(`document.getElementById('batteryValue').textContent`), '87.5 %');
  await run(`document.querySelector('#telemetryModal [data-close]').click();document.querySelector('#eventList button').click()`);
  assert.equal(await run(`document.getElementById('detailsModal').hidden`), false);
  await run(`document.querySelector('#detailsModal [data-close]').click()`);
  const pad = await run(`(()=>{const r=document.querySelector('[data-action="AVANCAR"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...pad});
  await new Promise(resolve=>setTimeout(resolve,300));
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...pad});
  await pause();
  assert.equal(await run(`__sent.at(-1).action`),'PARAR','Pointer release must stop');
  fs.mkdirSync('.runtime', { recursive: true });
  let shot = await call('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('.runtime/dashboard-desktop.png', Buffer.from(shot.data, 'base64'));
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 1000, deviceScaleFactor: 1, mobile: true });
  assert(await run('document.documentElement.scrollWidth<=window.innerWidth'));
  shot = await call('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('.runtime/dashboard-mobile.png', Buffer.from(shot.data, 'base64'));
  await run('__socket.onclose()');
  assert(await run(`[...document.querySelectorAll('[data-action]')].every(b=>b.disabled)`));
  console.log('Browser QA OK: bloqueio total, teclado, fim da aproximação, braço/rodas, Espaço, popups e responsividade.');
  ws.close();
})().catch(error => { console.error(error); process.exit(1); });
