---
name: bill-analyzer
description: 分析支付宝/微信账单。将账单文件放入 input/ 目录，自动解析、清洗、标准化商户与分类，生成多维分析报告，支持交互式查询。
---

# 账单分析 Skill

分析支付宝或微信导出的账单文件（xlsx/csv）。用户将账单文件放入 `input/` 目录后，依次运行解析和分析脚本，即可获得标准化的合并数据和多维度分析报告。

## 脚本一览

```
scripts/
├── parse_bill.py                   # 批量解析 input/ → cleaned_data.json
├── analyze_bill.py                 # 全维度分析 → Markdown/JSON 报告
├── query_bill.py                   # 交互式查询（筛选/分组/排行）
├── merchant_clean_mapping.json     # 原始商户名 → 标准化商户名
├── category_mapping.json           # 标准化商户名 → 分类
└── payment_method_mapping.json     # 原始支付方式 → 标准化支付方式
```

## 工作流

### Step 1: 解析账单

用户确认已将账单文件放入 `input/` 目录后，运行：

```bash
python3 .claude/skills/bill-analyzer/scripts/parse_bill.py input/ -o /tmp/cleaned_data.json
```

脚本自动完成：
- 扫描目录下所有 `.csv` 和 `.xlsx` 文件
- 自动检测表头行和来源（支付宝/微信）
- 过滤无效交易：不计收支、中性交易、失败/退款交易
- 按交易单号去重
- 字段标准化为统一结构：date/merchant_raw/merchant_clean/category/type/amount/payment_method/source/description
- 应用三个映射文件进行商户名清洗和分类归并

解析完成后向用户汇报：有效记录数、过滤记录数、新发现的商户（如有）。

**映射积累**：脚本自动将新商户/分类/支付方式追加到映射文件。如果自动映射不准确，用户可直接编辑 `scripts/` 下的 JSON 文件，下次运行即生效。

### Step 2: 全维度分析

```bash
python3 .claude/skills/bill-analyzer/scripts/analyze_bill.py /tmp/cleaned_data.json
```

输出 Markdown 报告，包含：
- **总览**：总收入、总支出、结余、周期
- **来源构成**：支付宝 vs 微信的收支对比
- **月度趋势**：按月的收支/结余/笔数
- **年度趋势**：跨年数据时展示年度对比
- **分类占比**：支出分类 Top 8 + 其余归为"其他分类"（避免与真实"其他"分类混淆）
- **TOP 商户**：支出 Top 10，含金额/笔数/所属分类
- **支付方式分布**：各渠道金额和占比
- **星期消费习惯**：一周七天消费金额和笔数分布
- **收入来源**：收入 Top 10

也可用 `--format json` 输出 JSON 格式供后续处理。

### Step 3: 交互式查询

用户可能会问特定问题（"我上个月在餐饮上花了多少钱？""蜜雪冰城去了几次？""今年每个月的交通支出趋势？"），此时用 `query_bill.py` 直接查询，无需再走完整分析流程：

```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json [选项]
```

**常用查询模式**：

查看特定商户的消费明细：
```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json --merchant 蜜雪冰城
```

查看某一分类的 Top N：
```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json --category 餐饮美食 --type expense --top 5 --group-by merchant
```

查看某时间段的月度趋势：
```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json --from 2026-01 --to 2026-05 --category 交通出行 --group-by month
```

支付方式分布：
```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json --group-by payment --type expense
```

关键词模糊搜索：
```bash
python3 .claude/skills/bill-analyzer/scripts/query_bill.py /tmp/cleaned_data.json --keyword 房租
```

**可用筛选条件**：`--type`（income/expense）、`--category`、`--merchant`、`--payment`、`--source`（alipay/wechat）、`--date-from`、`--date-to`、`--keyword`

**可用分组维度**：`--group-by category|merchant|month|year|payment|source|weekday`

**输出控制**：`--top N`（取前 N 条）、`--format json`（输出 JSON）

### 用户查询响应策略

当用户问特定问题时，优先用 `query_bill.py` 精准回答，而不是生成完整报告：
- "我在 XX 花了多少" → `--merchant XX`
- "XX 类别的花费" → `--category XX --group-by month`
- "上个月花了多少" → `--date-from YYYY-MM-01 --date-to YYYY-MM-31 --type expense`
- "哪种支付方式用最多" → `--group-by payment`
- "对比今年和去年" → 分两次查询后对比

如果用户的问题需要多维度综合分析，则使用 `analyze_bill.py`。

## 支持的文件格式

- 支付宝：csv（自动检测 gbk/utf-8 编码）
- 微信：xlsx

## 故障排查

- 检查 `openpyxl` 已安装：`pip3 install openpyxl`
- 如果解析出错，查看 stderr 中的表头行检测信息
- 支付宝 csv 乱码：脚本会自动尝试多种编码
- 商户名大量未匹配：检查 `merchant_clean_mapping.json` 是否需要手动补充
