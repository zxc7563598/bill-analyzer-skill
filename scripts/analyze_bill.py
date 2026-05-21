#!/usr/bin/env python3
"""分析标准化账单数据，生成多维分析报告。"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta


def load_data(filepath: str) -> list[dict]:
    """加载标准化账单 JSON。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        print("错误: 数据为空", file=sys.stderr)
        sys.exit(1)
    return data


def summarize(data: list[dict]) -> dict:
    """基础汇总统计。"""
    total_income = sum(r["amount"] for r in data if r["type"] == "income")
    total_expense = sum(r["amount"] for r in data if r["type"] == "expense")
    dates = sorted(r["date"] for r in data if r["date"])
    return {
        "total_records": len(data),
        "date_start": dates[0] if dates else None,
        "date_end": dates[-1] if dates else None,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "balance": round(total_income - total_expense, 2),
    }


def monthly_trend(data: list[dict]) -> list[dict]:
    """月度收支趋势。"""
    months: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0, "count": 0})
    for r in data:
        if not r["date"]:
            continue
        month = r["date"][:7]
        if r["type"] == "income":
            months[month]["income"] += r["amount"]
        else:
            months[month]["expense"] += r["amount"]
        months[month]["count"] += 1

    result = []
    for month in sorted(months.keys()):
        m = months[month]
        result.append({
            "month": month,
            "income": round(m["income"], 2),
            "expense": round(m["expense"], 2),
            "net": round(m["income"] - m["expense"], 2),
            "count": m["count"],
        })
    return result


def category_breakdown(data: list[dict], top_n: int = 8) -> list[dict]:
    """支出分类占比分析。"""
    cats: dict[str, float] = defaultdict(float)
    for r in data:
        if r["type"] == "expense":
            cats[r["category"]] += r["amount"]

    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    total = sum(c[1] for c in sorted_cats)

    result = []
    others_amount = 0.0
    for i, (cat, amount) in enumerate(sorted_cats):
        if i < top_n:
            result.append({
                "category": cat,
                "amount": round(amount, 2),
                "percent": round(amount / total * 100, 1) if total > 0 else 0,
            })
        else:
            others_amount += amount

    if others_amount > 0:
        result.append({
            "category": "其他",
            "amount": round(others_amount, 2),
            "percent": round(others_amount / total * 100, 1) if total > 0 else 0,
        })

    return result


def top_merchants(data: list[dict], top_n: int = 10) -> list[dict]:
    """支出 TOP 商户。"""
    merchants: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0, "category": ""})
    for r in data:
        if r["type"] == "expense":
            key = r["merchant_clean"]
            merchants[key]["amount"] += r["amount"]
            merchants[key]["count"] += 1
            merchants[key]["category"] = r["category"]

    sorted_merchants = sorted(merchants.items(), key=lambda x: x[1]["amount"], reverse=True)
    return [
        {
            "merchant": name,
            "amount": round(info["amount"], 2),
            "count": info["count"],
            "category": info["category"],
        }
        for name, info in sorted_merchants[:top_n]
    ]


def daily_trend(data: list[dict]) -> list[dict]:
    """每日支出趋势。"""
    days: dict[str, float] = defaultdict(float)
    for r in data:
        if r["type"] == "expense" and r["date"]:
            days[r["date"]] += r["amount"]

    return [{"date": d, "amount": round(amt, 2)} for d, amt in sorted(days.items())]


def payment_method_breakdown(data: list[dict]) -> list[dict]:
    """支付方式分布。"""
    pm: dict[str, float] = defaultdict(float)
    for r in data:
        method = r.get("payment_method", "未知")
        pm[method] += r["amount"]

    sorted_pm = sorted(pm.items(), key=lambda x: x[1], reverse=True)
    total = sum(p[1] for p in sorted_pm)
    return [
        {
            "method": name,
            "amount": round(amount, 2),
            "percent": round(amount / total * 100, 1) if total > 0 else 0,
        }
        for name, amount in sorted_pm
    ]


def income_source_breakdown(data: list[dict]) -> list[dict]:
    """收入来源分析。"""
    sources: dict[str, float] = defaultdict(float)
    for r in data:
        if r["type"] == "income":
            key = r["merchant_clean"] or r["merchant_raw"]
            sources[key] += r["amount"]

    sorted_src = sorted(sources.items(), key=lambda x: x[1], reverse=True)
    return [{"source": name, "amount": round(amt, 2)} for name, amt in sorted_src[:10]]


def weekday_analysis(data: list[dict]) -> dict:
    """按星期几分析消费习惯。"""
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekdays: dict[int, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0})

    for r in data:
        if r["type"] == "expense" and r["date"]:
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d")
                wd = d.weekday()
                weekdays[wd]["amount"] += r["amount"]
                weekdays[wd]["count"] += 1
            except ValueError:
                pass

    return {
        "labels": weekday_names,
        "amounts": [round(weekdays[i]["amount"], 2) for i in range(7)],
        "counts": [weekdays[i]["count"] for i in range(7)],
    }


def source_breakdown(data: list[dict]) -> dict:
    """按来源（支付宝/微信）统计。"""
    sources: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0, "count": 0})
    for r in data:
        src = r.get("source", "未知")
        if r["type"] == "income":
            sources[src]["income"] += r["amount"]
        else:
            sources[src]["expense"] += r["amount"]
        sources[src]["count"] += 1
    return {
        k: {"income": round(v["income"], 2), "expense": round(v["expense"], 2), "count": v["count"]}
        for k, v in sources.items()
    }


def yearly_trend(data: list[dict]) -> list[dict]:
    """年度收支趋势。"""
    years: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0, "count": 0})
    for r in data:
        if not r["date"]:
            continue
        year = r["date"][:4]
        if r["type"] == "income":
            years[year]["income"] += r["amount"]
        else:
            years[year]["expense"] += r["amount"]
        years[year]["count"] += 1
    return [
        {"year": y, "income": round(v["income"], 2), "expense": round(v["expense"], 2),
         "net": round(v["income"] - v["expense"], 2), "count": v["count"]}
        for y, v in sorted(years.items())
    ]


def format_report(data: list[dict]) -> str:
    """生成 Markdown 格式的分析报告。"""
    s = summarize(data)
    monthly = monthly_trend(data)
    yearly = yearly_trend(data)
    sources = source_breakdown(data)
    categories = category_breakdown(data)
    merchants = top_merchants(data)
    payments = payment_method_breakdown(data)
    weekday = weekday_analysis(data)
    income_sources = income_source_breakdown(data)

    lines = []

    # ── 总览 ──
    lines.append("## 账单总览")
    lines.append("")
    date_range = f"{s['date_start']} ~ {s['date_end']}" if s["date_start"] else "未知"
    lines.append(f"- 账单周期: {date_range}")
    lines.append(f"- 交易笔数: {s['total_records']} 笔")
    lines.append(f"- 总收入: ¥{s['total_income']:,.2f}")
    lines.append(f"- 总支出: ¥{s['total_expense']:,.2f}")
    lines.append(f"- 结余: ¥{s['balance']:,.2f}")
    lines.append("")

    # ── 来源构成 ──
    lines.append("## 来源构成")
    lines.append("")
    lines.append("| 来源 | 支出 | 收入 | 笔数 |")
    lines.append("|------|------|------|------|")
    for src_name, info in sources.items():
        label = "支付宝" if src_name == "alipay" else "微信" if src_name == "wechat" else src_name
        lines.append(f"| {label} | ¥{info['expense']:,.2f} | ¥{info['income']:,.2f} | {info['count']} |")
    lines.append("")

    # ── 月度趋势 ──
    lines.append("## 月度趋势")
    lines.append("")
    lines.append("| 月份 | 收入 | 支出 | 结余 | 笔数 |")
    lines.append("|------|------|------|------|------|")
    for m in monthly:
        lines.append(f"| {m['month']} | ¥{m['income']:,.2f} | ¥{m['expense']:,.2f} | ¥{m['net']:,.2f} | {m['count']} |")
    if monthly:
        avg_expense = sum(m["expense"] for m in monthly) / len(monthly)
        lines.append("")
        lines.append(f"月均支出: ¥{avg_expense:,.2f}")
    lines.append("")

    # ── 年度趋势 ──
    if len(yearly) > 1:
        lines.append("## 年度趋势")
        lines.append("")
        lines.append("| 年份 | 收入 | 支出 | 结余 | 笔数 |")
        lines.append("|------|------|------|------|------|")
        for y in yearly:
            lines.append(f"| {y['year']} | ¥{y['income']:,.2f} | ¥{y['expense']:,.2f} | ¥{y['net']:,.2f} | {y['count']} |")
        lines.append("")

    # ── 分类占比 ──
    lines.append("## 支出分类占比")
    lines.append("")
    total_expense = sum(c["amount"] for c in categories)
    lines.append("| 分类 | 金额 | 占比 |")
    lines.append("|------|------|------|")
    for c in categories:
        bar = "█" * int(c["percent"] / 5) + "░" * (20 - int(c["percent"] / 5))
        lines.append(f"| {c['category']} | ¥{c['amount']:,.2f} | {bar} {c['percent']}% |")
    max_cat = max(categories, key=lambda x: x["amount"]) if categories else None
    if max_cat:
        lines.append("")
        lines.append(f"支出最多的分类是 **{max_cat['category']}**，共 ¥{max_cat['amount']:,.2f}，占总支出 {max_cat['percent']}%")
    lines.append("")

    # ── TOP 商户 ──
    lines.append("## 支出 TOP 10 商户")
    lines.append("")
    lines.append("| 排名 | 商户 | 分类 | 金额 | 笔数 |")
    lines.append("|------|------|------|------|------|")
    for i, m in enumerate(merchants, 1):
        lines.append(f"| {i} | {m['merchant']} | {m['category']} | ¥{m['amount']:,.2f} | {m['count']} |")
    lines.append("")

    # ── 支付方式 ──
    lines.append("## 支付方式分布")
    lines.append("")
    lines.append("| 支付方式 | 金额 | 占比 |")
    lines.append("|----------|------|------|")
    for p in payments:
        lines.append(f"| {p['method']} | ¥{p['amount']:,.2f} | {p['percent']}% |")
    lines.append("")

    # ── 星期分布 ──
    lines.append("## 星期消费习惯")
    lines.append("")
    max_wd = max(weekday["amounts"]) if weekday["amounts"] else 1
    max_wd = max_wd or 1  # 避免除零
    lines.append("| 星期 | 消费金额 | 笔数 | 分布 |")
    lines.append("|------|----------|------|------|")
    for i, (label, amt, cnt) in enumerate(zip(weekday["labels"], weekday["amounts"], weekday["counts"])):
        bar_len = int(amt / max_wd * 15)
        bar = "█" * bar_len
        lines.append(f"| {label} | ¥{amt:,.2f} | {cnt} | {bar} |")
    lines.append("")

    # ── 收入来源 ──
    if income_sources:
        lines.append("## 收入来源 TOP 10")
        lines.append("")
        lines.append("| 来源 | 金额 |")
        lines.append("|------|------|")
        for src in income_sources:
            lines.append(f"| {src['source']} | ¥{src['amount']:,.2f} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="分析标准化账单数据")
    parser.add_argument("filepath", help="标准化 JSON 文件路径")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "md"], default="markdown",
                        help="输出格式")
    args = parser.parse_args()

    data = load_data(args.filepath)

    if args.format in ("markdown", "md"):
        print(format_report(data))
    else:
        report = {
            "summary": summarize(data),
            "monthly_trend": monthly_trend(data),
            "category_breakdown": category_breakdown(data),
            "top_merchants": top_merchants(data),
            "daily_trend": daily_trend(data),
            "payment_methods": payment_method_breakdown(data),
            "income_sources": income_source_breakdown(data),
            "weekday_analysis": weekday_analysis(data),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
