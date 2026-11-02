"""（图像令牌预算场景）如何让图像令牌预算的复现条件与可验证性的度量结果能被第三方复核？用口径一致性比对输出每个分量的贡献。

测量：口径一致性比对（consistency_rate）；协议：对照实验。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

SEP = '\t'
MEASURE_FIELD = 'consistency_rate'
FAILURE_MODE = '版本漂移'


def _read_rows(path: str, limit: int = 0) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if SEP and SEP in line:
                label, _, payload = line.partition(SEP)
                rows.append((label.strip(), payload.strip()))
            else:
                rows.append(("", line.strip()))
            if limit and len(rows) >= limit:
                break
    return rows


def _nums(values: list[str]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac



def measure_consistency(rows: list[tuple[str, str]]) -> dict:
    """口径一致性：同一事实在不同表述下是否一致。"""
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for label, payload in rows:
        groups[label or "unlabeled"].append(payload)
    out: dict = {"metric": "consistency", "unit": "比例"}
    conflicts: list[dict] = []
    consistent = 0
    total = 0
    for label, values in sorted(groups.items()):
        if len(values) < 2:
            continue
        total += 1
        normalized = {v.strip().lower() for v in values}
        if len(normalized) == 1:
            consistent += 1
        else:
            conflicts.append({"group": label, "variants": sorted(normalized)})
    out["consistency_rate"] = round(consistent / total, 4) if total else 0.0
    out["conflict_groups"] = conflicts
    out["passed"] = (total == 0) or out["consistency_rate"] >= 0.95
    return out



def measure(rows: list[tuple[str, str]]) -> dict:
    """按测量族分派到具体测量函数。"""
    return measure_consistency(rows)



def run_protocol(measure, rows: list[tuple[str, str]], args: argparse.Namespace) -> dict:
    """对照实验：按标签分组测量，并列出组间差异。"""
    buckets: dict[str, list[tuple[str, str]]] = {}
    for label, payload in rows:
        buckets.setdefault(label or "all", []).append((label, payload))
    groups = {name: measure(items) for name, items in sorted(buckets.items())}
    result = {"protocol": "controlled_comparison", "groups": groups,
              "group_count": len(groups)}
    values = [g.get('consistency_rate') for g in groups.values()
              if isinstance(g.get('consistency_rate'), (int, float))]
    if len(values) > 1:
        result["spread"] = round(max(values) - min(values), 6)
        result["max_group"] = max(groups, key=lambda k: groups[k].get('consistency_rate', 0))
    return result



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="（图像令牌预算场景）如何让图像令牌预算的复现条件与可验证性的度量结果能被第三方复核？用口径一致性比对输出每个分量的贡献。")
    ap.add_argument("--input", help="输入文件路径")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 行")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--threshold", type=float, default=0.0, help="判定阈值")
    ap.add_argument("--budget", type=int, default=50, help="预算条数")
    ap.add_argument("--bins", type=int, default=10, help="分桶数量")
    ap.add_argument("--components", default="", help="组件列表（逗号分隔）")
    args = ap.parse_args(argv)

    if not args.input:
        ap.print_help()
        return 0

    t0 = time.time()
    try:
        rows = _read_rows(args.input, args.limit)
    except OSError as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return 2

    measured = measure(rows)
    result = run_protocol(measure, rows, args)
    result["measure"] = measured
    result["row_count"] = len(rows)
    result["failure_mode"] = FAILURE_MODE
    result["elapsed_seconds"] = round(time.time() - t0, 4)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        value = measured.get(MEASURE_FIELD)
        print(f"读取 1 个文件，共 {result['row_count']} 条记录")
        print(f"{MEASURE_FIELD} = {value}")
        print(f"处理完成，耗时 {result['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
