"""Offline ASA voice installer. Payload hashes and original backups are mandatory."""
import argparse,csv,hashlib,json,os,shutil,subprocess,sys,threading
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def atomic_json(p,obj):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)
def safe(root,relative):
 p=(root/relative).resolve()
 if not p.is_relative_to(root.resolve()):raise RuntimeError('Недопустимый путь в пакете')
 return p
def running():
 if os.name!='nt':return False
 p=subprocess.run(['tasklist','/FI','IMAGENAME eq ArkAscended.exe','/FO','CSV','/NH'],capture_output=True,creationflags=0x08000000)
 return b'arkascended.exe' in p.stdout.lower()
def locate_game(raw):
 p=Path(raw.strip().strip('"')).expanduser().resolve()
 for x in [p,p/'steamapps/common/ARK Survival Ascended',p/'common/ARK Survival Ascended']:
  if (x/'ShooterGame/Binaries/Win64/ArkAscended.exe').is_file():return x
 raise RuntimeError('Выберите папку ARK Survival Ascended или её библиотеку Steam.')
def copy_atomic(src,dst,expected):
 dst.parent.mkdir(parents=True,exist_ok=True);tmp=dst.with_name(dst.name+'.asa-ru-tmp')
 shutil.copy2(src,tmp)
 if digest(tmp)!=expected:raise RuntimeError('Ошибка копирования: '+dst.name)
 os.replace(tmp,dst)
def install(package,game,progress=print,originals=None):
 game=locate_game(str(game))
 if running():raise RuntimeError('Закройте ARK Survival Ascended перед установкой.')
 manifest=json.loads((package/'manifest.json').read_text('utf-8'))
 files=manifest['files'];backup=game/'.ASA-Russian-Voice-Backup';journal=backup/'state.json'
 state=json.loads(journal.read_text('utf-8')) if journal.exists() else {'format':1,'files':{}}
 # Verify every payload and original before changing any installed file.
 tasks=[];needed=0
 for i,x in enumerate(files):
  rel=x['path'];src=safe(package,rel);target=safe(game/'ShooterGame/Content',rel)
  if digest(src)!=x['sha256']:raise RuntimeError('Пакет повреждён: '+rel)
  current=digest(target) if target.exists() else None
  allowed=[x['sha256'],x.get('original_sha256'),*x.get('previous_sha256',[])]
  if current is not None and rel in state['files']:allowed.append(state['files'][rel]['installed_sha256'])
  if current is not None and current not in allowed:raise RuntimeError('Файл игры отличается от проверенной версии: '+rel+'. Проверьте версию пакета.')
  original=safe(originals,rel) if originals else None
  if original and original.exists() and digest(original)!=x.get('original_sha256'):raise RuntimeError('Резервный оригинал не прошёл проверку: '+rel)
  if rel.startswith('Movies/') and current!=x.get('original_sha256') and rel not in state['files'] and not (original and original.exists()):raise RuntimeError('Для обновления нужна сохранённая оригинальная копия: '+rel)
  if current!=x['sha256']:needed+=src.stat().st_size
  if rel.startswith('Movies/') and rel not in state['files']:needed+=target.stat().st_size
  if rel in state['files'] and not state['files'][rel]['created']:
   saved=safe(backup,rel)
   if not saved.exists() or digest(saved)!=state['files'][rel]['original_sha256']:raise RuntimeError('Резервная копия отсутствует или повреждена: '+rel)
  tasks.append((x,src,target,current,original));progress(f'Проверка {i+1}/{len(files)}: {target.name}')
 if shutil.disk_usage(game).free<needed+1024**3:raise RuntimeError('Недостаточно места для установки и резервных копий.')
 backup.mkdir(exist_ok=True)
 for i,(x,src,target,current,original) in enumerate(tasks):
  if running():raise RuntimeError('Игра запущена. Установка остановлена; закройте её и повторите.')
  rel=x['path'];saved=safe(backup,rel)
  if rel not in state['files']:
   if rel.startswith('Movies/'):
    origin=original if original and original.exists() else target
    expected=x['original_sha256']
    if not saved.exists():copy_atomic(origin,saved,expected)
    elif digest(saved)!=expected:raise RuntimeError('Резервная копия повреждена: '+rel)
    state['files'][rel]={'original_sha256':expected,'installed_sha256':x['sha256'],'created':False}
   else:state['files'][rel]={'original_sha256':None,'installed_sha256':x['sha256'],'created':True}
   atomic_json(journal,state)
  if current!=x['sha256']:copy_atomic(src,target,x['sha256'])
  state['files'][rel]['installed_sha256']=x['sha256'];atomic_json(journal,state)
  progress(f'Установлено {i+1}/{len(files)}: {target.name}')
 state['version']=manifest['version'];state['complete']=True;atomic_json(journal,state)
 progress('Готово. Можно запускать ASA.')
def restore(game,progress=print):
 game=locate_game(str(game))
 if running():raise RuntimeError('Закройте ASA перед восстановлением.')
 backup=game/'.ASA-Russian-Voice-Backup';journal=backup/'state.json'
 if not journal.exists():raise RuntimeError('Резервные копии этой программы не найдены.')
 state=json.loads(journal.read_text('utf-8'))
 for rel,x in state['files'].items():
  target=safe(game/'ShooterGame/Content',rel)
  if target.exists() and digest(target) not in [x['installed_sha256'],x['original_sha256']]:raise RuntimeError('Файл изменён после установки: '+rel)
  if not x['created'] and digest(safe(backup,rel))!=x['original_sha256']:raise RuntimeError('Резервная копия повреждена: '+rel)
 for rel,x in state['files'].items():
  target=safe(game/'ShooterGame/Content',rel)
  if x['created']:target.unlink(missing_ok=True)
  else:copy_atomic(safe(backup,rel),target,x['original_sha256'])
  progress('Восстановлено: '+rel)
 state['complete']=False;atomic_json(journal,state);progress('Оригинальные файлы восстановлены.')
def gui(package):
 import tkinter as tk
 from tkinter import ttk,filedialog,messagebox
 root=tk.Tk();root.title('ASA — Русская озвучка');root.geometry('800x620');root.configure(bg='#101c28')
 style=ttk.Style();style.theme_use('clam');style.configure('TButton',font=('Segoe UI',11),padding=9)
 tk.Label(root,text='ARK  /  RUSSIAN VOICES',fg='#57d6c7',bg='#101c28',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=28,pady=(26,6))
 tk.Label(root,text='Истории Ковчегов — по-русски',fg='white',bg='#101c28',font=('Segoe UI',23,'bold')).pack(anchor='w',padx=28)
 tk.Label(root,text='Survival Ascended  •  Записки, диалоги и кат-сцены',fg='#aab9ca',bg='#101c28',font=('Segoe UI',11)).pack(anchor='w',padx=28,pady=(6,24))
 tk.Label(root,text='Папка игры или библиотека Steam',fg='white',bg='#101c28',font=('Segoe UI',10)).pack(anchor='w',padx=28)
 frame=tk.Frame(root,bg='#101c28');frame.pack(fill='x',padx=28,pady=8)
 path=tk.StringVar(value='D:/SteamLibrary/steamapps/common/ARK Survival Ascended');ttk.Entry(frame,textvariable=path,font=('Segoe UI',11)).pack(side='left',fill='x',expand=True)
 ttk.Button(frame,text='Выбрать',command=lambda:path.set(filedialog.askdirectory() or path.get())).pack(side='right',padx=(10,0))
 tk.Label(root,text='Папка загрузки (нужно около 60 ГБ для частей и распаковки)',fg='white',bg='#101c28',font=('Segoe UI',10)).pack(anchor='w',padx=28,pady=(12,0))
 cache=tk.StringVar(value=str(Path.home()/'Downloads/ASA-Russian-Voice-Download'))
 download_frame=tk.Frame(root,bg='#101c28');download_frame.pack(fill='x',padx=28,pady=8)
 ttk.Entry(download_frame,textvariable=cache,font=('Segoe UI',11)).pack(side='left',fill='x',expand=True)
 ttk.Button(download_frame,text='Выбрать',command=lambda:cache.set(filedialog.askdirectory() or cache.get())).pack(side='right',padx=(10,0))
 status=tk.StringVar(value='Версия 1.1.0. Скачаю 16 частей, проверю и распакую автоматически. Оригиналы игры сохраняются.')
 tk.Label(root,textvariable=status,fg='#d8e4ec',bg='#101c28',wraplength=700,justify='left',font=('Segoe UI',10)).pack(anchor='w',padx=28,pady=20)
 bar=ttk.Progressbar(root,mode='indeterminate');bar.pack(fill='x',padx=28)
 buttons=tk.Frame(root,bg='#101c28');buttons.pack(fill='x',padx=28,pady=24)
 controls=[]
 def run(action):
  raw=path.get();cache_path=cache.get()
  for b in controls:b.configure(state='disabled')
  bar.start()
  def progress(text):root.after(0,status.set,text)
  def worker():
   try:
    if action=='install':
     game=locate_game(raw)
     if running():raise RuntimeError('Закройте ASA перед установкой.')
     from asa_download import prepare
     payload=package if (package/'manifest.json').exists() else prepare(Path(cache_path),progress)
     install(payload,game,progress)
    else:restore(Path(raw),progress)
   except Exception as e:root.after(0,messagebox.showerror,'Установка остановлена',str(e));progress('Операция остановлена. Причина показана в сообщении.')
   finally:
    def done():
     bar.stop()
     for b in controls:b.configure(state='normal')
    root.after(0,done)
  threading.Thread(target=worker,daemon=True).start()
 for label,action in [('Установить / обновить','install'),('Вернуть оригинал','restore')]:
  b=ttk.Button(buttons,text=label,command=lambda a=action:run(a));b.pack(side='left',padx=(0,12));controls.append(b)
 tk.Label(root,text='Закройте игру. Для загрузки нужен интернет. Повторный запуск продолжит прерванную загрузку.',fg='#8799ab',bg='#101c28',font=('Segoe UI',10)).pack(anchor='w',padx=28)
 root.mainloop()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--game',type=Path);p.add_argument('--package',type=Path);p.add_argument('--originals',type=Path);p.add_argument('--restore',action='store_true');a=p.parse_args()
 package=a.package or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent/'release/ASA-Russian-Voice')
 if a.game:
  if a.restore:restore(a.game)
  else:install(package,a.game,originals=a.originals)
 else:gui(package)
