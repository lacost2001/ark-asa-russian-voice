import io,json,hashlib,os,time,urllib.request,zipfile,shutil,bisect
from pathlib import Path

BASE='https://github.com/lacost2001/ark-asa-russian-voice/releases/download/v1.0.0/'
VERSION='1.1.0'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def fetch(url,path,size,checksum,progress):
 if path.exists() and path.stat().st_size==size and sha(path)==checksum:return
 temp=path.with_name(path.name+'.partial')
 for attempt in range(3):
  try:
   offset=temp.stat().st_size if temp.exists() else 0
   if offset>size:temp.unlink();offset=0
   if offset<size:
    req=urllib.request.Request(url,headers={'User-Agent':'ASA-Russian-Voice/'+VERSION,**({'Range':f'bytes={offset}-'} if offset else {})})
    with urllib.request.urlopen(req,timeout=60) as r:
     if offset and r.status==206:
      if not r.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise RuntimeError('Некорректный ответ при продолжении загрузки')
     elif r.status==200:offset=0
     else:raise RuntimeError('Неожиданный ответ сервера загрузки')
     with temp.open('ab' if offset else 'wb') as f:
      last=0
      while True:
       b=r.read(1024*1024)
       if not b:break
       if offset+len(b)>size:raise RuntimeError('Размер загрузки превышает ожидаемый')
       f.write(b);offset+=len(b)
       if time.monotonic()-last>0.5:progress(f'{path.name}: {offset/size:.0%}');last=time.monotonic()
   if temp.stat().st_size!=size:raise RuntimeError('Загрузка оборвалась')
   progress('Проверка SHA256: '+path.name)
   if sha(temp)!=checksum:
    temp.unlink();raise RuntimeError('Контрольная сумма не совпала')
   os.replace(temp,path);return
  except Exception:
   if attempt==2:raise
   progress('Повторная попытка: '+path.name);time.sleep(1)

class PartsReader(io.RawIOBase):
 def __init__(self,paths):
  super().__init__();self.files=[p.open('rb') for p in paths];self.ends=[];total=0
  for p in paths:total+=p.stat().st_size;self.ends.append(total)
  self.total=total;self.pos=0
 def seekable(self):return True
 def readable(self):return True
 def tell(self):return self.pos
 def seek(self,offset,whence=0):
  p=offset if whence==0 else self.pos+offset if whence==1 else self.total+offset
  if p<0:raise ValueError('Negative seek')
  self.pos=p;return p
 def read(self,n=-1):
  n=max(0,self.total-self.pos) if n<0 else min(n,max(0,self.total-self.pos));out=[]
  while n:
   i=bisect.bisect_right(self.ends,self.pos);start=self.ends[i-1] if i else 0
   f=self.files[i];f.seek(self.pos-start);b=f.read(min(n,self.ends[i]-self.pos))
   if not b:raise OSError('Unexpected end of archive part')
   out.append(b);self.pos+=len(b);n-=len(b)
  return b''.join(out)
 def close(self):
  for f in self.files:f.close()
  super().close()

def extract(paths,destination,progress):
 destination=destination.resolve();destination.mkdir(parents=True,exist_ok=True)
 with PartsReader(paths) as stream,zipfile.ZipFile(stream) as z:
  entries=z.infolist();targets=[]
  for x in entries:
   target=(destination/x.filename).resolve()
   if not target.is_relative_to(destination) or ':' in x.filename or '\\' in x.filename:raise RuntimeError('Недопустимый путь в архиве')
   targets.append(target)
  needed=sum(x.file_size for x in entries if not x.is_dir())
  if shutil.disk_usage(destination).free<needed+1024**3:raise RuntimeError('Недостаточно места для распаковки: нужно около 30 ГБ.')
  for i,(x,target) in enumerate(zip(entries,targets)):
   if x.is_dir():target.mkdir(parents=True,exist_ok=True);continue
   progress(f'Распаковка {i+1}/{len(entries)}: {target.name}')
   target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.name+'.extracting')
   with z.open(x) as src,tmp.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
   os.replace(tmp,target)

# Fixed release metadata fingerprint prevents substituting a different package.
METADATA_SHA256='356a08ac8f7781195da297dca32495f7f32048605cb3f2cef0ab42a186d5e6e9'
def prepare(cache,progress=print):
 cache=cache.resolve();cache.mkdir(parents=True,exist_ok=True)
 progress('Получение списка файлов с GitHub…')
 with urllib.request.urlopen(urllib.request.Request(BASE+'parts.json',headers={'User-Agent':'ASA-Russian-Voice/'+VERSION}),timeout=60) as r:data=r.read(1024*1024)
 if hashlib.sha256(data).hexdigest()!=METADATA_SHA256:raise RuntimeError('Список файлов не прошёл проверку. Обновите установщик.')
 meta=json.loads(data);paths=[]
 for part in meta['parts']:
  name=part['name']
  if Path(name).name!=name or '/' in name or '\\' in name:raise RuntimeError('Недопустимое имя части')
  paths.append(cache/name)
 required=sum(max(0,x['size']-(p.with_name(p.name+'.partial').stat().st_size if p.with_name(p.name+'.partial').exists() else 0)) for x,p in zip(meta['parts'],paths) if not p.exists())
 if shutil.disk_usage(cache).free<required+1024**3:raise RuntimeError('Недостаточно места для загрузки 29 ГБ. Выберите другой диск для пакета.')
 for i,(part,p) in enumerate(zip(meta['parts'],paths)):
  progress(f'Часть {i+1}/{len(paths)}')
  fetch(BASE+part['name'],p,part['size'],part['sha256'],progress)
 progress('Проверка полного архива…');h=hashlib.sha256()
 for p in paths:
  with p.open('rb') as f:
   for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 if h.hexdigest()!=meta['sha256']:raise RuntimeError('Архив не прошёл проверку')
 unpack=cache/'unpacked';marker=unpack/'.complete'
 if not marker.exists() or marker.read_text()!=meta['sha256']:
  extract(paths,unpack,progress);marker.write_text(meta['sha256'])
 manifests=list(unpack.glob('*/manifest.json'))
 if (unpack/'manifest.json').exists():manifests=[unpack/'manifest.json']
 if len(manifests)!=1:raise RuntimeError('Не найден установочный пакет')
 return manifests[0].parent
