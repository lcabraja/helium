#!/usr/bin/env python3
"""Serve the private editor preview, own fixtures and native download directory."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
from urllib.parse import urlsplit

FIXTURE = '''<!doctype html><html><head><meta charset="utf-8"><title>Helium script fixture</title>
<script src="/fixtures/page.js"></script><link rel="stylesheet" href="/fixtures/page.css"></head>
<body><main><p class="eyebrow">HELIUM · OWN TEST PAGE</p><h1>User-script playground</h1>
<p>Use this page to check MAIN-world JavaScript, timing and single-page routes.</p>
<pre id="state"></pre><div><button data-route="/fixtures/watch?v=AAA">SPA: watch AAA</button>
<button data-route="/fixtures/watch?v=BBB">SPA: watch BBB</button><button data-route="/fixtures/other">SPA: nonmatch</button>
<button data-route="/fixtures/watch?v=AAA#details">SPA: fragment</button></div>
<p><a href="/fixtures/watch?v=AAA">Normal navigation</a> · <a href="/fixtures/strict">Strict CSP</a> ·
<a href="/fixtures/slow">Slow load</a> · <a href="/">Download and guide</a></p><div id="script-output"></div>
SLOW_IMAGE</main></body></html>'''
PAGE_JS = '''window.fixture = {pageValue: 41, firstScriptReadyState: document.readyState,
  startMarkerAtFirstScript: window.heliumStartMarker || null};
console.log('[Fixture] first page script', JSON.stringify(window.fixture));
function renderFixture() { const el=document.getElementById('state');if(el)el.textContent=JSON.stringify({
 url:location.href, readyState:document.readyState, fixture:window.fixture,
 startRuns:window.heliumStartRuns||0, loadRuns:window.heliumLoadRuns||0, mainAnswer:window.heliumMainAnswer||null},null,2); }
addEventListener('DOMContentLoaded',()=>{ document.querySelectorAll('[data-route]').forEach(button=>button.addEventListener('click',()=>{
 history.pushState({},'',button.dataset.route);renderFixture();}));renderFixture(); });
addEventListener('load',()=>{console.log('[Fixture] window load');renderFixture();});
addEventListener('popstate',renderFixture);setInterval(renderFixture,100);
'''
STYLE = '''body{font:16px -apple-system,sans-serif;margin:0;background:#101318;color:#e6e9f0}main{max-width:840px;margin:70px auto;padding:24px}h1{font-size:40px}pre{padding:22px;border:1px solid #394355;border-radius:14px;white-space:pre-wrap}button{padding:12px;margin:5px;border-radius:8px;border:1px solid #7587c3;background:#273049;color:inherit}a{color:#a5b5ff}.eyebrow{color:#8d9cd1;font-size:12px;letter-spacing:.14em}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8130)
    args=parser.parse_args()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):
            super().__init__(*a,directory=str(args.root),**kw)
        def end_headers(self):
            self.send_header('Cache-Control','no-store')
            super().end_headers()
        def do_GET(self):
            path=urlsplit(self.path).path
            if not path.startswith('/fixtures/'):
                return super().do_GET()
            ctype='text/html; charset=utf-8'
            if path=='/fixtures/page.js':
                data=PAGE_JS.encode();ctype='text/javascript; charset=utf-8'
            elif path=='/fixtures/page.css':
                data=STYLE.encode();ctype='text/css; charset=utf-8'
            elif path=='/fixtures/slow.svg':
                time.sleep(4);ctype='image/svg+xml'
                data=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
            else:
                data=FIXTURE.replace('SLOW_IMAGE','<img src="/fixtures/slow.svg" alt=""/>' if path=='/fixtures/slow' else '').encode()
            self.send_response(200)
            if path=='/fixtures/strict':
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'")
            self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':
    main()
