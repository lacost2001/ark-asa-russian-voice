import tempfile,threading,hashlib,zipfile,io
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import asa_download as d
DATA=b'test data'*10000
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  offset=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0]);offset=0 if self.path=='/ignore' else offset
  self.send_response(206 if offset else 200)
  if offset:self.send_header('Content-Range',f'bytes {offset}-{len(DATA)-1}/{len(DATA)}')
  self.end_headers();self.wfile.write(DATA[offset:])
server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);h=hashlib.sha256(DATA).hexdigest()
 for route in ['resume','ignore']:
  p=root/route;p.with_name(p.name+'.partial').write_bytes(DATA[:50]);d.fetch(f'http://127.0.0.1:{server.server_port}/{route}',p,len(DATA),h,lambda x:None);assert p.read_bytes()==DATA
 p=root/'bad';p.write_bytes(b'bad');d.fetch(f'http://127.0.0.1:{server.server_port}/ok',p,len(DATA),h,lambda x:None);assert p.read_bytes()==DATA
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,'w') as z:z.writestr('package/manifest.json','{}');z.writestr('package/data.bin',DATA)
 raw=buf.getvalue();parts=[]
 for i in range(0,len(raw),7777):
  p=root/str(i);p.write_bytes(raw[i:i+7777]);parts.append(p)
 d.extract(parts,root/'out',lambda x:None);assert (root/'out/package/data.bin').read_bytes()==DATA
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,'w') as z:z.writestr('../escape','bad')
 p=root/'evil';p.write_bytes(buf.getvalue())
 try:d.extract([p],root/'out',lambda x:None)
 except RuntimeError:pass
 else:raise AssertionError('Unsafe path accepted')
server.shutdown();print('PASS: resumed download, ignored Range, corrupt cache, multipart ZIP, traversal rejection')
