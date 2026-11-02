#!/usr/bin/env python3
"""Compare publisher PDF links with official PMC Open Data PDF delivery."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from paperman.paths import corpus_directory
from pypdf import PdfReader
from paperman.corpus.config import Settings, normalize_doi
from paperman.corpus.network import Client, safe_url
from paperman.corpus.store import atomic_write,json_bytes,now

OUTPUT=corpus_directory()
S3="https://pmc-oa-opendata.s3.amazonaws.com"


def read_pdf(response, paper, source, extra=None):
    row={"doi":paper["doi"],"publisher":paper["publisher"],"source":source,
         "http_status":response.http_status,"url":safe_url(response.url)}
    row.update(extra or {})
    if response.status!="success":
        row["status"]=response.status
        return row
    if not response.body.lstrip().startswith(b"%PDF-"):
        row["status"]="not_pdf"
        return row
    try:
        reader=PdfReader(io.BytesIO(response.body))
        pages=len(reader.pages)
        text="\n".join(page.extract_text() or "" for page in reader.pages[:20])
    except Exception as exc:
        row.update(status="pdf_parse_failed",error_type=type(exc).__name__)
        return row
    compact="".join(text.lower().split())
    matched="".join(paper["doi"].lower().split()) in compact
    row.update(pages=pages,text_characters=len(text),doi_verified=matched)
    if pages<2 or len(text)<2000 or not matched:
        row["status"]="pdf_needs_review"
        return row
    digest=hashlib.sha256(response.body).hexdigest()
    directory=OUTPUT/"pdf_documents"/hashlib.sha256(paper["doi"].encode()).hexdigest()
    atomic_write(directory/"article.pdf",response.body)
    atomic_write(directory/"article.txt",text.encode())
    row.update(status="success",path=str((directory/"article.pdf").relative_to(OUTPUT)),
               text_path=str((directory/"article.txt").relative_to(OUTPUT)),
               sha256=digest,size=len(response.body),
               validation="PDF parsed; >=2 pages; >=2000 extracted characters; DOI matched; manual completeness review pending")
    return row


def publisher_tests(papers):
    results=[]
    for publisher in ("springer_nature","acs","wiley"):
        selected={}
        for paper in sorted((p for p in papers.values() if p["publisher"]==publisher),
                            key=lambda p:(not p.get("selected",False),p["doi"])):
            kind="cc_licensed" if any("creativecommons.org/licenses/" in x.get("url","") for x in paper.get("licenses",[])) else "access_unknown"
            if kind in selected:
                continue
            links=[x["url"] for x in paper.get("links",[])
                   if "pdf" in x.get("content_type","").lower()
                   and "api." not in (urlsplit(x["url"]).hostname or "")]
            if links:
                selected[kind]=(paper,links[0])
            if len(selected)==2:
                break
        client=Client(Settings(interval=10,retries=0,timeout=20))
        try:
            for kind,(paper,url) in selected.items():
                response=client.get(url,publisher=publisher)
                row=read_pdf(response,paper,"publisher_pdf",{"sample_kind":kind})
                results.append(row)
                print(json.dumps(row,ensure_ascii=False),flush=True)
        finally:
            client.session.close()
    return results


def s3_url(url):
    if url.startswith("s3://pmc-oa-opendata/"):
        url=S3+"/"+url.split("s3://pmc-oa-opendata/",1)[1]
    if not url.startswith(S3+"/"):
        raise ValueError("Unexpected repository object host")
    return url


def repository_tests(papers, limit=4):
    matches=json.loads((OUTPUT/"reports/oa-repository-matches.json").read_text())["matches"]
    selected={}
    for match in matches:
        selected.setdefault(match["publisher"],match)
    ordered=list(selected.values())
    seen={m["doi"] for m in ordered}
    ordered.extend(m for m in matches if m["doi"] not in seen)
    index=OUTPUT/"reports/pdf-index.jsonl"
    previous={r["doi"]:r for r in (json.loads(x) for x in index.read_text().splitlines())} if index.exists() else {}
    client=Client(Settings(interval=1,retries=0,timeout=25))
    results=[]
    attempted=0
    try:
        for match in ordered:
            publisher=match["publisher"]
            doi=match["doi"]
            prior=previous.get(doi)
            if prior and (OUTPUT/prior["path"]).is_file():
                digest=hashlib.sha256((OUTPUT/prior["path"]).read_bytes()).hexdigest()
                if digest==prior["sha256"]:
                    results.append(dict(prior,status="skipped_valid"))
                    continue
            if attempted>=limit:
                continue
            attempted+=1
            listing=client.get(S3+"/",params={"list-type":"2","prefix":match["pmcid"]+".","delimiter":"/","max-keys":100})
            if listing.status!="success":
                row={"doi":doi,"publisher":publisher,"source":"pmc_cloud_pdf","status":listing.status,
                     "http_status":listing.http_status,"stage":"version_listing"}
                results.append(row); print(json.dumps(row),flush=True); continue
            try:
                tree=ET.fromstring(listing.body)
                prefixes=[n.text for n in tree.iter() if n.tag.rsplit("}",1)[-1]=="Prefix"
                          and n.text and n.text.startswith(match["pmcid"]+".") and n.text.endswith("/")]
            except ET.ParseError:
                prefixes=[]
            candidates=[]
            for prefix in prefixes[:4]:
                version=prefix.rstrip("/")
                response=client.get(S3+"/"+prefix+version+".json")
                if response.status!="success":
                    continue
                try:
                    metadata=response.json()
                    if normalize_doi(metadata.get("doi",""))!=doi:
                        continue
                    if str(metadata.get("is_pmc_openaccess","")).lower() not in ("yes","true","y","1"):
                        continue
                    if metadata.get("pdf_url"):
                        candidates.append((metadata,s3_url(metadata["pdf_url"])))
                except (ValueError,TypeError):
                    continue
            if not candidates:
                row={"doi":doi,"publisher":publisher,"source":"pmc_cloud_pdf",
                     "status":"no_eligible_pdf","versions_listed":len(prefixes)}
                results.append(row); print(json.dumps(row),flush=True); continue
            metadata,url=sorted(candidates,key=lambda x:str(x[0].get("is_manuscript","")).lower() in ("yes","true"))[0]
            response=client.get(url)
            expected=parse_qs(urlsplit(url).query).get("md5",[""])[0]
            if response.status=="success" and expected and hashlib.md5(response.body).hexdigest()!=expected:
                row={"doi":doi,"publisher":publisher,"source":"pmc_cloud_pdf","status":"checksum_mismatch"}
            else:
                row=read_pdf(response,papers[doi],"pmc_cloud_pdf",
                             {"pmcid":match["pmcid"],"license_code":metadata.get("license_code"),
                              "is_manuscript":metadata.get("is_manuscript")})
            results.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    finally:
        client.session.close()
    return results


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=["publisher","repository","both"],default="both")
    parser.add_argument("--repository-limit",type=int,default=4,
                        help="Maximum new repository PDF attempts; valid existing files are skipped")
    parser.add_argument("--output", "-o", type=Path, default=corpus_directory())
    args = parser.parse_args()
    OUTPUT = args.output
    if args.repository_limit<1:
        parser.error("--repository-limit must be positive")
    papers={p["doi"]:p for p in (json.loads(x) for x in (OUTPUT/"manifest.jsonl").read_text().splitlines())}
    results=[]
    if args.mode in ("publisher","both"):
        results.extend(publisher_tests(papers))
    if args.mode in ("repository","both"):
        results.extend(repository_tests(papers,args.repository_limit))
    report={"generated_at":now(),"results":results,
            "counts":dict(Counter(r["source"]+":"+r["status"] for r in results)),
            "note":"Small purposive feasibility sample; no publisher credentials used; PDF parsed and DOI checked, manual completeness review remains."}
    atomic_write(OUTPUT/"reports/pdf-probe.json",json_bytes(report))
    stamp=report["generated_at"].replace(":","").replace("+","_")
    atomic_write(OUTPUT/"reports/pdf-probes"/(stamp+".json"),json_bytes(report))
    index=OUTPUT/"reports/pdf-index.jsonl"
    previous={r["doi"]:r for r in (json.loads(x) for x in index.read_text().splitlines())} if index.exists() else {}
    previous.update({r["doi"]:r for r in results if r["status"]=="success"})
    atomic_write(index,("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in previous.values())).encode())
    print(json.dumps({"counts":report["counts"],"indexed_pdfs":len(previous)},ensure_ascii=False))


if __name__=="__main__":
    main()
