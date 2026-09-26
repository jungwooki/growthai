"""Build a local, private deployment handoff; never upload or include secrets."""
from pathlib import Path
import hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'artifacts/mps-growth-web.zip'
allow=['backend/reference_storage.py','backend/mps_guidance.py','backend/vision_stages.py','backend/centers.py','headquarters.html','frontend/js/headquarters.js','frontend/css/centers.css','backend/budget.py','frontend/js/budget.js','backend/result_extraction.py','frontend/js/result-review.js','backend/media_storage.py','frontend/js/media-upload.js','docs/private-upload-setup.md','vercel.json','pyproject.toml','uv.lock','.python-version','.vercelignore','frontend/css/workspace.css','frontend/assets/mps-symbol.png','backend/__init__.py','backend/server.py','server.py','backend/web_access.py','backend/vision_report.py','backend/growth_history.py','index.html','workspace.html','frontend/css/landing.css','frontend/js/login.js','frontend/js/app.js','frontend/js/memo-parser.js','frontend/js/clinical-report.js','frontend/css/styles.css','requirements.txt','Dockerfile','.dockerignore','render.yaml','.env.example','DEPLOY.md','data/manifest.json','data/pages.json','data/growth.json']
manifest=json.loads((ROOT/'data/manifest.json').read_text())
allow += ['data/sources/'+s['name'] for s in manifest]
OUTPUT.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(OUTPUT,'w',zipfile.ZIP_DEFLATED) as z:
 for relative in allow:z.write(ROOT/relative,relative)
 z.writestr('.gitignore','.env\n.env.*\n!.env.example\n.venv/\n__pycache__/\ndata/sources/\nartifacts/\n')
with zipfile.ZipFile(OUTPUT) as z:
 assert '.env' not in z.namelist()
 assert 'backend/reference_storage.py' in z.namelist()
 for source in manifest:
  raw=z.read('data/sources/'+source['name'])
  assert len(raw)==source['size'] and hashlib.sha256(raw).hexdigest()==source['sha256']
 assert all(not n.startswith('.venv/') for n in z.namelist())
print(f'{len(allow)+1} allowlisted files packaged; no .env or key included; {OUTPUT.stat().st_size//1024//1024} MB')
