#!/usr/bin/env python3
"""
解析支付宝/微信账单（目录批量模式）。

用法:
  python3 parse_bill.py <账单目录> [-o cleaned.json] [--mapping-dir references/]

自动扫描目录下所有 csv/xlsx 文件，识别来源（支付宝/微信），自动检测表头行，
过滤不计收支/中性交易/失败交易，标准化字段，应用商户映射和分类映射。
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from typing import Any, Optional

try:
    import openpyxl
except ImportError:
    print("需要安装 openpyxl: pip3 install openpyxl", file=sys.stderr)
    sys.exit(1)


# ── 列名定义 ──────────────────────────────────────────────

ALIPAY_HEADER_KEYS = ["交易时间", "交易分类", "交易对方", "商品说明", "收/支", "金额", "收/付款方式", "交易状态", "交易订单号"]

WECHAT_HEADER_KEYS = ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)", "支付方式", "当前状态", "交易单号"]

# ── 有效交易状态 ──────────────────────────────────────────

VALID_ALIPAY_STATUS = {"交易成功", "支付成功", "充值成功", "转入成功", "还款成功", "解冻成功", "退款成功"}

VALID_WECHAT_STATUS = {"支付成功", "已存入零钱", "对方已收钱", "已转账", "充值完成"}


# ── 支付方式标准化 ────────────────────────────────────────

def load_payment_method_mapping(mapping_file: str) -> dict[str, str]:
    """加载支付方式映射表。"""
    if not os.path.exists(mapping_file):
        return {}
    with open(mapping_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_payment_method_mapping(mapping: dict[str, str], mapping_file: str):
    """保存支付方式映射表。"""
    os.makedirs(os.path.dirname(mapping_file), exist_ok=True)
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def standardize_payment_method(raw: str, source: str, mapping: dict[str, str]) -> str:
    """标准化支付方式。"""

    if not raw:
        return "未知"

    # 先查映射表
    if raw in mapping:
        return mapping[raw]

    raw_clean = raw.strip()

    # 支付宝内部方式 → 支付宝账户
    alipay_internal = {"余额", "余额宝", "账户余额", "花呗"}
    if source == "alipay":
        # 检查是否纯支付宝方式（可能带优惠后缀）
        base_method = raw_clean.split("&")[0].strip()
        if base_method in alipay_internal:
            result = "支付宝账户"
            mapping[raw] = result
            return result
        # 银行卡类：提取银行名+卡类型
        card_match = re.match(r"(.+银行.+?)(?:\(\d+\))?(?:&.*)?$", raw_clean)
        if card_match:
            bank_part = card_match.group(1)
            # 统一银行简称
            result = _normalize_bank_name(bank_part)
            mapping[raw] = result
            return result
        # 网商银行也是银行卡
        if "网商银行" in raw_clean:
            result = "网商银行储蓄卡"
            mapping[raw] = result
            return result

    if source == "wechat":
        # 微信转账时支付方式为 "/"，实际走微信账户
        if raw_clean == "/":
            result = "微信账户"
            mapping[raw] = result
            return result
        wechat_internal = {"零钱", "零钱通"}
        base_method = raw_clean.split("&")[0].strip() if "&" in raw_clean else raw_clean
        if base_method in wechat_internal:
            result = "微信账户"
            mapping[raw] = result
            return result
        card_match = re.match(r"(.+银行.+?)(?:\(\d+\))?$", raw_clean)
        if card_match:
            result = _normalize_bank_name(card_match.group(1))
            mapping[raw] = result
            return result

    # 无法识别，直接返回原值
    result = raw_clean
    mapping[raw] = result
    return result


def _normalize_bank_name(name: str) -> str:
    """统一银行名称。"""
    name = name.strip()
    # 去掉尾号
    name = re.sub(r"\(\d+\)$", "", name)
    # 统一简称
    replacements = {
        "中国农业银行": "农业银行",
        "中国建设银行": "建设银行",
        "中国工商银行": "工商银行",
        "中国银行": "中国银行",
        "招商银行": "招商银行",
        "交通银行": "交通银行",
        "兴业银行": "兴业银行",
        "中信银行": "中信银行",
        "浦发银行": "浦发银行",
        "光大银行": "光大银行",
        "民生银行": "民生银行",
        "平安银行": "平安银行",
        "华夏银行": "华夏银行",
        "广发银行": "广发银行",
        "网商银行": "网商银行",
    }
    for full, short in replacements.items():
        if full in name:
            # 保留卡类型（信用卡/储蓄卡）
            if "信用" in name:
                return short + "信用卡"
            elif "储蓄" in name or "借记" in name:
                return short + "储蓄卡"
            return short + name.replace(full, "")
    return name


# ── 商户名标准化 ──────────────────────────────────────────

def load_mapping(mapping_file: str) -> dict[str, str]:
    """加载映射表。"""
    if not os.path.exists(mapping_file):
        return {}
    with open(mapping_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_mapping(mapping: dict[str, str], mapping_file: str):
    """保存映射表（保持排序）。"""
    os.makedirs(os.path.dirname(mapping_file), exist_ok=True)
    sorted_items = sorted(mapping.items(), key=lambda x: x[0])
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(OrderedDict(sorted_items), f, ensure_ascii=False, indent=2)


def clean_merchant_name_heuristic(raw: str, source: str) -> str:
    """启发式清洗商户名（用于映射表中不存在的新商户）。"""
    name = raw.strip()
    if not name:
        return "未知商户"

    # 去掉门店编号后缀: "蜜雪冰城945327店" / "蜜雪冰城926816改店"
    name = re.sub(r"\d{4,}(?:改)?店$", "", name)
    # 去掉数字尾号: "蜜雪冰城945327店" → "蜜雪冰城"
    name = re.sub(r"\d{5,}$", "", name)

    # 去掉括号内容: "瑞幸咖啡(北京朝阳店)" → "瑞幸咖啡"
    name = re.sub(r"[（(][^)）]*[)）]$", "", name)

    # 去掉微信支付- 前缀
    name = re.sub(r"^微信支付[－-]", "", name)

    # 去掉门店类型后缀 "XXX店"（保留品牌名）
    # 但对于只有一个词的不处理：如 "菜摊" 不处理
    name = re.sub(r"(?:股份|有限|责任|科技)?公司$", "", name)

    # 脱敏名称保留原样（无法标准化）
    if re.match(r"^[\*\?][\*\w]+$", name):
        return raw  # 脱敏名称不处理

    # 含私人名字+手机号: "张映树 13658022939" → 只保留名字
    name = re.sub(r"\s+\d{11}$", "", name)

    # 个体工商户注册名: "开封市示范区艳娟餐饮店（个体工商户）" → 去掉法律后缀
    name = re.sub(r"[（(]个体工商户[)）]$", "", name)
    name = re.sub(r"^.+?(?=市|区|县)[市区县](.+)$", r"\1", name)  # 如果前面是地名前缀则去掉

    return name.strip() or raw


def apply_merchant_cleaning(merchant_raw: str, source: str,
                           merchant_mapping: dict[str, str]) -> tuple[str, bool]:
    """
    商户名标准化。返回 (clean_name, is_new)。
    is_new=True 表示该商户是新加入映射的，需要后续人工审核。
    """
    merchant_raw = merchant_raw.strip()
    if not merchant_raw:
        return ("未知商户", False)

    if merchant_raw in merchant_mapping:
        return (merchant_mapping[merchant_raw], False)

    # 不在映射表中，用启发式规则清洗
    clean = clean_merchant_name_heuristic(merchant_raw, source)
    merchant_mapping[merchant_raw] = clean
    return (clean, True)


def apply_category(merchant_clean: str, alipay_category: str,
                   wechat_tx_type: str, source: str,
                   category_mapping: dict[str, str]) -> tuple[str, bool]:
    """
    确定分类。返回 (category, is_new)。
    支付宝自带的分类优先级最高，可以覆盖微信默认的"其他"分类。
    """
    current = category_mapping.get(merchant_clean)

    # 支付宝自带分类最具权威性，优先使用
    if source == "alipay" and alipay_category:
        if current is None or current == "其他":
            category_mapping[merchant_clean] = alipay_category
            return (alipay_category, True)
        return (current, False)

    # 已有有效分类（非"其他"），直接返回
    if current is not None:
        return (current, False)

    # 微信：根据交易类型推断分类
    if source == "wechat":
        wechat_type_to_category = {
            "商户消费": "其他",
            "扫二维码付款": "其他",
            "转账": "转账红包",
            "微信红包": "转账红包",
            "微信红包（单发）": "转账红包",
        }
        if wechat_tx_type and "退款" in str(wechat_tx_type):
            category_mapping[merchant_clean] = "退款"
            return ("退款", True)
        cat = wechat_type_to_category.get(wechat_tx_type, "其他")
        category_mapping[merchant_clean] = cat
        return (cat, True)

    # 无法推断
    category_mapping[merchant_clean] = "其他"
    return ("其他", True)


# ── 文件读取 ──────────────────────────────────────────────

def find_header_row(rows: list, max_scan: int = 30) -> int:
    """在行列表中查找表头所在行号（0-indexed）。"""
    for i, row in enumerate(rows[:max_scan]):
        row_str = " ".join(str(c) for c in row)
        if "交易时间" in row_str and ("收/支" in row_str or "交易对方" in row_str):
            return i
    return 0  # fallback


def detect_source_from_header(headers: list[str]) -> str:
    """通过列名判断账单来源。"""
    header_str = " ".join(headers)
    if "交易分类" in header_str:
        return "alipay"
    if "交易类型" in header_str:
        return "wechat"
    # fallback: check for Alipay-specific columns
    alipay_score = sum(1 for k in ALIPAY_HEADER_KEYS if k in headers)
    wechat_score = sum(1 for k in WECHAT_HEADER_KEYS if k in headers)
    return "alipay" if alipay_score >= wechat_score else "wechat"


def read_csv_file(filepath: str) -> tuple[list[str], list[list[str]]]:
    """读取 csv 文件。先尝试 utf-8-sig，再尝试 gbk。"""
    encodings = ["utf-8-sig", "gbk", "utf-8", "gb2312", "gb18030"]
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                return ([str(c).strip() for c in rows[0]], rows)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法读取文件: {filepath}")


def read_xlsx_file(filepath: str) -> tuple[list[str], list[list[str]]]:
    """读取 xlsx 文件。"""
    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    all_rows = [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]
    wb.close()
    if not all_rows:
        raise ValueError(f"文件为空: {filepath}")
    return (all_rows[0], all_rows)


def build_column_map(headers: list[str], source: str) -> dict[str, int]:
    """建立标准字段 → 列索引的映射。"""
    col_map = {}
    for idx, h in enumerate(headers):
        h = h.strip().replace("﻿", "").rstrip(",")
        col_map[h] = idx

    # 标准字段名查找表
    if source == "alipay":
        field_aliases = {
            "date": ["交易时间"],
            "alipay_category": ["交易分类"],
            "merchant_raw": ["交易对方"],
            "description": ["商品说明"],
            "type_raw": ["收/支"],
            "amount": ["金额"],
            "payment_method": ["收/付款方式"],
            "status": ["交易状态"],
            "order_id": ["交易订单号", "商户订单号"],
        }
    else:
        field_aliases = {
            "date": ["交易时间"],
            "wechat_tx_type": ["交易类型"],
            "merchant_raw": ["交易对方"],
            "description": ["商品"],
            "type_raw": ["收/支"],
            "amount": ["金额(元)", "金额"],
            "payment_method": ["支付方式"],
            "status": ["当前状态", "交易状态"],
            "order_id": ["交易单号", "商户单号"],
        }

    result = {}
    for std_field, aliases in field_aliases.items():
        for alias in aliases:
            if alias in col_map:
                result[std_field] = col_map[alias]
                break
    return result, col_map


# ── 交易有效性判断 ────────────────────────────────────────

def is_valid_transaction(row_data: list[str], col_map: dict[str, int],
                         source: str) -> tuple[bool, str]:
    """
    判断交易是否有效。返回 (is_valid, reason)。
    过滤："不计收支"、中性交易("/")、失败交易等。
    """
    # 检查收/支
    if "type_raw" in col_map:
        type_val = str(row_data[col_map["type_raw"]]).strip()
        if source == "alipay" and type_val == "不计收支":
            return (False, "支付宝不计收支")
        if source == "wechat" and type_val == "/":
            return (False, "微信中性交易(/)")

    # 检查交易状态
    if "status" in col_map:
        status = str(row_data[col_map["status"]]).strip()
        if source == "alipay":
            if status not in VALID_ALIPAY_STATUS:
                return (False, f"交易状态异常: {status}")
        else:
            if status not in VALID_WECHAT_STATUS:
                return (False, f"交易状态异常: {status}")

    return (True, "")


# ── 主解析函数 ────────────────────────────────────────────

def parse_single_file(
    filepath: str,
    merchant_mapping: dict[str, str],
    category_mapping: dict[str, str],
    payment_mapping: dict[str, str],
) -> tuple[list[dict], dict[str, str], dict[str, str], dict[str, str], list[str]]:
    """
    解析单个账单文件。返回:
    - records: 标准化交易记录列表
    - merchant_mapping: 更新后的商户映射
    - category_mapping: 更新后的分类映射
    - payment_mapping: 更新后的支付方式映射
    - new_merchants: 新发现的商户（原始名）列表
    """
    ext = os.path.splitext(filepath)[1].lower()

    # 读取文件
    if ext == ".csv":
        _, all_rows = read_csv_file(filepath)
    elif ext in (".xlsx", ".xls"):
        _, all_rows = read_xlsx_file(filepath)
    else:
        print(f"  跳过不支持格式: {filepath}", file=sys.stderr)
        return ([], merchant_mapping, category_mapping, payment_mapping, [])

    # 查找表头
    header_idx = find_header_row(all_rows)
    headers = [str(c).strip().replace("﻿", "").rstrip(",") for c in all_rows[header_idx]]
    source = detect_source_from_header(headers)

    # 建立列映射
    col_map, raw_col_map = build_column_map(headers, source)
    required = ["date", "merchant_raw", "amount"]
    missing = [r for r in required if r not in col_map]
    if missing:
        print(f"  警告: {os.path.basename(filepath)} 缺少必要列: {missing}", file=sys.stderr)
        return ([], merchant_mapping, category_mapping, payment_mapping, [])

    print(f"  解析: {os.path.basename(filepath)} → 来源={source}, 表头行={header_idx+1}", file=sys.stderr)

    records = []
    new_merchants = []
    skipped = {"neutral": 0, "status": 0, "no_date": 0, "zero_amount": 0}
    seen_orders = set()

    for row in all_rows[header_idx + 1:]:
        # 跳过空行
        if not row or all(not str(c).strip() for c in row):
            continue

        row_str = [str(c).strip() if c is not None else "" for c in row]

        # 过滤
        valid, reason = is_valid_transaction(row_str, col_map, source)
        if not valid:
            if "不计收支" in reason or "中性" in reason:
                skipped["neutral"] += 1
            else:
                skipped["status"] += 1
            continue

        # 提取各字段
        def get_col(field: str) -> str:
            idx = col_map.get(field)
            if idx is not None and idx < len(row_str):
                return row_str[idx]
            return ""

        merchant_raw = get_col("merchant_raw")
        type_raw = get_col("type_raw")
        amount_raw = get_col("amount")
        date_raw = get_col("date")
        status_raw = get_col("status")
        desc_raw = get_col("description")
        order_id = get_col("order_id")
        payment_raw = get_col("payment_method")

        alipay_cat = get_col("alipay_category") if source == "alipay" else ""
        wechat_tx = get_col("wechat_tx_type") if source == "wechat" else ""

        # 解析金额
        try:
            amount_str = str(amount_raw).replace("¥", "").replace("￥", "").replace(",", "").strip()
            amount = abs(float(amount_str))
        except (ValueError, TypeError):
            skipped["zero_amount"] += 1
            continue

        if amount == 0:
            skipped["zero_amount"] += 1
            continue

        # 解析日期
        date_str = None
        if date_raw:
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]:
                try:
                    date_str = datetime.strptime(date_raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            # 处理 datetime 对象（xlsx 自动转换的）
            if date_str is None and hasattr(date_raw, "strftime"):
                date_str = date_raw.strftime("%Y-%m-%d")
        if not date_str:
            skipped["no_date"] += 1
            continue

        # 去重
        if order_id and order_id in seen_orders:
            continue
        if order_id:
            seen_orders.add(order_id)

        # 判断收支
        is_income = ("收" in str(type_raw) and "支" not in str(type_raw)) or "收入" in str(type_raw)
        txn_type = "income" if is_income else "expense"

        # 商户名标准化（阶段1）
        merchant_clean, merchant_is_new = apply_merchant_cleaning(merchant_raw, source, merchant_mapping)
        if merchant_is_new:
            new_merchants.append(merchant_raw)

        # 分类（阶段2）
        category, cat_is_new = apply_category(merchant_clean, alipay_cat, wechat_tx, source, category_mapping)
        if cat_is_new and not merchant_is_new:
            pass  # 商户名已知但分类新增（一般不会发生）

        # 支付方式标准化
        payment_clean = standardize_payment_method(payment_raw, source, payment_mapping)

        records.append({
            "date": date_str,
            "merchant_raw": merchant_raw.strip() or "未知",
            "merchant_clean": merchant_clean,
            "category": category,
            "type": txn_type,
            "amount": round(amount, 2),
            "payment_method": payment_clean,
            "source": source,
            "description": desc_raw.strip() if desc_raw else "",
            "status": status_raw.strip() if status_raw else "",
        })

    print(f"    有效{len(records)}条, 跳过: 中性{skipped['neutral']} 状态异常{skipped['status']} 无日期{skipped['no_date']} 零金额{skipped['zero_amount']}", file=sys.stderr)
    return (records, merchant_mapping, category_mapping, payment_mapping, new_merchants)


def parse_directory(
    input_dir: str,
    mapping_dir: str,
) -> dict:
    """扫描目录下所有账单文件，解析并合并。"""

    merchant_mapping_file = os.path.join(mapping_dir, "merchant_clean_mapping.json")
    category_mapping_file = os.path.join(mapping_dir, "category_mapping.json")
    payment_mapping_file = os.path.join(mapping_dir, "payment_method_mapping.json")

    # 加载现有映射
    merchant_mapping = load_mapping(merchant_mapping_file)
    category_mapping = load_mapping(category_mapping_file)
    payment_mapping = load_payment_method_mapping(payment_mapping_file)

    print(f"已加载映射: 商户{len(merchant_mapping)}条, 分类{len(category_mapping)}条, 支付方式{len(payment_mapping)}条",
          file=sys.stderr)
    print(file=sys.stderr)

    # 扫描文件
    files = []
    for f in sorted(os.listdir(input_dir)):
        if f.startswith("~$") or f.startswith("."):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in (".csv", ".xlsx", ".xls"):
            files.append(os.path.join(input_dir, f))

    if not files:
        print(f"错误: 目录 {input_dir} 中未找到账单文件 (csv/xlsx)", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(files)} 个账单文件:", file=sys.stderr)
    for f in files:
        print(f"  - {os.path.basename(f)}", file=sys.stderr)
    print(file=sys.stderr)

    # 逐个解析
    all_records = []
    all_new_merchants = []
    total_new_merchant = 0
    total_new_category = 0
    total_new_payment = 0

    for fpath in files:
        records, merchant_mapping, category_mapping, payment_mapping, new_merchants = \
            parse_single_file(fpath, merchant_mapping, category_mapping, payment_mapping)
        all_records.extend(records)
        all_new_merchants.extend(new_merchants)
        if new_merchants:
            total_new_merchant += len(new_merchants)

    # 按日期排序
    all_records.sort(key=lambda r: r["date"])

    # 回填修正：用最终的映射表重新校正记录的 category
    # 解决微信先于支付宝处理时，"其他"分类未被升级的问题
    fixed_cat = 0
    for r in all_records:
        mc = r["merchant_clean"]
        if mc in category_mapping and category_mapping[mc] != r["category"]:
            r["category"] = category_mapping[mc]
            fixed_cat += 1
    if fixed_cat:
        print(f"回填修正: {fixed_cat} 条分类记录", file=sys.stderr)

    # 统计映射增长
    # 重新计数（通过比较前后的映射大小）
    print(file=sys.stderr)
    print(f"总计: {len(all_records)} 条交易记录", file=sys.stderr)
    print(f"新发现商户: {len(set(all_new_merchants))} 个", file=sys.stderr)
    for m in sorted(set(all_new_merchants)):
        print(f"  + {m} → {merchant_mapping[m]}", file=sys.stderr)

    # 保存映射
    save_mapping(merchant_mapping, merchant_mapping_file)
    save_mapping(category_mapping, category_mapping_file)
    save_payment_method_mapping(payment_mapping, payment_mapping_file)
    print(f"映射已保存: 商户{len(merchant_mapping)}条, 分类{len(category_mapping)}条, 支付方式{len(payment_mapping)}条",
          file=sys.stderr)

    return {
        "records": all_records,
        "stats": {
            "total": len(all_records),
            "new_merchants": len(set(all_new_merchants)),
            "merchant_mapping_size": len(merchant_mapping),
            "category_mapping_size": len(category_mapping),
            "payment_mapping_size": len(payment_mapping),
        }
    }


def main():
    parser = argparse.ArgumentParser(description="解析支付宝/微信账单（目录批量模式）")
    parser.add_argument("input_dir", help="账单文件所在目录路径")
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径（默认输出到 stdout）")
    parser.add_argument("--mapping-dir", "-m", default=None, help="映射文件目录（默认 ../references/）")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"错误: 目录不存在: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_dir = args.mapping_dir or os.path.join(os.path.dirname(script_dir), "references")

    result = parse_directory(args.input_dir, mapping_dir)

    output = json.dumps(result["records"], ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"输出已写入: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
