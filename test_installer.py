import hashlib,json,uuid
from pathlib import Path
import asa_installer as api
root=Path(__file__).resolve().parent/'work/installer-tests'/str(uuid.uuid4());root.mkdir(parents=True)
game=root/'game';(game/'ShooterGame/Binaries/Win64').mkdir(parents=True);(game/'ShooterGame/Binaries/Win64/ArkAscended.exe').write_bytes(b'fixture')
content=game/'ShooterGame/Content';(content/'Movies').mkdir(parents=True);(content/'Paks').mkdir()
package=root/'package';(package/'Movies').mkdir(parents=True);(package/'Paks').mkdir()
original=b'original film';dub=b'russian film';pak=b'voice container'
(content/'Movies/scene.bk2').write_bytes(original);(package/'Movies/scene.bk2').write_bytes(dub);(package/'Paks/z_ASARussianVoice_P.pak').write_bytes(pak)
def sha(x):return hashlib.sha256(x).hexdigest()
m={'version':'test','files':[{'path':'Movies/scene.bk2','sha256':sha(dub),'original_sha256':sha(original)},{'path':'Paks/z_ASARussianVoice_P.pak','sha256':sha(pak)}]}
(package/'manifest.json').write_text(json.dumps(m));api.running=lambda:False
quiet=lambda x:None
api.install(package,game,quiet);assert (content/'Movies/scene.bk2').read_bytes()==dub
api.install(package,game,quiet) # idempotent
api.restore(game,quiet);assert (content/'Movies/scene.bk2').read_bytes()==original;assert not (content/'Paks/z_ASARussianVoice_P.pak').exists()
(package/'Movies/scene.bk2').write_bytes(b'corruption')
try:api.install(package,game,quiet);raise AssertionError('Corruption accepted')
except RuntimeError:pass
assert (content/'Movies/scene.bk2').read_bytes()==original
(package/'Movies/scene.bk2').write_bytes(dub);api.install(package,game,quiet)
new=b'new dub';(package/'Movies/scene.bk2').write_bytes(new);m['files'][0]['sha256']=sha(new);m['version']='test2';(package/'manifest.json').write_text(json.dumps(m));api.install(package,game,quiet)
assert (content/'Movies/scene.bk2').read_bytes()==new
api.restore(game,quiet);assert (content/'Movies/scene.bk2').read_bytes()==original
try:api.safe(root,'../escape');raise AssertionError('Traversal accepted')
except RuntimeError:pass
api.running=lambda:True
try:api.install(package,game,quiet);raise AssertionError('Running game accepted')
except RuntimeError:pass
print('PASS: install, repeat install, restore, corrupt payload, update, path containment, running-game guard')
