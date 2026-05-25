#!/usr/bin/env python3
"""
交互式查询标准化账单数据。

用法:
  # 按分类查询
  python3 query_bill.py cleaned_data.json --category 餐饮美食 --top 5

  # 按商户查询
  python3 query_bill.py cleaned_data.json --merchant 蜜雪冰城

  # 按时间段和分类组合查询
  python3 query_bill.py cleaned_data.json --from 2026-01 --to 2026-05 --category 餐饮美食 --group-by month

  # 支付方式分布
  python3 query_bill.py cleaned_data.json --group-by payment

  # 月度趋势
  python3 query_bill.py cleaned_data.json --group-by month --type expense
"""

import argparse
import json
import sys
from collections import defaultdict


def load_data(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_data(data: list[dict], args) -> list[dict]:
    """Apply all filters."""
    result = []
    for r in data:
        if args.type and r["type"] != args.type:
            continue
        if args.category and r["category"] != args.category:
            continue
        if args.merchant and r["merchant_clean"] != args.merchant:
            continue
        if args.payment and r["payment_method"] != args.payment:
            continue
        if args.source and r["source"] != args.source:
            continue
        if args.date_from and r["date"] < args.date_from:
            continue
        if args.date_to and r["date"] > args.date_to:
            continue
        if args.keyword:
            kw = args.keyword.lower()
            if kw not in r.get("merchant_raw", "").lower() and \
               kw not in r.get("merchant_clean", "").lower() and \
               kw not in r.get("description", "").lower():
                continue
        result.append(r)
    return result


def group_and_summarize(data: list[dict], group_by: str) -> list[dict]:
    """Group by a dimension and summarize amounts."""
    groups: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0, "income": 0.0, "expense": 0.0})

    for r in data:
        if group_by == "month":
            key = r["date"][:7] if r["date"] else "未知"
        elif group_by == "year":
            key = r["date"][:4] if r["date"] else "未知"
        elif group_by == "category":
            key = r["category"]
        elif group_by == "merchant":
            key = r["merchant_clean"]
        elif group_by == "payment":
            key = r["payment_method"]
        elif group_by == "source":
            key = r["source"]
        elif group_by == "weekday":
            from datetime import datetime
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d")
                wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]
                key = wd
            except (ValueError, IndexError):
                key = "未知"
        else:
            key = "全部"

        groups[key]["amount"] += r["amount"]
        groups[key]["count"] += 1
        if r["type"] == "income":
            groups[key]["income"] += r["amount"]
        else:
            groups[key]["expense"] += r["amount"]

    total = sum(g["amount"] for g in groups.values())
    result = []
    for key, info in sorted(groups.items(),
                            key=lambda x: x[1]["amount"], reverse=True):
        result.append({
            "group": key,
            "amount": round(info["amount"], 2),
            "income": round(info["income"], 2),
            "expense": round(info["expense"], 2),
            "count": info["count"],
            "percent": round(info["amount"] / total * 100, 1) if total > 0 else 0,
        })
    return result


def format_table(results: list[dict], columns: list[str], headers: list[str],
                 args) -> str:
    """Format results as a markdown table."""
    total_amount = sum(r.get("amount", r.get("expense", 0)) for r in results)

    lines = []
    # Header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["------"] * len(headers)) + "|")

    for i, r in enumerate(results):
        row = []
        for col in columns:
            val = r.get(col, "")
            if col == "amount" or col == "expense" or col == "income":
                row.append(f"¥{val:,.2f}")
            elif col == "percent":
                row.append(f"{val}%")
            elif col == "rank":
                row.append(str(i + 1))
            else:
                row.append(str(val))
        lines.append("| " + " | ".join(row) + " |")

    # Summary
    lines.append("")
    lines.append(f"共 {len(results)} 项，合计 ¥{total_amount:,.2f}")

    return "\n".join(lines)


def format_merchant_detail(results: list[dict]) -> str:
    """Format detailed merchant transaction list."""
    lines = []
    lines.append("| 日期 | 金额 | 分类 | 支付方式 | 说明 |")
    lines.append("|------|------|------|----------|------|")
    for r in sorted(results, key=lambda x: x["date"], reverse=True):
        lines.append(
            f"| {r['date']} | ¥{r['amount']:.2f} | {r['category']} | "
            f"{r['payment_method']} | {r['description']} |"
        )
    lines.append("")
    total = sum(r["amount"] for r in results)
    lines.append(f"共 {len(results)} 笔，合计 ¥{total:.2f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="查询标准化账单数据")
    parser.add_argument("data_file", help="标准化 JSON 文件路径")

    # Filters
    parser.add_argument("--type", choices=["income", "expense"], help="交易类型")
    parser.add_argument("--category", help="分类筛选")
    parser.add_argument("--merchant", help="商户名筛选（精确匹配 merchant_clean）")
    parser.add_argument("--payment", help="支付方式筛选")
    parser.add_argument("--source", choices=["alipay", "wechat"], help="来源筛选")
    parser.add_argument("--date-from", dest="date_from", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", dest="date_to", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--keyword", help="关键词模糊搜索（商户名/商品说明）")

    # Grouping and output
    parser.add_argument("--group-by", dest="group_by",
                        choices=["category", "merchant", "month", "year",
                                 "payment", "source", "weekday"],
                        help="按维度汇总")
    parser.add_argument("--top", type=int, default=None, help="只显示前 N 条")
    parser.add_argument("--format", choices=["table", "markdown", "json", "csv"],
                        default="markdown", help="输出格式（默认 markdown）")

    args = parser.parse_args()

    data = load_data(args.data_file)
    filtered = filter_data(data, args)

    if not filtered:
        print("未找到匹配的记录。")
        sys.exit(1)

    # If merchant detail (no group-by, specific merchant)
    if args.merchant and not args.group_by:
        print(format_merchant_detail(filtered))
        return

    # Group and summarize
    if args.group_by:
        results = group_and_summarize(filtered, args.group_by)
    else:
        # No grouping: summary only
        total = sum(r["amount"] for r in filtered)
        incomes = sum(r["amount"] for r in filtered if r["type"] == "income")
        expenses = sum(r["amount"] for r in filtered if r["type"] == "expense")
        results = [{
            "group": "匹配记录",
            "amount": round(total, 2),
            "income": round(incomes, 2),
            "expense": round(expenses, 2),
            "count": len(filtered),
            "percent": 100.0,
        }]

    if args.top:
        results = results[:args.top]

    if args.format == "json":
        print(json.dumps({"filtered_count": len(filtered), "results": results},
                         ensure_ascii=False, indent=2))
    elif args.format == "csv":
        if results:
            keys = list(results[0].keys())
            print(",".join(keys))
            for r in results:
                print(",".join(str(r[k]) for k in keys))
    else:
        # markdown table
        if args.group_by:
            columns = list(results[0].keys())
            headers = {
                "group": "分组", "amount": "金额", "income": "收入",
                "expense": "支出", "count": "笔数", "percent": "占比"
            }
            print(format_table(results, columns,
                              [headers.get(c, c) for c in columns], args))
        else:
            print(format_table(results,
                              ["group", "count", "income", "expense"],
                              ["类型", "笔数", "收入", "支出"], args))


if __name__ == "__main__":
    main()
