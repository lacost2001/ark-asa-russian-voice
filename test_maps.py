import tempfile,threading,hashlib,json
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import asa_maps as maps
DATA=b'abcdefghijklmnopqrstuvwxyz'*1000;seen=[]
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  start,end=map(int,self.headers['Range'][6:].split('-'));seen.append((start,end))
  self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(DATA)}');self.end_headers();self.wfile.write(DATA[start:end+1])
srv=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{srv.server_port}/part'
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'movie.bk2';expected=DATA[30:100]+DATA[300:500]
 item={'path':'Movies/movie.bk2','size':len(expected),'sha256':hashlib.sha256(expected).hexdigest(),'ranges':[{'url':url,'start':30,'size':70},{'url':url,'start':300,'size':200}]}
 p.with_name(p.name+'.partial').write_bytes(expected[:90]);maps.download_ranges(item,p,lambda x:None);assert p.read_bytes()==expected;assert seen==[(320,499)],seen
 p.write_bytes(b'broken');seen.clear();maps.download_ranges(item,p,lambda x:None);assert p.read_bytes()==expected
 cat={'groups':{'TheIsland':{'files':[item]},'Genesis2':{'files':[dict(item,path='Movies/other.bk2')]},'Shared':{'files':[]}}}
 assert [x['path'] for x in maps.chosen_files(cat,['TheIsland'])]==['Movies/movie.bk2']
 try:maps.chosen_files(cat,[])
 except RuntimeError:pass
 else:raise AssertionError('Empty selection accepted')
srv.shutdown();print('PASS: ranged multipart resume, checksum repair, selected maps only, empty selection')
# Production catalog must partition all speech, without duplicate replacement paths.
c=json.loads(Path('maps.json').read_text('utf-8'));paths=[x['path'] for g in c['groups'].values() for x in g['files']]
assert len(paths)==len(set(paths));assert sum(g['audio_assets'] for g in c['groups'].values())==1792
print('PASS: production map partition, 1792 assets, no conflicting files')
