import os,sys,json,time,subprocess,collections,hashlib
from pathlib import Path
base=Path(sys.argv[1]);selection=json.loads((base/"selection.json").read_text())["records"]
with (base/"console.log").open("w") as log:
 child=subprocess.Popen([sys.executable,"-u","paperman/scripts/bounded_batch.py",str(base/"dois.txt"),"--output",str(base/"results"),"--timeout","180"],stdout=log,stderr=subprocess.STDOUT)
 run=json.loads((base/"run.json").read_text());run["worker_pid"]=child.pid;(base/"run.json").write_text(json.dumps(run,indent=2))
 while True:
  groups={p:{"selected":20,"attempted":0,"downloaded":0,"timeout":0,"failed":0} for p in sorted({r["publisher"] for r in selection})}
  sources=collections.Counter();rows=[]
  for item in selection:
   f=base/"results"/hashlib.sha256(item["doi"].encode()).hexdigest()/"result.json"
   if not f.exists():continue
   try:r=json.loads(f.read_text())
   except (OSError,json.JSONDecodeError):continue
   r["publisher"]=item["publisher"];rows.append(r);g=groups[item["publisher"]];g["attempted"]+=1
   if r["status"]=="downloaded":g["downloaded"]+=1;sources[r.get("download_source") or "unknown"]+=1
   elif r["status"]=="timeout":g["timeout"]+=1
   else:g["failed"]+=1
  done=child.poll() is not None
  summary={"state":"completed" if done and len(rows)==100 else "stopped" if done else "running","selected":100,"attempted":len(rows),"downloaded":sum(g["downloaded"] for g in groups.values()),"groups":groups,"download_sources":dict(sources),"timeout_seconds":180,"note":"Timeout means pipeline interrupted by deadline, not all sources exhausted. Downloaded means saved PDF; content audit is separate."}
  tmp=base/"progress.tmp";tmp.write_text(json.dumps(summary,indent=2));tmp.replace(base/"progress.json")
  if done:
   (base/"summary.json").write_text(json.dumps(summary,indent=2));break
  time.sleep(20)
