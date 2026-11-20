const {chromium}=require('playwright');const fs=require('fs');
const IP=fs.readFileSync(__dirname+'/certs/_ip.txt','utf8').trim();
(async()=>{
const b=await chromium.launch({args:['--no-proxy-server']});
// http: secure context false
const c1=await b.newContext({ignoreHTTPSErrors:true});const p1=await c1.newPage();
await p1.goto('http://'+IP+':8080/share');await p1.waitForTimeout(300);
const httpSecure=await p1.evaluate(()=>window.isSecureContext);
const btn=await p1.$eval('#go',e=>e.disabled);
// https: secure, share, lands on box
const c2=await b.newContext({ignoreHTTPSErrors:true});
await c2.grantPermissions(['geolocation'],{origin:'https://'+IP+':8443'});
await c2.setGeolocation({latitude:30.42,longitude:-81.90,accuracy:9});
const p2=await c2.newPage();
await p2.goto('https://'+IP+':8443/share');await p2.waitForTimeout(300);
const httpsSecure=await p2.evaluate(()=>window.isSecureContext);
await p2.click('#go');await p2.waitForTimeout(900);
const units=await p2.evaluate(()=>fetch('/units.json').then(r=>r.json()));
const kml=await p2.evaluate(()=>fetch('/units.kml').then(r=>r.text()));
await p2.screenshot({path:'proof_units.png'});
console.log(JSON.stringify({http_secure:httpSecure,http_btn_disabled:btn,https_secure:httpsSecure,units_count:units.count,unit:units.units[0],kml_has_phone:kml.includes('phone-')},null,2));
await b.close();})();
