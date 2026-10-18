import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_re.common import ROOT, now, write_json
from unified_re.retrieval import Index

CASES = [
    ("静态分析这个 Electron 程序的模块依赖和 IPC", "javascript.static"),
    ("Map how code pieces in a shipped desktop bundle fit together without starting the program.", "javascript.static"),
    ("先别启动这个桌面程序，梳理其中脚本互相衔接的关系", "javascript.static"),
    ("Bring the unreadable processor operations back into human understandable routines.", "native.analyze"),
    ("看看手机安装文件里的清单、类和方法", "android.inspect"),
    ("Read compiled C sharp metadata and intermediate language instructions", "managed.inspect"),
    ("给我一份番茄炒蛋菜谱", None),
    ("Plan a birthday party and recommend a chocolate cake recipe", None),
    ("预测明天下午的天气并推荐雨伞", None),
]


def main():
    index = Index()
    records = []
    for query, expected in CASES:
        result = index.search(query, 12)
        passed = result["status"] == "no_match" if expected is None else any(expected in c["capabilities"] for c in result["candidates"])
        record = {"query": query, "expected_capability": expected, "passed": passed, "result": result}
        records.append(record)
        print(json.dumps({"query": query, "passed": passed, "status": result["status"], "top": [(c["id"], round(c["semantic_similarity"], 3)) for c in result["candidates"][:5]]}, ensure_ascii=True))
    write_json(ROOT / "reports/retrieval-evaluation.json", {"observed_at": now(), "passed": all(r["passed"] for r in records), "cases": records, "scope": "Explicit local acceptance cases, not a calibrated confidence or general success-rate estimate"})
    if not all(r["passed"] for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
