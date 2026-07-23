"""
paperman 全面功能测试
执行: pixi run python tests/run_all_tests.py
"""
import subprocess
import sys
from pathlib import Path

PAPERMAN = ["pixi", "run", "paperman"]
PASS = 0
FAIL = 0
KNOWN_DOIS = [
    "10.1073/pnas.2407765121",
    "10.1038/s41586-026-10644-y",
    "10.1186/s13054-026-05843-y",
    "10.3390/jcm15134884",
    "10.1126/sciadv.adw6666",
    "10.1016/j.cell.2024.09.021",
    "10.1186/s12931-025-03240-7",
    "10.1126/scitranslmed.adt6387",
]


def run(cmd, desc="", timeout=60):
    global PASS, FAIL
    full_cmd = PAPERMAN + cmd
    print(f"\n  [{desc}] $ {' '.join(full_cmd)}")
    try:
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout, cwd=PROJECT_DIR)
        ok = r.returncode == 0
        status = "✅" if ok else "❌"
        print(f"  {status} exit={r.returncode}")
        if not ok:
            print(f"     stderr: {r.stderr[:200]}")
        PASS += ok
        FAIL += not ok
        return r
    except subprocess.TimeoutExpired:
        print(f"  ⏰ 超时 ({timeout}s)")
        FAIL += 1
        return None


PROJECT_DIR = Path(__file__).resolve().parent.parent

print("=" * 60)
print("paperman 全面功能测试")
print("=" * 60)

# ── help ──
run(["--help"], "help")

# ── download: --no-pdf（不依赖网络下载PDF，只测元数据）──
for doi in KNOWN_DOIS[:3]:
    run(["download", doi, "--no-pdf", "-f"], f"download --no-pdf {doi[:30]}")

# ── download: 通过 PMID ──
run(["download", "40296124", "--no-pdf", "-f"], "download by PMID 40296124")

# ── download: 通过 arXiv ID ──
run(["download", "2505.13400", "--no-pdf", "-f"], "download by arXiv 2505.13400")

# ── download: 标题搜索 ──
run(["download", "PIEZO1 liver regeneration", "--no-pdf", "-f"], "download by title")

# ── download: --bib ──
run(["download", KNOWN_DOIS[0], "--no-pdf", "--bib", "-f"], "download --bib")

# ── download: --force ──
run(["download", KNOWN_DOIS[0], "--no-pdf", "-f"], "download --force")

# ── search: crossref ──
run(["search", "piezo1 mechanosensing", "-l", "3"], "search crossref")

# ── search: crossref --csv ──
run(["search", "liver regeneration", "-l", "3", "--csv"], "search crossref --csv")

# ── search: pubmed ──
run(["search", "piezo1", "--source", "pubmed", "-l", "3", "--csv"], "search pubmed --csv")

# ── search: all ──
run(["search", "mechanosensing", "--source", "all", "-l", "3", "--csv"], "search all --csv")

# ── list ──
run(["list"], "list cache")

# ── list --query ──
run(["list", "-q", "piezo1"], "list --query piezo1")

# ── show ──
run(["show", KNOWN_DOIS[0]], "show by DOI")
run(["show", "40296124"], "show by PMID")

# ── stats ──
run(["stats"], "stats")

# ── config ──
run(["config"], "config show")

# ── config --set ──
run(["config", "--set", "output", "--value", "/tmp/paperman-test"], "config set output")

# ── config --show ──
run(["config"], "config verify")

# ── 恢复配置 ──
run(["config", "--set", "output", "--value", str(Path.home() / "Documents" / "papers")], "config reset output")

# ── batch: 创建临时文件并测试 ──
tmpfile = Path("/tmp/paperman-test-dois.txt")
tmpfile.write_text("\n".join(KNOWN_DOIS[:2]))
run(["batch", str(tmpfile), "--no-pdf", "-o", "/tmp/paperman-batch"], "batch 2 DOIs")

# ── batch --resume: 应该跳过已下载的 ──
# 先用 --no-pdf 跑过一次后缓存有了元数据但没有PDF
# --resume 会检查 pdf_path，由于没有PDF所以不会跳过
# 这个测试验证 --resume 不会报错
run(["batch", str(tmpfile), "--no-pdf", "-o", "/tmp/paperman-batch", "--resume"], "batch --resume")

# ── prune --dry-run ──
run(["prune", "--dry-run"], "prune --dry-run")

# ── prune --all --dry-run ──
run(["prune", "--all", "--dry-run"], "prune --all --dry-run")

# ── 清理临时文件 ──
tmpfile.unlink(missing_ok=True)

# ── 总结 ──
print("\n" + "=" * 60)
print(f"  通过: {PASS}  |  失败: {FAIL}  |  总数: {PASS + FAIL}")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
