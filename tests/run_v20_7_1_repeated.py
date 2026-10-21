import subprocess,sys,os,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
results=[]
for round_no in (1,2):
 for name in ['auth','simulation','feature_test']:
  script=root/'tests'/f'run_v20_7_1_{name}.py'
  r=subprocess.run([sys.executable,'-u',str(script)],capture_output=True,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=180)
  (root/f'tests/round_{round_no}_{name}.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
  results.append({'round':round_no,'suite':name,'exit_code':r.returncode,'result':'PASS' if r.returncode==0 else 'FAIL'})
  print(json.dumps(results[-1]),flush=True)
  if r.returncode:print(r.stdout+r.stderr,flush=True)
(root/'REPEATED_TEST_RESULT_v20.7.1.json').write_text(json.dumps({'version':'20.7.1','runs':results,'result':'PASS' if all(r['exit_code']==0 for r in results) else 'FAIL'},indent=2),encoding='utf-8')
sys.exit(int(any(r['exit_code'] for r in results)))
