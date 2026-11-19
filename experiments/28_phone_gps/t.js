const {chromium}=require('playwright');
const fs=require('fs');
const IP=fs.readFileSync(__dirname+'/certs/_ip.txt','utf8').trim();
(async()=>{
const b=await chromium.launch({args:['--no-proxy-server']});
// HTTP (insecure origin)
const c1=await b.newContext({ignoreHTTPSErrors:true});
const p1=await c1.newPage();
await p1.goto('http://'+IP+':8080/report.html');
await p1.waitForTimeout(300);
const httpCtx=await p1.evaluate(()=>window.__ctx());
const btnDisabled=await p1.$eval('#go',e=>e.disabled);
// HTTPS (secure origin)
const c2=await b.newContext({ignoreHTTPSErrors:true});
await c2.grantPermissions(['geolocation'],{origin:'https://'+IP+':8443'});
await c2.setGeolocation({latitude:30.39382,longitude:-81.93785,accuracy:12});
const p2=await c2.newPage();
await p2.goto('https://'+IP+':8443/report.html');
await p2.waitForTimeout(300);
const httpsCtx=await p2.evaluate(()=>window.__ctx());
await p2.click('#go');
await p2.waitForTimeout(900);
const units=await p2.evaluate(()=>fetch('/units.json').then(r=>r.json()));
await p2.screenshot({path:'proof.png'});
console.log(JSON.stringify({
  http_secureContext:httpCtx.secure, http_button_disabled:btnDisabled,
  https_secureContext:httpsCtx.secure, box_received_units:units
},null,2));
await b.close();
})();
