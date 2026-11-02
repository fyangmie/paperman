#!/usr/bin/env python3
"""Isolated publisher-path regression; uses Paperman fetcher/downloader, not batch."""
import sys,os,json,datetime,hashlib,re
from pathlib import Path

from paperman.fetchers.crossref import CrossrefFetcher
from paperman.downloaders.publisher import PublisherDownloader
from pypdf import PdfReader
base=Path("polymer_corpus/publisher_repair_test");base.mkdir(exist_ok=True)
dest=base/"pdfs";dest.mkdir(exist_ok=True)
os.environ["PAPERMAN_DIAGNOSTICS"]=str(base/"requests.jsonl")
selection=json.loads(Path("polymer_corpus/paperman_publisher_test/selection.json").read_text())["records"]
samples=[{"publisher":"springer_control","doi":"10.1007/s00289-025-05639-0"}]+[r for r in selection if r["publisher"]!="springer_nature" and r["publisher_sample_index"]<=3]
records=[]
for item in samples:
 row=dict(item)
 try:
  paper=CrossrefFetcher()._fetch_by_doi(item["doi"])
  if paper is None:row["status"]="metadata_failed"
  else:
   os.environ["PAPERMAN_CURRENT_SOURCE"]="publisher"
   dl=PublisherDownloader();url=dl.get_pdf_url(paper)
   row["resolved_url"]=url
   if not url:row["status"]="no_pdf_link"
   else:
    paper.pdf_url=url;pdf=dl.download(paper,dest)
    if pdf is None:row["status"]="download_failed"
    else:
     reader=PdfReader(pdf);text=" ".join(p.extract_text() or "" for p in reader.pages[:20])
     normalize=lambda s:re.sub(r"\s+","",s).lower()
     doi_match=normalize(item["doi"]) in normalize(text)
     title_match=bool(paper.title) and normalize(paper.title) in normalize(text)
     row.update(status="verified" if doi_match or title_match else "needs_review",pages=len(reader.pages),doi_match=doi_match,title_match=title_match,path=str(pdf))
     paper.pdf_path=pdf;paper.pdf_source="publisher";pdf.with_suffix(".yaml").write_text(paper.to_yaml())
 except Exception as exc:row.update(status="error",error=type(exc).__name__)
 records.append(row)
 (base/"results.json").write_text(json.dumps({"records":records,"complete":len(records)==len(samples)},indent=2))
 print(json.dumps(row),flush=True)
