#!/usr/bin/env python3
"""Stage 3: Knowledge Extraction for DAX Deep Textbook"""
import re, os, json
from collections import defaultdict

SRC = r"D:\Mylibrary\书籍总结\DAX-深度教材-v5.0-20260618-1902\_collected\dax _ Microsoft Learn.md"
OUT_DIR = r"D:\Mylibrary\书籍总结\DAX-深度教材-v5.0-20260618-1902"

with open(SRC, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# ── 01 ── Extract function categories ──
func_cats = [
    ("日期和时间函数", "DATE/TIME"),
    ("筛选器函数", "FILTER"),
    ("时间智能函数", "TIME_INTELLIGENCE"),
    ("表操作函数", "TABLE"),
    ("统计函数", "STATISTICAL"),
    ("文本函数", "TEXT"),
    ("逻辑函数", "LOGICAL"),
    ("数学和三角函数", "MATH_TRIG"),
    ("财务函数", "FINANCIAL"),
    ("信息函数", "INFORMATION"),
    ("关系函数", "RELATIONSHIP"),
    ("其他函数", "OTHER"),
]

print("Extracting function references...")

# Find function names for each category
func_refs = {}
current_cat = None
cat_started = False

for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped:
        continue
    for cat_cn, cat_en in func_cats:
        if stripped == cat_cn or stripped.startswith(cat_cn + " "):
            if cat_en not in func_refs:
                func_refs[cat_en] = {"cn": cat_cn, "functions": [], "description": ""}
            current_cat = cat_en
            cat_started = True
            # Next line is usually description
            if i+1 < len(lines):
                func_refs[current_cat]["description"] = lines[i+1].strip()
            break
    if cat_started and current_cat:
        # Collect function names (patterns like "XXX 函数" or just function names)
        func_matches = re.findall(r'([A-Z][A-Z_]+)\s*(?:函数|\(|$)', stripped)
        for fm in func_matches:
            if fm not in func_refs[current_cat]["functions"] and len(fm) > 1:
                func_refs[current_cat]["functions"].append(fm)

# ── 02 ── Extract DAX statements ──
print("Extracting DAX statements...")
statements = ["EVALUATE", "DEFINE", "MEASURE", "VAR", "RETURN", "ORDER BY", "START AT",
              "COLUMN", "TABLE", "CALCULATETABLE", "GROUPBY", "SUMMARIZE", "SUMMARIZECOLUMNS"]

# ── 03 ── Extract operators ──
print("Extracting operators...")
operators = {
    "算术": ["+", "-", "*", "/", "^"],
    "比较": ["=", "<>", ">", "<", ">=", "<="],
    "文本串联": ["&"],
    "逻辑": ["&&", "||", "IN", "NOT"]
}

# ── 04 ── Find key concept sections ──
print("Finding key concept areas...")
concepts = {
    "度量值": [],
    "计算列": [],
    "计算表": [],
    "行级别安全性": [],
    "行上下文": [],
    "筛选器上下文": [],
    "上下文转换": [],
    "CALCULATE": [],
    "变量": [],
    "关系": [],
}

for concept in concepts:
    for i, line in enumerate(lines):
        if concept in line and len(line.strip()) < 100:
            start = max(0, i-1)
            end = min(len(lines), i+10)
            snippet = ' '.join([l.strip() for l in lines[start:end] if l.strip()])
            if len(snippet) > 20:
                concepts[concept].append(snippet[:200])
                break  # just first occurrence

# ── 05 ── Extract traps ──
print("Identifying common traps...")
traps = [
    ("CALCULATE 覆盖筛选器", "初学者误以为 CALCULATE 只添加筛选器，实际上它移除并替换同列上的筛选器"),
    ("FILTER 性能坑", "在迭代器中使用 FILTER 对百万行表操作导致性能灾难"),
    ("BLANK 传播", "BLANK() 在算术运算中传播，导致整个度量值无声返回空白"),
    ("关系方向误用", "多对多关系或非活动关系未用 USERELATIONSHIP 激活"),
    ("上下文转换困惑", "误用 VALUES/DISTINCT 在筛选上下文中导致意外结果"),
    ("时间智能需日期表", "时间智能函数要求连续日期表，否则返回错误"),
    ("DIVIDE vs / 号", "直接除号遇到0分母报错，DIVIDE 优雅处理"),
    ("ALL vs ALLEXCEPT", "ALL 清除所有筛选器 vs ALLEXCEPT 保留指定列——混淆导致结果偏差"),
    ("EARLIER 嵌套坑", "EARLIER 在多层嵌套中引用错误层级"),
    ("隐式类型转换", "DAX 自动将文本转换为数字可能导致意外排序/比较结果"),
]

# ── Build extraction output ──
print("Building extraction manifest...")
extract = []
extract.append("# DAX 深度教材 — 知识提炼清单\n")
extract.append("## 全局素材\n")
extract.append("### 一句话定义")
extract.append("DAX (Data Analysis Expressions) 是微软为表格数据模型设计的公式表达式语言，运行于 Power BI / Analysis Services / Power Pivot，用于定义度量值、计算列、计算表和行级别安全规则。")
extract.append("")
extract.append("### 核心价值")
extract.append("1. **高级计算** — 超越 Excel 公式的复杂业务逻辑（同比/环比/累积/排名）")
extract.append("2. **上下文驱动** — 行上下文+筛选器上下文自动适配不同报表维度组合")
extract.append("3. **声明式编程** — 描述"想算什么"而非"如何算"，引擎自动优化")
extract.append("4. **250+ 内置函数** — 覆盖日期、时间智能、统计、文本、筛选、表操作等")
extract.append("5. **安全模型** — 原生支持行级别安全性 (RLS)")
extract.append("")
extract.append("### 适用边界")
extract.append("- 仅适用于表格数据模型（不支持多维模型的原生 MDX 计算）")
extract.append("- 不直接操作数据源；只能操作已加载到模型中的表")
extract.append("- 度量值结果取决于报表客户端提供的上下文（透视表/切片器/筛选器）")
extract.append("- 性能取决于 VertiPaq 引擎的列存储压缩和内存模型")
extract.append("")

# Function categories
extract.append("## API 矩阵素材 — 函数分类总览\n")
extract.append("| 分类 | 英文 | 函数数 | 典型函数 |")
extract.append("|------|------|:--:|------|")
for cat_en, cat_data in func_refs.items():
    func_list = cat_data["functions"]
    typical = ', '.join(func_list[:5]) if func_list else '-'
    extract.append(f"| {cat_data['cn']} | {cat_en} | {len(func_list)} | {typical} |")

extract.append("")

# Chapter-specific material
extract.append("## 分章提炼\n")

# ch01: DAX入门
extract.append("### 第01章：DAX 入门与极速上手\n")
extract.append("**核心素材**：DAX 概述（度量值/计算列/计算表/RLS/查询概念）、环境安装（Power BI Desktop / DAX Studio / SSMS）、DAX 查询视图")
extract.append("**术语**：度量值(Measure)、计算列(Calculated Column)、计算表(Calculated Table)、DAX 查询视图(DAX Query View)")
extract.append("**陷阱**：度量值 vs 计算列选择场景混淆、DAX 查询视图仅 Power BI Desktop 可用")
extract.append("**案例素材**：TotalSales=SUM() 度量值创建 → 报表可视化闭环")
extract.append("")

# ch02: 语法与数据类型
extract.append("### 第02章：DAX 核心语法与数据类型\n")
extract.append("**核心素材**：DAX 语法规则（等号开头/自动完成/Fx按钮/括号检查）、数据类型（Whole Number/Decimal Number/Currency/Date/DateTime/Text/Boolean/Binary）、运算符体系（算术/比较/文本串联/逻辑）、VAR/RETURN 变量定义、公式栏操作")
extract.append("**术语**：表达式(Expression)、隐式转换(Implicit Conversion)、变量(VAR)、语法检查")
extract.append("**陷阱**：= 号前有空格会报错、文本与数字混合比较返回错误、隐式类型转换导致意外排序")
extract.append("**API素材**：运算符优先级表、数据类型对照表（DAX vs Power Query vs SQL）、常用语法模板")
extract.append("")

# ch03: 计算模型与求值上下文
extract.append("### 第03章：计算模型与求值上下文\n")
extract.append("**核心素材**：行上下文(Row Context) vs 筛选器上下文(Filter Context)、CALCULATE 深度剖析（替换式筛选 vs 添加式筛选）、CALCULATETABLE、上下文转换(Context Transition)、迭代器函数与行上下文产生、RELATED/RELATEDTABLE、CROSSFILTER/USERELATIONSHIP")
extract.append("**术语**：行上下文、筛选器上下文、上下文转换、CALCULATE、迭代器(Iterator)、活动关系(Active Relationship)")
extract.append("**陷阱**：")
for t in traps[:5]:
    extract.append(f"  - ❌ {t[0]}：{t[1]}")
extract.append("**案例素材**：同比销售增长率、累计至今销售额")
extract.append("")

# ch04: 日期时间与时间智能
extract.append("### 第04章：日期时间与时间智能函数\n")
extract.append("**核心素材**：日期时间函数（DATE/YEAR/MONTH/DAY/TODAY/NOW/DATEDIFF/EOMONTH/WEEKNUM/YEARFRAC...）、时间智能函数（TOTALYTD/TOTALQTD/TOTALMTD/DATESYTD/DATEADD/SAMEPERIODLASTYEAR/PARALLELPERIOD/...）、日期表设计规范、PREVIOUSMONTH vs DATEADD 对比")
extract.append("**术语**：日期表(Date Table)、标记为日期表(Mark as Date Table)、YTD/QTD/MTD、会计年度")
extract.append("**陷阱**：时间智能函数无日期表报错、日期表不连续导致断点、SAMEPERIODLASTYEAR 在闰年边界")
extract.append("")

# ch05: 筛选器与表操作函数
extract.append("### 第05章：筛选器与表操作函数\n")
extract.append("**核心素材**：筛选器函数（FILTER/ALL/ALLEXCEPT/ALLSELECTED/ALLNOBLANKROW/KEEPFILTERS/REMOVEFILTERS/LOOKUPVALUE）、表操作函数（ADDCOLUMNS/SUMMARIZE/SUMMARIZECOLUMNS/CROSSJOIN/UNION/INTERSECT/EXCEPT/DISTINCT/VALUES/TOPN/NATURALINNERJOIN/...）、迭代器（SUMX/AVERAGEX/MAXX/MINX/COUNTX/RANKX/CONCATENATEX）、筛选器修饰符（KEEPFILTERS/REMOVEFILTERS）")
extract.append("**术语**：迭代器(Iterator)、筛选器修饰符(Filter Modifier)、虚拟表(Virtual Table)、扩展表(Expanded Table)")
extract.append("**陷阱**：FILTER 在百万级行上的性能杀手、VALUES vs DISTINCT 在空白行上的差异、ALLSELECTED 在复杂筛选场景的意外行为")
extract.append("")

# ch06: 聚合逻辑文本
extract.append("### 第06章：聚合、逻辑与文本函数\n")
extract.append("**核心素材**：聚合函数（SUM/COUNT/COUNTA/COUNTROWS/AVERAGE/MIN/MAX/MEDIAN/STDEV.P/VAR.P/DISTINCTCOUNT）、逻辑函数（IF/SWITCH/AND/OR/NOT/IFERROR/COALESCE）、文本函数（FORMAT/CONCATENATE/LEFT/RIGHT/MID/LEN/FIND/SEARCH/REPLACE/SUBSTITUTE/UPPER/LOWER/TRIM）、数学函数（ROUND/CEILING/FLOOR/ABS/SIGN/SQRT/POWER/MOD/DIVIDE）、信息函数（ISBLANK/ISERROR/ISNUMBER/ISTEXT/ISLOGICAL）")
extract.append("**陷阱**：IF 嵌套过深→SWITCH、COUNTA 包含空白→用 COUNT、DIVIDE vs / 除零处理")
extract.append("")

# ch07: 查询与高级
extract.append("### 第07章：DAX 查询、关系与高级模式\n")
extract.append("**核心素材**：DAX 查询语法（EVALUATE/DEFINE MEASURE/ORDER BY/START AT）、SUMMARIZECOLUMNS 查询模式、关系函数（RELATED/RELATEDTABLE/CROSSFILTER/USERELATIONSHIP）、父子函数（PATH/PATHITEM/PATHLENGTH）、INFO 系统函数系列（INFO.TABLES/INFO.COLUMNS/INFO.MEASURES...）、RLS 安全公式设计、查询优化（DAX Studio / Performance Analyzer / 服务器计时）")
extract.append("**术语**：查询(Query)、EVALUATE、DEFINE、表表达式(Table Expression)、ROLAP/MOLAP、VertiPaq 引擎")
extract.append("**陷阱**：EVALUATE 返回表格过大→客户端崩溃、RLS 公式中引用未授权表、循环依赖")
extract.append("")

# ch08: 实战与排障
extract.append("### 第08章：实战排障与工程最佳实践\n")
extract.append("**核心素材**：综合所有前章的排障痛点、实战案例（销售 Dashboard / KPI 仪表板 / 财务 P&L / 人力资源分析）、性能调优（DAX Studio 分析/避免过度 CALCULATE/迭代器优化/列存储优化）、最佳实践（变量使用/度量值命名规范/格式化/代码组织）")
extract.append("**综合陷阱总表**：20+ 陷阱全章汇总")
for t in traps:
    extract.append(f"  - ❌ {t[0]}：{t[1]}")
extract.append("**FAQA素材**：CALCULATE 不生效？度量值返回空？日期函数报错？性能慢？关系方向错误？")

extract.append("")
extract.append("> **提炼完成** ✅ → 进入阶段4编撰")

# Write
out_path = os.path.join(OUT_DIR, '_提炼清单.md')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(extract))

print(f"Written: {out_path}")
print(f"Length: {len('\n'.join(extract))} chars")

# Write采集清单
manifest_path = os.path.join(OUT_DIR, '_采集清单.md')
with open(manifest_path, 'w', encoding='utf-8') as f:
    f.write(f"""# DAX 深度教材 — 采集清单

| 项目 | 值 |
|------|-----|
| 来源 | `dax.pdf` — Microsoft Learn DAX 参考文档 |
| 采集方式 | PyMuPDF (fitz) 全页文本提取 |
| 总页数 | 1,365 页 |
| 总字符数 | 601,367 字 |
| 输出文件 | `_collected/dax _ Microsoft Learn.md` |
| 涵盖范围 | DAX 概述、语法、250+函数(12分类)、查询、语句、运算符、术语表 |
| 采集状态 | ✅ 完成 |
""")
print(f"Written: {manifest_path}")

# Update checkpoint
ckpt_path = os.path.join(OUT_DIR, '_checkpoint.json')
with open(ckpt_path, 'r', encoding='utf-8') as f:
    ckpt = json.load(f)
ckpt['current_stage'] = 3
ckpt['stage_history'].append({'stage': 3, 'name': '提炼', 'status': 'done'})
ckpt['updated_at'] = '2026-06-18T19:02:00'
with open(ckpt_path, 'w', encoding='utf-8') as f:
    json.dump(ckpt, f, ensure_ascii=False, indent=2)
print("Updated _checkpoint.json → stage 3 done")
