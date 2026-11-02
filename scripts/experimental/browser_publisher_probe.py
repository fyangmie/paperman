#!/usr/bin/env python3
"""Download through the user's dedicated, normally authenticated Chrome session."""
import argparse,json,sys,time,base64,hashlib,re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cdp import command
from pypdf import PdfReader
parser=argparse.ArgumentParser();parser.add_argument("--publisher",required=True,choices=["acs","rsc","wiley","elsevier"]);parser.add_argument("--limit",type=int,default=3)
args=parser.parse_args()
base=Path("polymer_corpus/publisher_repair_test");dest=base/"browser_pdfs";dest.mkdir(exist_ok=True)
selection=json.loads(Path("polymer_corpus/paperman_publisher_test/selection.json").read_text())["records"]
samples=[r for r in selection if r["publisher"]==args.publisher][:args.limit]
target=command("browser","Target.createTarget",{"url":"about:blank"})["result"]["targetId"]
results=[]
for item in samples:
 doi=item["doi"];row=dict(item);path=dest/(hashlib.sha256(doi.encode()).hexdigest()+".pdf")
 try:
  command(target,"Page.navigate",{"url":"https://doi.org/"+doi})
  for attempt in range(10):
   result=command(target,"Runtime.evaluate",{"expression":"({ready:document.readyState,title:document.title,links:Array.from(document.querySelectorAll('a[href]')).filter(a=>/article-pdf|\\/doi\\/pdf\\/|\\/pdfft/.test(a.href)).map(a=>a.href)})","returnByValue":True})["result"]["result"].get("value",{})
   if result.get("links"):break
   if "Just a moment" in result.get("title","") or "请稍候" in result.get("title",""):break
   time.sleep(1)
  if not result.get("links"):row.update(status="no_link_or_verification",title=result.get("title"))
  else:
   url=result["links"][0]
   expr="""(async()=>{try{const r=await fetch(URL,{credentials:'include',signal:AbortSignal.timeout(20000)});const b=new Uint8Array(await r.arrayBuffer());const pdf=new TextDecoder().decode(b.slice(0,5))==='%PDF-';let data=null;if(pdf){let s='';for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));data=btoa(s);}return {http_status:r.status,bytes:b.length,pdf,data};}catch(e){return {error:String(e)}}})()""".replace("URL",json.dumps(url))
   answer=command(target,"Runtime.evaluate",{"expression":expr,"awaitPromise":True,"returnByValue":True})["result"]["result"].get("value",{})
   data=answer.pop("data",None);row.update(answer)
   if data:
    path.write_bytes(base64.b64decode(data));reader=PdfReader(path)
    text="".join(p.extract_text() or "" for p in reader.pages[:20])
    match=re.sub(r"\s+","",doi.lower()) in re.sub(r"\s+","",text.lower())
    row.update(status="verified" if match else "needs_review",path=str(path),pages=len(reader.pages),doi_match=match)
   else:row["status"]="download_failed"
 except Exception as e:row.update(status="error",error=type(e).__name__)
 results.append(row);(base/(args.publisher+"_browser_results.json")).write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
 # Gate expansion after three attempts.
 if len(results)==3 and args.limit>3 and not all(r.get("status")=="verified" for r in results):break
