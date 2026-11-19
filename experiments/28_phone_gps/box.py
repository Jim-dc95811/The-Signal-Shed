#!/usr/bin/env python3
"""Prototype: phone-GPS -> box over HTTPS (Signal Shed #28).
Serves the phone page on http:8080 (insecure) AND https:8443 (secure),
so you can see the browser gate: geolocation only works on https.
POST /report folds a phone's own fix into the box's unit list."""
import json, ssl, threading, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE=os.path.dirname(os.path.abspath(__file__))
UNITS={}; LOCK=threading.Lock()
PAGE=open(os.path.join(HERE,"report.html"),"rb").read()
CA=open(os.path.join(HERE,"certs","lookout-ca.crt"),"rb").read()
class H(BaseHTTPRequestHandler):
    def _send(self,code,body,ctype="application/json",extra=None):
        self.send_response(code);self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        if extra:
            for k,v in extra.items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def log_message(self,*a): pass
    def do_GET(self):
        p=self.path.split("?")[0]
        if p in("/","/report.html"): return self._send(200,PAGE,"text/html; charset=utf-8")
        if p=="/units.json":
            with LOCK: out=json.dumps(list(UNITS.values())).encode()
            return self._send(200,out)
        if p=="/ca":  # phone downloads the fleet CA to install
            return self._send(200,CA,"application/x-x509-ca-cert",
                {"Content-Disposition":"attachment; filename=lookout-fleet-ca.crt"})
        self._send(404,b'{"err":"not found"}')
    def do_POST(self):
        if self.path.split("?")[0]!="/report": return self._send(404,b'{"err":"no"}')
        n=int(self.headers.get("Content-Length",0))
        try: d=json.loads(self.rfile.read(n) or b"{}")
        except Exception: return self._send(400,b'{"err":"bad json"}')
        lat,lon=d.get("lat"),d.get("lon")
        if not(isinstance(lat,(int,float)) and isinstance(lon,(int,float))
               and -90<=lat<=90 and -180<=lon<=180):
            return self._send(400,b'{"err":"bad coords"}')
        uid=str(d.get("id") or "phone")[:24]
        with LOCK:
            UNITS[uid]={"id":uid,"lat":round(lat,6),"lon":round(lon,6),
                        "acc":d.get("acc"),"t":time.strftime("%H:%M:%S")}
        self._send(200,b'{"ok":true}')
def serve(port,tls):
    s=ThreadingHTTPServer(("0.0.0.0",port),H)
    if tls:
        c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        c.load_cert_chain(os.path.join(HERE,"certs","server.crt"),
                          os.path.join(HERE,"certs","server.key"))
        s.socket=c.wrap_socket(s.socket,server_side=True)
    print(("https" if tls else "http")+f" on :{port}")
    s.serve_forever()
if __name__=="__main__":
    threading.Thread(target=serve,args=(8080,False),daemon=True).start()
    serve(8443,True)
