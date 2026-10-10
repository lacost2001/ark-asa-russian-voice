"""Selective downloads from fixed GitHub release assets; no whole-archive download."""
import json,hashlib,os,shutil,time,urllib.request
from pathlib import Path
from asa_download import fetch,sha

def download_ranges(item,dest,progress):
 if dest.exists() and dest.stat().st_size==item['size'] and sha(dest)==item['sha256']:return
 temp=dest.with_name(dest.name+'.partial');ranges=item['ranges']
 for attempt in range(3):
  try:
   offset=temp.stat().st_size if temp.exists() else 0
   if offset>item['size']:temp.unlink();offset=0
   consumed=0
   for segment in ranges:
    if offset>=consumed+segment['size']:consumed+=segment['size'];continue
    skip=max(0,offset-consumed);start=segment['start']+skip;left=segment['size']-skip
    # Bounded requests allow resuming without requesting any other movie bytes.
    while left:
     amount=min(left,16*1024*1024);end=start+amount-1
     req=urllib.request.Request(segment['url'],headers={'User-Agent':'ASA-Russian-Voice/1.2.0','Range':f'bytes={start}-{end}'})
     with urllib.request.urlopen(req,timeout=60) as r:
      if r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):raise RuntimeError('GitHub не подтвердил частичную загрузку. Повторите позже.')
      with temp.open('ab' if offset else 'wb') as f:
       remaining=amount
       while remaining:
        b=r.read(min(1024*1024,remaining))
        if not b:raise RuntimeError('Загрузка прервалась')
        f.write(b);offset+=len(b);remaining-=len(b)
     start+=amount;left-=amount;progress(f'{dest.name}: {offset/item["size"]:.0%}')
    consumed+=segment['size']
   if offset!=item['size'] or sha(temp)!=item['sha256']:
    temp.unlink(missing_ok=True);raise RuntimeError('Контрольная сумма файла не совпала')
   os.replace(temp,dest);return
  except Exception:
   if attempt==2:raise
   progress('Повтор загрузки: '+dest.name);time.sleep(1)

def chosen_files(catalog,selected):
 keys=set(selected)
 if not keys:raise RuntimeError('Выберите хотя бы одну карту.')
 if 'Shared' in catalog['groups']:keys.add('Shared')
 if not keys.issubset(catalog['groups']):raise RuntimeError('Неизвестная карта')
 result={}
 for key in keys:
  for item in catalog['groups'][key]['files']:
   if item['path'] in result and result[item['path']]['sha256']!=item['sha256']:raise RuntimeError('Конфликт пакетов')
   result[item['path']]=item
 return list(result.values())

def prepare_maps(catalog,selected,cache,game,progress):
 from asa_installer import safe,copy_atomic
 items=chosen_files(catalog,selected);cache=cache.resolve();cache.mkdir(parents=True,exist_ok=True)
 needed=0
 for item in items:
  dest=safe(cache,item['path'])
  if not dest.exists() or sha(dest)!=item['sha256']:needed+=item['size']
 if shutil.disk_usage(cache).free<needed+1024**3:raise RuntimeError('Недостаточно места в папке загрузки для выбранных карт.')
 for i,item in enumerate(items):
  dest=safe(cache,item['path']);dest.parent.mkdir(parents=True,exist_ok=True);progress(f'Файл {i+1}/{len(items)}: {dest.name}')
  if dest.exists() and sha(dest)==item['sha256']:continue
  local=safe(game/'ShooterGame/Content',item['path'])
  if local.exists() and sha(local)==item['sha256']:copy_atomic(local,dest,item['sha256']);continue
  if 'ranges' in item:download_ranges(item,dest,progress)
  else:fetch(item['url'],dest,item['size'],item['sha256'],progress)
 manifest={'version':'1.2.0','files':items}
 from asa_installer import atomic_json
 atomic_json(cache/'manifest.json',manifest)
 return cache

def validate_legacy(catalog,game):
 from asa_installer import safe
 for item in catalog['legacy_files']:
  p=safe(game/'ShooterGame/Content',item['path'])
  if p.exists() and sha(p) not in [item['sha256'],*item.get('previous_sha256',[])]:raise RuntimeError('Неизвестная версия старого общего пакета: '+p.name)

def deactivate_legacy(catalog,game):
 from asa_installer import safe,copy_atomic,running
 if running():raise RuntimeError('Игра запущена. Закройте её и повторите установку для завершения перехода.')
 validate_legacy(catalog,game)
 for item in catalog['legacy_files']:
  p=safe(game/'ShooterGame/Content',item['path'])
  if p.exists():
   target=game/'.ASA-Russian-Voice-Backup/legacy-containers'/p.name
   copy_atomic(p,target,sha(p));p.unlink()
