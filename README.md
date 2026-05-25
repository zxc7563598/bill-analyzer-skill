# bill-analyzer-skill

一个 Claude Code 技能，用于分析支付宝和微信导出的账单文件。自动解析、清洗、标准化商户与分类，生成多维分析报告，支持交互式查询。

## 功能

- 自动识别支付宝 CSV（gbk/utf-8）和微信 xlsx 账单
- 统一字段标准化（日期/商户/金额/分类/支付方式）
- 智能过滤：排除不计收支、中性交易、失败退款等无效记录
- 商户名自动清洗：去门店号、去括号后缀、去手机号等
- 分类自动归并：支付宝自带分类优先，微信按交易类型推测
- 映射持续积累：商户/分类/支付方式映射表随使用自动完善
- 多维度分析报告：总览、来源构成、月度/年度趋势、分类占比、TOP 商户、支付方式分布、星期消费习惯、收入来源
- 交互式查询：按分类、商户、时间、支付方式等维度自由筛选和分组

## 项目结构

```
bill-analyzer-skill/
├── .claude/skills/bill-analyzer/   # 技能目录
│   ├── SKILL.md                    # 技能描述与工作流指引
│   └── scripts/
│       ├── parse_bill.py           # 批量解析 input/ → cleaned_data.json
│       ├── analyze_bill.py         # 全维度分析 → Markdown/JSON 报告
│       └── query_bill.py           # 交互式查询（筛选/分组/排行）
├── input/                          # 放置账单文件的目录（已 gitignore）
├── .gitignore
└── LICENSE
```

> 映射文件（`merchant_clean_mapping.json`、`category_mapping.json`、`payment_method_mapping.json`）会在首次解析账单时自动生成于 `scripts/` 目录下，随使用逐步完善。这些文件已加入 `.gitignore`，不会提交到仓库。

## 安装

### 前置条件

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 已安装
- Python 3.9+ 及 `openpyxl` 库

### 步骤

**方式一：通过 Claude Code 技能市场安装（推荐）**

在 Claude Code 中运行：

```
/add-skill https://github.com/zxc7563598/bill-analyzer-skill
```

**方式二：手动安装**

```bash
# 克隆仓库
git clone https://github.com/zxc7563598/bill-analyzer-skill.git
cd bill-analyzer-skill

# 安装依赖
pip3 install openpyxl

# 将技能链接到 Claude Code
mkdir -p ~/.claude/skills
ln -s "$(pwd)/.claude/skills/bill-analyzer" ~/.claude/skills/bill-analyzer
```

## 使用

### 第一步：准备账单文件

将支付宝或微信导出的账单文件放入项目根目录下的 `input/` 文件夹。

支持的文件格式：
- **支付宝**：CSV 格式，自动检测编码（gbk/utf-8）
- **微信**：XLSX 格式

> 示例目录结构：
> ```
> input/
> ├── 支付宝交易明细(20240701-20250630).csv
> └── 微信支付账单流水文件(20240701-20250701).xlsx
> ```

### 第二步：触发技能

在 Claude Code 中输入 `/bill-analyzer` 或直接描述你的账单分析需求，例如：

> "帮我分析一下 input/ 目录下的账单"

技能会引导你确认文件已就位，然后自动完成解析和分析。

### 第三步：查看分析报告

解析完成后，会自动生成一份包含以下内容的 Markdown 报告：

- 总览（总收入、总支出、结余、月均支出）
- 支付宝 vs 微信来源构成
- 月度/年度收支趋势
- 支出分类占比
- 支出 TOP 10 商户
- 支付方式分布
- 星期消费习惯
- 收入来源

### 第四步：交互式追问

报告生成后，你可以继续追问具体问题，例如：

> "我在餐饮上花了多少钱？列出最多的 5 家店"

> "蜜雪冰城去了多少次？一共花了多少？"

> "今年每个月的交通支出变化趋势是怎样的？"

> "用哪种支付方式最多？占比多少？"

技能会自动调用 `query_bill.py` 精准回答，无需重新生成完整报告。

## 映射文件管理

三个映射文件存储在 `scripts/` 目录下（已 gitignore），随使用自动积累：

| 文件 | 作用 |
|------|------|
| `merchant_clean_mapping.json` | 原始商户名 → 标准化商户名 |
| `category_mapping.json` | 标准化商户名 → 消费分类 |
| `payment_method_mapping.json` | 原始支付方式 → 标准化支付方式 |

如果自动映射不准确，可直接编辑对应的 JSON 文件，下次解析时生效。

## 依赖

- Python 3.9+
- [openpyxl](https://openpyxl.readthedocs.io/) — 用于读取 xlsx 文件
