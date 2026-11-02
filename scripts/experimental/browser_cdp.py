#!/usr/bin/env python3
"""Send one CDP command to the dedicated Windows Paperman Chrome window."""
import argparse,base64,json,subprocess
from pathlib import Path

def command(target,method,params):
    request={"id":1,"method":method,"params":params}
    payload=base64.b64encode(json.dumps(request,ensure_ascii=False).encode()).decode()
    script=Path(__file__).with_suffix(".ps1").read_text()
    script=script.replace("param([string]$TargetId, [string]$RequestBase64)",
                          "$TargetId = '"+target+"'; $RequestBase64 = '"+payload+"'")
    encoded=base64.b64encode(script.encode("utf-16-le")).decode()
    result=subprocess.run(["/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                           "-NoProfile","-NonInteractive","-EncodedCommand",encoded],
                          capture_output=True,timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("gb18030",errors="replace")[:1600])
    for line in reversed(result.stdout.decode("utf-8",errors="replace").splitlines()):
        if line.startswith("{"):
            data=json.loads(line)
            if data.get("id")==1:
                return data
    raise RuntimeError("No CDP reply")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",required=True)
    parser.add_argument("--method",required=True)
    parser.add_argument("--params",default="{}")
    args=parser.parse_args()
    if not (args.target=="browser" or all(c in "0123456789ABCDEFabcdef" for c in args.target)):
        parser.error("Invalid target")
    print(json.dumps(command(args.target,args.method,json.loads(args.params)),ensure_ascii=False))

if __name__=="__main__":
    main()
