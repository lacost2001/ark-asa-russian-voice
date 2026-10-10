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
 from asa_maps import chosen_files,prepare_maps,validate_legacy,deactivate_legacy
 resources=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
 catalog=json.loads((resources/'maps.json').read_text('utf-8'))
 settings_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ASA-Russian-Voice/settings.json'
 try:settings=json.loads(settings_path.read_text('utf-8'))
 except Exception:settings={}
 root=tk.Tk();root.title('ASA — Русская озвучка 1.2.0');root.geometry('820x780');root.minsize(740,720);root.configure(bg='#101c28')
 style=ttk.Style();style.theme_use('clam');style.configure('TButton',font=('Segoe UI',10),padding=8)
 tk.Label(root,text='Истории Ковчегов — по-русски',fg='white',bg='#101c28',font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=(20,4))
 tk.Label(root,text='Survival Ascended  •  Скачиваются только выбранные карты',fg='#57d6c7',bg='#101c28',font=('Segoe UI',11)).pack(anchor='w',padx=24,pady=(0,12))
 controls=[]
 def folder(label,initial):
  tk.Label(root,text=label,fg='white',bg='#101c28').pack(anchor='w',padx=24)
  row=tk.Frame(root,bg='#101c28');row.pack(fill='x',padx=24,pady=6);var=tk.StringVar(value=initial)
  field=ttk.Entry(row,textvariable=var);field.pack(side='left',fill='x',expand=True)
  btn=ttk.Button(row,text='Выбрать',command=lambda:var.set(filedialog.askdirectory() or var.get()));btn.pack(side='right',padx=(8,0));controls.extend([field,btn]);return var
 path=folder('Папка ASA или библиотека Steam',settings.get('game','D:/SteamLibrary/steamapps/common/ARK Survival Ascended'))
 cache=folder('Папка загрузки',settings.get('cache',str(Path.home()/'Downloads/ASA-Voice-Maps')))
 frame=tk.Frame(root,bg='#182939');frame.pack(fill='both',expand=True,padx=24,pady=12)
 canvas=tk.Canvas(frame,bg='#182939',highlightthickness=0);scroll=ttk.Scrollbar(frame,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
 scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True);inner=tk.Frame(canvas,bg='#182939');canvas.create_window((0,0),window=inner,anchor='nw');inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
 selected={};total=tk.StringVar()
 def estimate():
  keys=[k for k,v in selected.items() if v.get()]
  amount=sum(x['size'] for x in chosen_files(catalog,keys)) if keys else 0
  total.set(f'Выбрано: {amount/1024**3:.2f} ГБ. Уже скачанные файлы используются повторно.')
 order=['TheIsland','ScorchedEarth','Aberration','Extinction','Genesis1','Genesis2','LostColony','BobTales','Ragnarok','Valguero','CrystalIsles','LostIsland','Fjordur']
 for key in order:
  if key not in catalog['groups']:continue
  group=catalog['groups'][key];var=tk.BooleanVar(value=key in settings.get('maps',['TheIsland']));selected[key]=var
  check=tk.Checkbutton(inner,text=f"{group['title']} — {group['size']/1024**3:.2f} ГБ",variable=var,command=estimate,bg='#182939',fg='white',selectcolor='#284354',activebackground='#182939',activeforeground='white',font=('Segoe UI',11),anchor='w');check.pack(fill='x',padx=12,pady=2);controls.append(check)
 estimate();tk.Label(root,textvariable=total,fg='#57d6c7',bg='#101c28').pack(anchor='w',padx=24)
 tk.Label(root,text='Общие реплики подключаются автоматически. Снятие галочки не удаляет установленную карту.',fg='#aab9ca',bg='#101c28',wraplength=760,justify='left').pack(anchor='w',padx=24,pady=5)
 status=tk.StringVar(value='Закройте ASA перед установкой. Оригиналы сохраняются.');tk.Label(root,textvariable=status,fg='white',bg='#101c28',wraplength=760,justify='left').pack(anchor='w',padx=24,pady=8)
 bar=ttk.Progressbar(root,mode='indeterminate');bar.pack(fill='x',padx=24)
 buttons=tk.Frame(root,bg='#101c28');buttons.pack(fill='x',padx=24,pady=16)
 busy=[False]
 def run(action):
  raw=path.get();cache_path=cache.get();keys=[k for k,v in selected.items() if v.get()]
  if action=='install' and not keys:messagebox.showerror('Выберите карту','Отметьте хотя бы одну карту.');return
  busy[0]=True
  for widget in controls:widget.configure(state='disabled')
  bar.start()
  def progress(text):root.after(0,status.set,text)
  def worker():
   try:
    game=locate_game(raw)
    if running():raise RuntimeError('Закройте ASA перед установкой.')
    settings_path.parent.mkdir(parents=True,exist_ok=True);atomic_json(settings_path,dict(game=raw,cache=cache_path,maps=keys))
    if action=='install':
     validate_legacy(catalog,game)
     payload=prepare_maps(catalog,keys,Path(cache_path),game,progress)
     install(payload,game,progress)
     deactivate_legacy(catalog,game)
     progress('Готово. Выбранные карты установлены. Можно запускать ASA.')
    else:restore(game,progress)
   except Exception as error:
    text=str(error);root.after(0,lambda t=text:messagebox.showerror('Операция остановлена',t));progress(text)
   finally:
    def done():
     busy[0]=False;bar.stop()
     for widget in controls:widget.configure(state='normal')
    root.after(0,done)
  threading.Thread(target=worker,daemon=True).start()
 for label,action in [('Скачать / установить выбранное','install'),('Вернуть все оригиналы','restore')]:
  button=ttk.Button(buttons,text=label,command=lambda a=action:run(a));button.pack(side='left',padx=(0,10));controls.append(button)
 def close():
  if busy[0]:messagebox.showinfo('Операция выполняется','Дождитесь завершения операции.');return
  root.destroy()
 root.protocol('WM_DELETE_WINDOW',close);root.mainloop()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--game',type=Path);p.add_argument('--package',type=Path);p.add_argument('--originals',type=Path);p.add_argument('--restore',action='store_true');a=p.parse_args()
 package=a.package or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent/'release/ASA-Russian-Voice')
 if a.game:
  if a.restore:restore(a.game)
  else:install(package,a.game,originals=a.originals)
 else:gui(package)
