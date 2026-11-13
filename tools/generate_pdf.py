# -*- coding: utf-8 -*-
"""生成 SpeakPal 技术文档 PDF（ReportLab + 微软雅黑）。

用法（仓库根目录，PowerShell 7）：
    python tools/generate_pdf.py

产物：
    SpeakPal_技术文档.pdf      （根目录交付版）
    docs/技术文档.pdf          （文档库同源副本）

维护约定：本文档所有行为、字段、权重、端点数与默认值均应与源码逐项对齐；
         口径冲突时以 docs/design.md 与代码为准。改代码后请同步改这里。
"""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------- 字体注册
FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("MSYH", str(FONT_DIR / "msyh.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("MSYH-Bold", str(FONT_DIR / "msyhbd.ttc"), subfontIndex=0))
pdfmetrics.registerFontFamily(
    "MSYH", normal="MSYH", bold="MSYH-Bold", italic="MSYH", boldItalic="MSYH-Bold"
)

# ---------------------------------------------------------------- 配色
C_NAVY = colors.HexColor("#0F172A")
C_PRIMARY = colors.HexColor("#1E40AF")
C_ACCENT = colors.HexColor("#2563EB")
C_TEAL = colors.HexColor("#0D9488")
C_TEXT = colors.HexColor("#1E293B")
C_MUTED = colors.HexColor("#64748B")
C_BORDER = colors.HexColor("#CBD5E1")
C_BG_LIGHT = colors.HexColor("#F8FAFC")
C_BG_HEADER = colors.HexColor("#EFF6FF")
C_BG_CALLOUT = colors.HexColor("#F0FDF4")
C_BORDER_CALLOUT = colors.HexColor("#16A34A")
C_BG_WARN = colors.HexColor("#FFFBEB")
C_BORDER_WARN = colors.HexColor("#D97706")

CONTENT_W = 174 * mm  # A4(210mm) - 左右各 18mm 页边距


# ---------------------------------------------------------------- 样式
def build_styles():
    base = getSampleStyleSheet()
    s = {}
    s["CoverTag"] = ParagraphStyle(
        "CoverTag", parent=base["Normal"], fontName="MSYH-Bold", fontSize=10.5,
        leading=15, textColor=C_ACCENT, spaceAfter=6,
    )
    s["CoverTitle"] = ParagraphStyle(
        "CoverTitle", parent=base["Normal"], fontName="MSYH-Bold", fontSize=24,
        leading=32, textColor=C_NAVY, spaceAfter=8,
    )
    s["CoverSubtitle"] = ParagraphStyle(
        "CoverSubtitle", parent=base["Normal"], fontName="MSYH", fontSize=12,
        leading=18.5, textColor=C_MUTED, spaceAfter=12,
    )
    s["H1"] = ParagraphStyle(
        "H1", parent=base["Normal"], fontName="MSYH-Bold", fontSize=15, leading=21,
        textColor=C_NAVY, spaceBefore=12, spaceAfter=6, keepWithNext=True,
    )
    s["H2"] = ParagraphStyle(
        "H2", parent=base["Normal"], fontName="MSYH-Bold", fontSize=11.5, leading=17,
        textColor=C_PRIMARY, spaceBefore=8, spaceAfter=4, keepWithNext=True,
    )
    s["Body"] = ParagraphStyle(
        "Body", parent=base["Normal"], fontName="MSYH", fontSize=9.2, leading=14.6,
        textColor=C_TEXT, spaceBefore=2, spaceAfter=4, wordWrap="CJK",
    )
    s["Bullet"] = ParagraphStyle(
        "Bullet", parent=s["Body"], leftIndent=11, firstLineIndent=-8,
        spaceBefore=1.5, spaceAfter=2.5,
    )
    s["Cell"] = ParagraphStyle(
        "Cell", parent=base["Normal"], fontName="MSYH", fontSize=8.3, leading=12.4,
        textColor=C_TEXT, wordWrap="CJK",
    )
    s["CellBold"] = ParagraphStyle(
        "CellBold", parent=s["Cell"], fontName="MSYH-Bold", textColor=C_NAVY,
    )
    s["CellHeader"] = ParagraphStyle(
        "CellHeader", parent=s["Cell"], fontName="MSYH-Bold", fontSize=8.5,
        leading=12.6, textColor=C_NAVY,
    )
    s["Callout"] = ParagraphStyle(
        "Callout", parent=s["Body"], fontSize=8.7, leading=13.6, textColor=C_NAVY,
    )
    s["CodeBlock"] = ParagraphStyle(
        "CodeBlock", parent=base["Normal"], fontName="MSYH", fontSize=7.8,
        leading=11.6, textColor=C_NAVY, wordWrap="CJK",
    )
    return s


# ---------------------------------------------------------------- 构件
def make_table(headers, rows, col_widths, styles, bold_first_col=True):
    data = [[Paragraph(h, styles["CellHeader"]) for h in headers]]
    for row in rows:
        data.append(
            [
                Paragraph(
                    escape(str(cell)).replace("\n", "<br/>"),
                    styles["CellBold"] if (bold_first_col and idx == 0) else styles["Cell"],
                )
                for idx, cell in enumerate(row)
            ]
        )
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_BG_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_NAVY),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.45, C_BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5.5),
                ("TOPPADDING", (0, 0), (-1, -1), 4.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2),
            ]
        )
    )
    return t


def make_callout(title, body_text, styles, warn=False):
    bg = C_BG_WARN if warn else C_BG_CALLOUT
    border = C_BORDER_WARN if warn else C_BORDER_CALLOUT
    html = f"<b>{title}</b><br/>{escape(body_text)}"
    t = Table([[Paragraph(html, styles["Callout"])]], colWidths=[CONTENT_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
        )
    )
    return t


def make_code_box(lines, styles):
    text = "<br/>".join(escape(line) for line in lines)
    t = Table([[Paragraph(text, styles["CodeBlock"])]], colWidths=[CONTENT_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
        )
    )
    return t


def draw_page_chrome(canvas, doc):
    canvas.saveState()
    page_w, page_h = A4
    if doc.page == 1:
        canvas.setFillColor(C_PRIMARY)
        canvas.rect(0, page_h - 8 * mm, page_w, 8 * mm, stroke=0, fill=1)
        canvas.setFillColor(C_TEAL)
        canvas.rect(page_w * 0.68, page_h - 8 * mm, page_w * 0.32, 8 * mm, stroke=0, fill=1)
    else:
        canvas.setFont("MSYH", 8)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(
            18 * mm, page_h - 12 * mm, "SpeakPal · 可验证的 AI 英语口语诊断陪练 — 技术文档 (v2.1)"
        )
        canvas.drawRightString(page_w - 18 * mm, page_h - 12 * mm, "传智杯 AI-Web 网页开发挑战赛")
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, page_h - 14 * mm, page_w - 18 * mm, page_h - 14 * mm)

    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, page_w - 18 * mm, 14 * mm)
    canvas.setFont("MSYH", 8)
    canvas.setFillColor(C_MUTED)
    canvas.drawString(
        18 * mm, 9.5 * mm,
        "基于仓库真实实现编写 · FastAPI 0.2.0 + Vue 3.5 + SQLite + 离线信效度验证套件",
    )
    canvas.drawRightString(page_w - 18 * mm, 9.5 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


# ---------------------------------------------------------------- 正文
def build_story(styles):
    S = styles
    story = []

    # ========== 封面 ==========
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("传智杯 AI-Web 网页开发挑战赛 · 系统架构与工程技术说明书", S["CoverTag"]))
    story.append(Paragraph("SpeakPal 技术文档", S["CoverTitle"]))
    story.append(
        Paragraph(
            "可验证的场景化 AI 英语口语诊断陪练系统 —— 融合客观规则评分、人机一致性统计检验与 SM-2 间隔重复学习闭环",
            S["CoverSubtitle"],
        )
    )

    meta_rows = [
        ["产品名称", "SpeakPal · 可验证的 AI 英语口语诊断陪练", "代码版本", "后端 FastAPI 0.2.0 / 前端 speakpal-frontend@0.2.0"],
        ["文档版本", "v2.2（对齐当前仓库全量实现）", "更新日期", "2026-11-13"],
        ["核心技术栈", "Vue 3 + Vite + Tailwind CSS / FastAPI + SQLAlchemy 2 + SQLite", "验证工具链", "Python 纯标准库 evaluation/ + tools/check_content.py"],
        ["适用读者", "竞赛评委、前后端开发者、测试与运维人员", "覆盖范围", "架构设计、数据模型、API 规格、融合评分、SM-2 闭环、信效度验证与部署"],
    ]
    meta_data = [
        [
            Paragraph(r[0], S["CellBold"]),
            Paragraph(r[1], S["Cell"]),
            Paragraph(r[2], S["CellBold"]),
            Paragraph(r[3], S["Cell"]),
        ]
        for r in meta_rows
    ]
    meta_table = Table(meta_data, colWidths=[26 * mm, 61 * mm, 26 * mm, 61 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), C_BG_HEADER),
                ("BACKGROUND", (2, 0), (2, -1), C_BG_HEADER),
                ("GRID", (0, 0), (-1, -1), 0.45, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 3.5 * mm))
    story.append(
        make_callout(
            "文档设计准则与真实性声明",
            "本文档严格依据当前工作区代码实况编写，凡涉及行为、表结构、路由、公式与默认值的描述均与源码逐行对齐。"
            "设计基线见 docs/design.md，量表推导见 docs/rubric-band.md，离线统计口径见 docs/validation.md；三者与本文冲突时以代码为准。",
            S,
        )
    )
    story.append(Spacer(1, 2.5 * mm))

    # ========== 1 项目概述 ==========
    story.append(Paragraph("1. 项目概述与核心定位", S["H1"]))
    story.append(
        Paragraph(
            "<b>1.1 产品定位</b>：SpeakPal 是面向高校学生与英语学习者的<b>场景化 AI 英语口语诊断陪练系统</b>。"
            "用户注册登录后，可从 6 个高频真实交际场景（求职面试、咖啡店点单、雅思 Part 1、酒店入住、机场值机、餐厅点餐）中任选其一，"
            "通过语音录入或打字输入与 AI 角色进行多轮沉浸式对话（支持 SSE 流式回复与语音合成朗读）。练习结束后，系统输出 0–100 综合分、"
            "随作答方式动态裁剪的维度分、IELTS Band（0.5 步长）与 CEFR 等级（A2–C2），并提供逐句「更地道说法」改写与客观流利度指标，"
            "同时将错句自动沉淀为 SM-2 间隔重复学习卡片。",
            S["Body"],
        )
    )
    story.append(
        Paragraph(
            "<b>1.2 差异化创新点</b>：同类口语应用多停留在「能调用大模型聊天、黑盒打一个总分」。SpeakPal 在工程上重点打通了三大闭环："
            "① <b>可解释融合评分</b>：把语音包络停顿特征、文本词汇多样性（MTLD/TTR）、句法复杂度与场景交际清单转化为客观规则分，对大模型评分实施「只压不抬」约束；"
            "② <b>可复现统计验证</b>：内置零第三方依赖的 evaluation/ 子系统，用 ICC(2,1)/ICC(2,k)、Kappa、Bland-Altman 等指标与教师盲评金标准对齐；"
            "③ <b>诊学一体闭环</b>：把报告错句、85% 阈值跟读重说、最小对立对发音辨析与内置 720 条离线教研卡片（600 词库 + 60 语法 + 60 口语）统一纳入 SM-2 复习调度。",
            S["Body"],
        )
    )

    cap_headers = ["模块域", "核心功能", "关键技术实现", "代码入口"]
    cap_rows = [
        ["认证与安全", "注册/登录、改密踢旧设备、防暴破、SSRF 防护",
         "PBKDF2-SHA256（12 万次迭代）+ JWT（含 token_version 代次）+ 私网 IP 拦截",
         "app/security.py, app/services/outbound.py"],
        ["多轮场景对练", "6 大场景、3 档难度、句型脚手架、SSE 流式回复",
         "保留最近 8 条消息（约 4 轮问答）上下文；SSE 完整生成后落库，失败自动回退普通接口",
         "app/routers/sessions.py, src/api/stream.js"],
        ["双模态与音频", "Web Speech 语音转写、Web Audio 停顿检测、本地回放",
         "50ms 窗口 RMS > 0.02 判有声，≥0.15s 静默记停顿；MediaRecorder + IndexedDB 本地存音频",
         "src/utils/speech.js, audio.js, recordings.js"],
        ["融合诊断报告", "动态 3/4/5 维评分、IELTS/CEFR 换算、跨模式可比档",
         "模型 Band 与规则子分按权重融合 + 超 20 分截断；明细落库 scoring_json",
         "app/services/scoring.py, rules.py, evaluation/bands.py"],
        ["专项发音训练", "错句跟读重说（Drills）、最小对立对辨析（Minimal Pairs）",
         "词级相似度 ≥0.85 通关；内置 2 组 × 10 对易混音素对立训练",
         "app/routers/exercises.py, services/pronunciation.py"],
        ["SM-2 学习闭环", "今日待复习队列、高考/四六级词库、语法卡、地道口语卡",
         "简化 SM-2 间隔重复（again/hard/good 三档）+ 720 条离线 JSON 题库 + 随堂笔记 CRUD",
         "app/routers/study.py, services/srs.py, wordbank.py, library.py"],
        ["数据看板与后台", "Streak 连续天数、12 周热力图、维度均分、Admin 控制台",
         "按 tz_offset 本地时区切日聚合；单页管理台支持用户管理与存储迁移",
         "app/services/dashboard.py, static/admin.html"],
        ["离线统计验证", "人评内部信度、人机一致性效度、教研内容静态质检",
         "纯标准库 ANOVA 求 ICC、Kappa、Bland-Altman；词形屈折匹配检查",
         "evaluation/agreement.py, tools/check_content.py"],
    ]
    story.append(make_table(cap_headers, cap_rows, [24 * mm, 44 * mm, 64 * mm, 42 * mm], S))
    story.append(Spacer(1, 2.5 * mm))

    story.append(
        make_callout(
            "1.3 诚实边界与非目标声明（答辩高频追问点）",
            "① 不做音素级声学建模：发音维度由大模型结合语音识别转写特征推断，正常报告注脚为「分数由模型分与可测规则分融合得出，仅供参考」；"
            "② 服务端不保存用户原始录音，仅入库时长与停顿统计元信息（audio_json），录音回放仅限本浏览器 IndexedDB；"
            "③ evaluation/demo_data.csv 为固定随机种子（seed=42）生成的 20 条合成样本，用于验证统计流水线可复现，不冒充真人实测结论；"
            "④ 无多租户 / 班级 / 教师端，管理台仅做只读统计与账号运维。",
            S,
            warn=True,
        )
    )

    # ========== 2 架构与选型 ==========
    story.append(Paragraph("2. 系统总体架构与技术选型", S["H1"]))
    story.append(Paragraph("2.1 逻辑架构与进程拓扑", S["H2"]))
    story.append(
        Paragraph(
            "系统采用前后端分离 + 离线评估包共享特征层的三层架构。开发与演示环境下，前端运行于 Vite Dev Server（127.0.0.1:5173），"
            "通过 /api 反向代理与 FastAPI 后端（127.0.0.1:8000）通信；后端经 SQLAlchemy 2.x 访问 SQLite（backend/speakpal.db，10 张表），"
            "并通过 httpx 调用 OpenAI 兼容大模型接口与可选 TTS 接口。evaluation/ 包既可作为离线 CLI 独立运行，又被后端运行时直接导入，"
            "以保证线上报告与离线验证的特征提取、档位换算口径完全一致。",
            S["Body"],
        )
    )
    arch_lines = [
        "【浏览器端 Chrome / Edge (127.0.0.1:5173)】",
        "  ├─ Vue 3 SPA：12 个页面视图 (Login / Home / Practice / Report / History / Review / StudyHome / StudyScope / StudyLearn / Notes / Pronunciation / Settings) + catch-all 兜底",
        "  ├─ 语音与音频层：Web Speech API (转写 & 内置朗读) · Web Audio API (50ms RMS 包络采样) · MediaRecorder + IndexedDB (本地录音回放)",
        "  └─ 通信与状态层：Pinia (auth / session / settings) · Axios (Bearer JWT + X-LLM-Key / X-TTS-Key 头注入) · Fetch + ReadableStream (SSE)",
        "          │ HTTP REST / JSON 与 Server-Sent Events（开发环境经 Vite /api 代理转发）",
        "          ▼",
        "【FastAPI 后端服务 (uvicorn 127.0.0.1:8000)】",
        "  ├─ 路由层 routers/：auth · scenes · sessions · reports · exercises · hints · study · words · account · system · tts · admin（共 61 个 /api 操作，落在 54 条路径上）",
        "  ├─ 服务层 services/：agent (目标规划 / Critic / 结束判定) · llm (多轮对话 & SSE) · scoring (评分编排) · rules (规则分与融合) · srs (SM-2) · study · dashboard",
        "  │                    · wordbank · library · pronunciation · outbound (SSRF 防护) · llm_config · storage · user_data",
        "  ├─ 共享计算层：直接复用仓库根目录 evaluation.features（文本/语音特征）、evaluation.bands（权重 / IELTS Band / CEFR / 可比档）与 evaluation.scales（多量表）",
        "  └─ 数据与静态层：SQLAlchemy 2.x → SQLite（10 张表）│ 内置离线题库 data/*.json │ 运营后台 /admin 与离线 Swagger /docs │ tests/ unittest 回归",
    ]
    story.append(make_code_box(arch_lines, S))
    story.append(Spacer(1, 2.5 * mm))

    story.append(Paragraph("2.2 技术选型与工程取舍", S["H2"]))
    tech_headers = ["架构层", "核心组件", "版本约束", "选型理由与关键工程取舍"]
    tech_rows = [
        ["前端框架", "Vue 3（<script setup>）", "^3.5.0", "组合式 API 高内聚，单文件组件开发效率高，便于多视图交互状态管理"],
        ["前端构建与样式", "Vite 5 + Tailwind CSS 3", "^5.4.0 / ^3.4.10", "毫秒级热更新，内置 /api 反代消除跨域；原子类结合 style.css 统一定制视觉规范"],
        ["状态与路由", "Pinia 2 + Vue Router 4", "^2.2.0 / ^4.4.0", "History 路由配合全局前置守卫实现未登录拦截，并按 X-Auth-Reason 精准回跳"],
        ["后端框架", "FastAPI + Uvicorn", ">=0.110", "基于 Pydantic 自动生成 OpenAPI 契约，配合本地化静态资源提供离线 /docs 文档"],
        ["ORM 与数据库", "SQLAlchemy 2.x + SQLite", ">=2.0 / 内置", "单文件零外部服务依赖；main.py 启动期 _ensure_schema() 实现幂等自动补列迁移"],
        ["密码与鉴权", "hashlib.pbkdf2 + PyJWT", "标准库 / >=2.8", "PBKDF2-SHA256 规避 bcrypt 原生编译兼容问题；JWT 载荷引入 token_version 支持改密踢旧设备"],
        ["AI 接口通信", "httpx（OpenAI 兼容协议）", ">=0.27", "不绑定单一厂商 SDK，用户可自由切换 DeepSeek / OpenAI / 硅基流动 / 本地 Ollama"],
        ["离线统计验证", "Python 标准库（math / csv）", "Python 3.10+", "手写双向随机效应 ANOVA 与秩相关，零 numpy/scipy 依赖，确保评委机器开箱即跑"],
    ]
    story.append(make_table(tech_headers, tech_rows, [25 * mm, 38 * mm, 27 * mm, 84 * mm], S))

    # ========== 3 后端与数据模型 ==========
    story.append(PageBreak())
    story.append(Paragraph("3. 后端架构设计与数据模型", S["H1"]))
    story.append(Paragraph("3.1 启动自检、配置优先级与平滑迁移机制", S["H2"]))
    story.append(
        Paragraph(
            "• <b>弱密钥自动轮换与持久化</b>：启动时检查 JWT_SECRET 与 ADMIN_KEY，若为空或为公开弱默认值（dev-secret-change-me / admin123 / change-me-to-a-random-long-string），"
            "自动用 secrets.token_urlsafe 生成高强度随机密钥并写回 backend/.env；ADMIN_KEY 新值会打印到后端控制台。真实进程环境变量中提供的值不改写，仅告警。",
            S["Bullet"],
        )
    )
    story.append(
        Paragraph(
            "• <b>四级数据库路径解析</b>：_resolve_database_url() 按「真实进程环境变量 DATABASE_URL ＞ backend/data_location.json ＞ backend/.env ＞ 默认 sqlite:///./speakpal.db」顺序解析。"
            "当进程环境变量锁定时，管理台「改数据位置」接口返回 409 env_override。注意：进程环境快照必须在 load_dotenv() 之前采集，否则 .env 会永远压过 data_location.json。",
            S["Bullet"],
        )
    )
    story.append(
        Paragraph(
            "• <b>幂等 Schema 自动演进</b>：SQLite 不支持复杂在线迁移，_ensure_schema() 在每次启动时用 inspect(engine) 探测 reports / turns / users / notes / study_items 表结构，"
            "自动补齐新增列（features_json、bands_json、band、cefr、source、mock_reason、answer_mode、comparable_band、scoring_json、token_version、practice_difficulty、word_scope 等）；"
            "notes 表还内置了「旧列 content / learning_item_id 重建」的一次性清洗逻辑。仅支持加列，删列与改类型需手工处理。",
            S["Bullet"],
        )
    )

    story.append(Paragraph("3.2 数据库表结构设计（10 张核心表）", S["H2"]))
    story.append(
        Paragraph(
            "backend/app/models.py 定义 10 张 SQLAlchemy ORM 实体。所有时间戳以 UTC 无时区写入，接口出参统一由 timeutil.utc_iso 格式化为带 Z 的 ISO-8601 串，前端按本地时区展示。",
            S["Body"],
        )
    )
    db_headers = ["表名（ORM 类）", "主键与索引", "核心业务字段", "设计约束与业务用途"]
    db_rows = [
        ["users\n(User)", "PK: id\nUK: username（索引）",
         "password_hash, nickname, token_version, practice_difficulty, word_scope, created_at",
         "账号凭据与学习偏好（默认难度 medium、词库范围 cet4）；改密时 token_version 自增 1，使旧设备 JWT 立即 401"],
        ["sessions\n(PracticeSession)", "PK: id\nFK: user_id → users.id",
         "scene_id, difficulty, status（active|finished）, created_at",
         "单次场景练习主表；turns 与 report 均配置 cascade='all, delete-orphan' 级联删除"],
        ["turns\n(Turn)", "PK: id（同时用于轮次保序）\nFK: session_id → sessions.id",
         "role（ai|user）, content, input_mode（voice|typed）, audio_json, created_at",
         "按自增 id 保序记录对话；user 轮记录输入方式与音频特征 JSON（duration_sec / speech_time_sec / pauses）"],
        ["reports\n(Report)", "PK: id\nUNIQUE FK: session_id → sessions.id",
         "total_score, band, cefr, source（llm|mock）, mock_reason, answer_mode, comparable_band, dimensions_json, bands_json, scoring_json, fixes_json, features_json, comment",
         "与会话 1:1 绑定；完整保存综合分、雅思档、跨模式可比档、模型与规则融合明细（scoring_json）与逐句纠错列表"],
        ["drill_attempts\n(DrillAttempt)", "PK: id\nFK: report_id → reports.id",
         "item_index, transcript, similarity, created_at",
         "记录对第 item_index 条错句的每次语音跟读转写与词级相似度（≥0.85 判定通过）"],
        ["study_items\n(StudyItem)", "PK: id\nFK: user_id, source_session_id",
         "kind（word|phrase|spelling|grammar）, source, term, context, meaning_zh, example, related_json, ease, interval_days, due_at, reps, lapses",
         "SM-2 间隔重复卡片表；统一承载报告自动提炼错卡、高考/四六级新词卡、语法卡与口语表达卡"],
        ["notes\n(Note)", "PK: id\nFK: user_id, session_id",
         "title, body, session_id, created_at, updated_at",
         "随堂学习笔记表，支持关联特定练习会话；标题留空时自动截取正文首行"],
        ["review_events\n(ReviewEvent)", "PK: id\nFK: user_id, item_id",
         "result（again|hard|good）, interval_before, interval_after, created_at",
         "每次复习提交的结果日志；「今天复习了几张」「这条笔记今天复习过没有」按本地日从这张表统计"],
        ["note_links\n(NoteLink)", "PK: id\nFK: note_id, item_id",
         "term, start, end, created_at",
         "笔记正文命中的学习卡（纯文本自动识别）；start/end 是正文里的字符位置，同一个词多次出现会留多行"],
        ["note_link_mutes\n(NoteLinkMute)", "PK: note_id + item_id",
         "created_at",
         "用户手动取消的误关联；同一 (note, item) 只留一行，重新识别时跳过"],
    ]
    story.append(make_table(db_headers, db_rows, [26 * mm, 33 * mm, 52 * mm, 63 * mm], S))
    story.append(Spacer(1, 2.5 * mm))

    story.append(Paragraph("3.3 核心 JSON 字段契约", S["H2"]))
    json_headers = ["字段位置", "JSON 结构与关键键名"]
    json_rows = [
        ["turns.audio_json",
         '{"duration_sec": 3.2, "speech_time_sec": 2.8, "pauses": [0.22, 0.35]} —— 前端 Web Audio API 采样计算的本轮总时长、有效发声时长与停顿数组（秒）。打字轮为空对象 {}。'],
        ["reports.scoring_json",
         '每维一条明细：{"model_score": 78.0, "rule_score": 54.0, "final_score": 64.0, "weight_rule": 0.5, "clamped": true, "clamp_reason": "…", "inputs": {…}} —— 完整保存模型原分、规则子分、是否触发压分及计算输入，支撑前端「评分依据」面板原样复现。接口出参字段名是 scoring_detail（库内与响应不同名，查库时注意）。'],
        ["reports.fixes_json",
         '[{"original": "…", "better": "…", "natural": "…", "error_type": "grammar|spelling|stiffness|wordiness", "reason": "…", "target_term": "…", "meaning_zh": "…"}] —— 逐句纠错数组（1–3 条），驱动错句对比、原声回放与自动生成 study_items 学习卡。'],
        ["reports.features_json",
         '文本侧：word_count / filler_count / filler_rate / ttr / mtld / sentence_count / mean_sentence_len；音频侧：audio_duration_sec / speech_rate_wpm / articulation_rate_wpm / pause_count / mean_pause_sec / pause_ratio。无录音时音频键缺失，由无声学证据分支直接跳过流利度规则分。'],
        ["study_items.related_json",
         '{"synonyms": [], "antonyms": [], "similar": []} —— 近义词 / 反义词 / 形近词，API 出参统一解包为三个标准数组。'],
    ]
    story.append(make_table(json_headers, json_rows, [36 * mm, 138 * mm], S))

    # ========== 4 API ==========
    story.append(PageBreak())
    story.append(Paragraph("4. 后端 API 接口全景规格（61 个操作 / 54 条路径）", S["H1"]))
    story.append(
        Paragraph(
            "后端按业务域划分为 12 个路由模块，共 <b>61 个 /api 操作</b>（60 条路由注册 + GET /api/health），落在 54 条 /api 路径上；另有 3 个 HTML 页面入口（/、/admin、/docs）。"
            "通用约定：① 用户态接口使用 Authorization: Bearer &lt;JWT&gt;，Token 失效时响应头附带 X-Auth-Reason（expired / password_changed / user_gone / token_invalid），并在 CORS 中显式暴露该头；"
            "② 管理台接口使用 X-Admin-Key 头（读接口错密钥 401，写接口 403）；"
            "③ 大模型与语音密钥由浏览器通过 X-LLM-Key、X-LLM-Base-Url、X-LLM-Model、X-TTS-Key 等请求头按次传入，服务端不落库、不回显。"
            "跨域会话归属校验一律返回 404 而非 403，避免泄露会话是否存在。",
            S["Body"],
        )
    )
    api_headers = ["路由模块", "方法与路径", "鉴权", "功能说明与关键状态码"]
    api_rows = [
        ["认证\nauth.py（3）", "POST /api/auth/register\nPOST /api/auth/login\nGET /api/auth/me", "公开\n公开\n用户",
         "注册（用户名大小写归一，直接签发 Token，重名 400）；登录（滑动窗口失败计数防暴破，超限 429，账号不存在与密码错误同文案）；取当前用户"],
        ["场景\nscenes.py（2）", "GET /api/scenes\nGET /api/scenes/{scene_id}/frames", "用户\n用户",
         "6 个内置场景列表（对外隐藏 role / opening 等 prompt 字段）；场景句型脚手架（Frames）中英对照"],
        ["会话与对话\nsessions.py（6）", "POST /api/sessions\nPOST /api/sessions/{id}/turn\nPOST /api/sessions/{id}/turn/stream\nPOST /api/sessions/{id}/finish\nGET /api/sessions/{id}\nGET /api/sessions", "用户",
         "建会话并返回 AI 开场白（无可用 Key → 409 llm_not_configured，Key 被拒 → 502 key_invalid 且不落库）；提交轮次（普通 JSON 或 SSE 流式）；幂等结束并生成报告；会话详情与历史列表"],
        ["报告\nreports.py（1）", "GET /api/sessions/{id}/report", "用户",
         "读取诊断报告（综合分、Band、CEFR、维度分、scoring_detail 融合明细、流利度特征、逐句纠错）"],
        ["专项训练\nexercises.py（4）", "GET /api/sessions/{id}/drills\nPOST /api/sessions/{id}/drills/{idx}/attempt\nGET /api/pronunciation/minimal-pairs\nPOST /api/pronunciation/check", "用户",
         "报告错句跟读队列（含历史最高相似度与 0.85 阈值）；提交跟读转写判分；2 组 × 10 对最小对立对题组；发音辨析判定（correct / partner_heard / reason）"],
        ["SM-2 学习闭环\nstudy.py（21）", "GET /api/study/today\nGET /api/study/due | /summary\nGET /api/study/items\nPOST /api/study/items\nPOST /api/study/items/{id}/review\nDELETE /api/study/items/{id}\nGET|POST /api/study/vocab(/add)\nGET|POST /api/study/grammar(/add)\nGET|POST /api/study/spoken(/add)\nGET|POST /api/notes，GET|PATCH|DELETE /api/notes/{id}\nGET /api/notes/{id}/links\nPOST /api/notes/{id}/mutes，DELETE /api/notes/{id}/mutes/{item_id}", "用户",
         "今日待复习队列与模块汇总；手动建卡、提交复习（支持 grade 评分或 answer 客观判分驱动 SM-2）；高考/四级/六级词库、语法卡、口语卡查询与批量加卡（自动去重）；随堂笔记 CRUD 与「笔记 ↔ 已学词」知识链接"],
        ["提示\nhints.py（1）", "POST /api/sessions/{id}/hint", "用户",
         "按会话目标与最近发言给 3 条可用句式提示；模型不可用时降级为本地句型"],
        ["单词工具\nwords.py（4）", "POST /api/study/words/assist\nPOST /api/study/words/sentence-check\nPOST /api/study/words/import\nPOST /api/study/words/learn", "用户",
         "查词助手（释义 / 例句 / 近反义）；造句检查；批量导入生词；把单词加入学习清单"],
        ["个人中心与看板\naccount.py（7）", "PATCH /api/me/profile\nGET|PATCH /api/me/settings\nGET /api/me/dashboard\nGET /api/me/recommendation\nDELETE /api/me/data | /account", "用户",
         "改昵称/密码（改密需旧密码，token_version+1 并返回新 Token）；同步难度与词库偏好；学习看板（连续天数 / 12 周热力图 / 维度均分 / 近 7 天变化）；难度建议；清练习记录（scope=records）或注销账号（confirm='注销'）"],
        ["系统与语音\nsystem.py / tts.py（4）", "GET /api/config/llm\nPOST /api/config/llm/test\nGET /api/system/storage\nPOST /api/tts\nGET /api/health", "用户 ×4\n公开",
         "查询默认 LLM 配置；实测浏览器传入 Key 的连通性；查看数据库路径/大小/可写性；TTS 合成（无 Key 409 tts_not_configured，被拒 502 tts_key_invalid，不可达 502 tts_unavailable）；健康检查"],
        ["运营管理台\nadmin.py（7）", "GET /api/admin/stats | /users | /sessions\nPATCH|DELETE /api/admin/users/{id}\nDELETE /api/admin/data\nPUT /api/admin/storage", "管理\nX-Admin-Key",
         "全局统计、用户概览、最近会话（limit clamp 到 1–100）；重置用户昵称/密码、删除用户及数据；清全库（confirm='删除'）；改数据目录（环境变量锁定时 409 env_override）"],
    ]
    story.append(make_table(api_headers, api_rows, [26 * mm, 46 * mm, 16 * mm, 86 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        make_callout(
            "端点计数口径",
            "52 = 路由装饰器中注册到 /api 前缀的 51 条 + main.py 中定义的 GET /api/health。页面入口 /、/admin、/docs 不进 OpenAPI 路径表。"
            "路由变动后请以运行期 GET /openapi.json 为准，勿依赖本文档的手抄表格。",
            S,
        )
    )

    # ========== 5 评分体系 ==========
    story.append(PageBreak())
    story.append(Paragraph("5. 诊断评分体系与模型-规则融合算法", S["H1"]))
    story.append(Paragraph("5.1 动态评价维度与按模式加权（evaluation/bands.py）", S["H2"]))
    story.append(
        Paragraph(
            "系统依据用户在会话中的实际输入方式（turns.input_mode）动态裁剪评价维度并切换综合分权重，杜绝「打字练习却给发音打分」的逻辑漏洞。"
            "模型多给的维度会被后端主动丢弃：打字轮不进 pronunciation / fluency，录音轮不进 written_expression。缺失维度按剩余权重重新归一，不当 0 分；认不出模式才退回等权平均。",
            S["Body"],
        )
    )
    weight_headers = ["作答模式（answer_mode）", "pronunciation", "fluency", "written_expression", "grammar_vocab", "task_completion", "维度数"]
    weight_rows = [
        ["voice（全部轮次均为录音）", "20", "20", "—", "30", "30", "4 维"],
        ["typed（全部轮次均为打字）", "—", "—", "35", "35", "30", "3 维"],
        ["mixed（录音轮与打字轮并存）", "15", "15", "20", "25", "25", "5 维"],
        ["comparable（跨模式可比子分）", "—", "—", "—", "0.50", "0.50", "2 维"],
    ]
    story.append(
        make_table(weight_headers, weight_rows, [44 * mm, 22 * mm, 16 * mm, 26 * mm, 24 * mm, 24 * mm, 18 * mm], S)
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "权重按「证据强度」分配而非平均主义：发音在本项目没有声学证据（由模型依转写推断），纯录音中降到 20；纯打字没有发音与流利度证据，"
            "原本属于这两维的 40 分转给文字表达（35）与语言复杂度（35）；混合模式下语音证据只覆盖录音轮、文字证据只覆盖打字轮，因此各降一档。"
            "<b>comparable_band</b> 仅取两种作答都会评的 grammar_vocab 与 task_completion 等权平均，供历史成长曲线与「比上次进步」做跨模式比较——"
            "同一场混合会话的 band 与 comparable_band 相差 0.5 属正常现象，报告页应标明是本模式口径。",
            S["Body"],
        )
    )

    story.append(Paragraph("5.2 客观规则子分计算（backend/app/services/rules.py）", S["H2"]))
    story.append(
        Paragraph(
            "后端基于语音包络元信息与转写文本提取客观特征，按分段线性映射并 clamp 到 [0,1] 后加权合成三个维度的规则子分。所有分段常量均为项目自定，待真人标注数据校准。",
            S["Body"],
        )
    )
    rule_headers = ["规则维度", "子项与分段映射（clamp 到 0–1）", "合成公式"]
    rule_rows = [
        ["流利度\nrule_fluency",
         "s_wpm：≤70 WPM 记 0，70→130 线性上升，130–200 记满分，>200 按 (w−200)/60 衰减\n"
         "s_pause：停顿占比 ≤0.15 记 1.0，≥0.45 记 0\n"
         "s_filler：填充词率 ≤0.03 记 1.0，≥0.15 记 0",
         "S = round(45 + 45 × (0.40·s_wpm + 0.35·s_pause + 0.25·s_filler))；区间 45–90\n"
         "缺 speech_rate_wpm 或 pause_ratio 时规则分为 None（无语音证据不拿填充词硬凑）"],
        ["语言范围\nrule_complexity\n（grammar_vocab）",
         "s_mtld：MTLD 30→90 线性映射\n"
         "s_msl：平均句长 6→16 词/句\n"
         "s_cx：从句标记密度 = 标记数 / 句数（整词匹配 14 类连接词）",
         "S = round(45 + 45 × (0.45·s_mtld + 0.35·s_msl + 0.20·s_cx))；区间 45–90\n"
         "无可用句长时把 0.35 权重让给 s_cx；文本过短返回 None"],
        ["任务完成\nrule_task",
         "按场景交际功能清单 TASK_CHECKS（每场景 4–5 项必达交际动作）统计关键词命中率 hit_rate",
         "S = round(40 + 60 × hit_rate)；区间 40–100\n"
         "清单只测「有没有做」，得体性交由模型判断，故规则权重取 0.6"],
    ]
    story.append(make_table(rule_headers, rule_rows, [26 * mm, 76 * mm, 72 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "句数 sentence_count 的三种来源：标点切分 ≥2 句时直接用；否则若有停顿且词数 ≥8，按 min(1+pause_count, 词数//4) 估算；都没有则记为 None。"
            "之所以不能退化成「整段词数」，是因为 Chrome 转写通常不带标点，此时 sentence_count 恒为 1，mean_sentence_len 方向是错的。",
            S["Body"],
        )
    )

    story.append(Paragraph("5.3 「只压不抬」融合策略与单一换算锚", S["H2"]))
    story.append(
        Paragraph(
            "大模型容易给出「好人分（虚高）」，纯规则又无法识别语法硬伤或答非所问。rules.fuse() 因此实现<b>加权融合 + 单向截断（Clamp）</b>："
            "final = (1 − w_rule) × model_score + w_rule × rule_score，随后若 model_score − rule_score &gt; 20，强制 final = rule_score + 10 并标记 clamped=true 与压分原因；"
            "反之若模型分低于规则分超过 20 分，<b>绝不用规则分把低分往上抬</b>，只在报告中标注「请人工复核」。",
            S["Body"],
        )
    )
    fuse_headers = ["维度", "规则分权重 w_rule", "模型分权重", "说明"]
    fuse_rows = [
        ["pronunciation", "0.00", "1.00", "无声学证据，发音由模型依转写推断（报告显式注明）"],
        ["fluency", "0.50", "0.50", "规则分来自语速 / 停顿 / 填充词，模型补韵律与连贯性"],
        ["grammar_vocab", "0.35", "0.65", "规则分只测语言范围，准确度只能由模型给出，故模型权重大"],
        ["task_completion", "0.60", "0.40", "清单命中是硬证据，得体性交给模型"],
        ["written_expression", "0.00", "1.00", "仅打字轮出现，模型依文本判断书面组织与用词"],
    ]
    story.append(make_table(fuse_headers, fuse_rows, [34 * mm, 30 * mm, 30 * mm, 80 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "<b>单一换算锚</b>：全项目只在 evaluation/bands.py 定义一次 <b>S = 10 × B + 10</b>（反向 B = (S − 10) / 10），向最近 0.5 档取整（floor(B×2+0.5)/2），区间 3.0–9.0；"
            "S &lt; 40 分不给 band（显示低于 A2）。CEFR 映射：≥8.5 → C2，≥7.0 → C1，≥5.5 → B2，≥4.0 → B1，≥3.0 → A2。"
            "综合分与 band 由代码按维度加权算出并落库，<b>不是模型给一个 total 就存</b>。",
            S["Body"],
        )
    )

    story.append(
        Paragraph(
            "<b>多量表展示</b>：报告在雅思之外追加各考试的展示值（evaluation/scales.py，量表版本 2026-11，展示顺序 雅思 → CEFR → 托福 → 多邻国 → 四六级）："
            "托福 / 多邻国按 CEFR 档给官方区间（如 B2 → 托福 72–94、多邻国 90–115），四六级无官方 CEFR 换算、只做水平段参考（tier=reference）；"
            "高考英语不给分数，只标内容难度「难度 ≈ A2–B1」。<b>逐维度只映射雅思 + CEFR</b>——其余考试只有整卷总分或不同构念的子分，硬映射不成立。"
            "换算是确定性的、不落库，旧报告读时自动补齐；band 为空（&lt; 40 分）时不给量表值，降级报告标「本次不计分」。",
            S["Body"],
        )
    )

    story.append(Paragraph("5.4 降级策略与防伪校验", S["H2"]))
    story.append(
        Paragraph(
            "模型不可用（超时、不可达、解析失败、中途丢 Key）时生成降级报告：source=mock，total_score / band / cefr 全部为 null，mock_reason 取 unavailable 或 not_configured，"
            "报告标注「示例报告（模型不可用）· 本次不计分」，历史页显示「—」。<b>降级报告不允许借规则分凑出成绩</b>——apply_to_report() 遇到 source≠llm 直接原样返回。"
            "此外，模型给出的纠错原句 original 必须能在该用户真实转写中匹配到（忽略大小写与标点），找不到直接丢弃，杜绝模型编句子。",
            S["Body"],
        )
    )

    # ========== 6 前端 ==========
    story.append(PageBreak())
    story.append(Paragraph("6. 前端工程设计与 SM-2 学习闭环", S["H1"]))
    story.append(Paragraph("6.1 视图架构与关键交互链路", S["H2"]))
    fe_headers = ["路由路径", "视图组件", "核心状态与业务职责"]
    fe_rows = [
        ["/login", "Login.vue", "登录/注册双模式；依据 URL 查询参数 reason（expired / password_changed / user_gone）展示精准提示，成功后优先回跳 next"],
        ["/", "Home.vue", "6 大场景卡片、句型脚手架预览与 AI 难度建议；顶部集成 LLM 密钥门禁（llmGate.js），未配 Key 时引导至设置页"],
        ["/practice\n/practice/:id", "Practice.vue", "多轮语音/打字对话主界面；Web Speech 实时转写、Web Audio 停顿包络采集、SSE 流式气泡渲染、句型提示抽屉、本地录音回放"],
        ["/report/:id", "Report.vue", "诊断报告页：总分 / Band / CEFR、维度进度条、可展开的「评分依据（可复现）」验算表、逐句纠错对比、错句原声回放与 85% 阈值跟读重说"],
        ["/study", "Study.vue", "四合一学习中心（?tab=review|new|grammar|spoken）：今日到期卡片复习（拼写/选句/造句客观判分）、高考/四六级选词、语法错句辨析、地道口语卡"],
        ["/history", "History.vue", "顶部挂载 StudyDashboard.vue（Streak 连续天数、12 周热力图、维度均分、近 7 天变化）；中部 comparable_band 成长曲线；底部多维筛选历史会话"],
        ["/notes", "Notes.vue", "随堂笔记工作台：新建、搜索、编辑、删除，可回溯关联的练习会话"],
        ["/pronunciation", "Pronunciation.vue", "最小对立对发音辨析训练：针对 /iː/ vs /ɪ/、/θ/ vs /s/ 等中国学习者高频易混音素提供示范与即时比对"],
        ["/settings", "Settings.vue", "五大配置分区：模型 Key 配置与连通性测试、可选 TTS、难度与词库偏好、密码修改、清数据与注销账号"],
    ]
    story.append(make_table(fe_headers, fe_rows, [30 * mm, 30 * mm, 114 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "路由守卫只判断「有没有 token」，不校验是否过期；过期 token 会让首屏请求失败，由 Axios 响应拦截器统一踢回登录页并附原因码。"
            "session store 为纯内存，练习页刷新即丢失进度（有意的简化，避免客户端状态与后端会话不同步）。",
            S["Body"],
        )
    )

    story.append(Paragraph("6.2 语音采集、包络分析与零上传录音回放", S["H2"]))
    story.append(
        Paragraph(
            "• <b>双通道并行采集</b>：按下麦克风时并行启动 SpeechRecognition（en-US）与 getUserMedia 音频流。audio.js 每 50ms 读取时域波形计算 RMS，"
            "RMS &gt; 0.02 判为有声帧，累计 speech_time；由有声转无声记为静音起点，再次转有声时若静音 ≥0.15s 则记入 pauses。麦克风被拒时捕获异常并置 capturer=null，对话仍可继续（只是没有音频特征）。",
            S["Bullet"],
        )
    )
    story.append(
        Paragraph(
            "• <b>零上传隐私回放</b>：recordings.js 用 MediaRecorder 录制用户原声并写入浏览器本地 IndexedDB（按 sessionId + turnIndex 索引）。"
            "在练习页气泡与报告页纠错卡片上可随时「听原句」回放自己的发音并与标准朗读对比，音频数据全程不离开本地浏览器。",
            S["Bullet"],
        )
    )
    story.append(
        Paragraph(
            "• <b>朗读链路</b>：默认走浏览器 speechSynthesis（无需 Key，语速档位 0.85 / 1.0 / 1.15）。若配置了兼容 OpenAI /audio/speech 的 TTS，前端先试 POST /api/tts，"
            "<b>任何失败都回落 speechSynthesis</b>——TTS 挂掉不能连朗读一起没有。",
            S["Bullet"],
        )
    )

    story.append(Paragraph("6.3 SM-2 调度与 720 条离线教研题库", S["H2"]))
    story.append(
        Paragraph(
            "卡片来源分两类：① <b>报告自动建卡</b>——会话结束生成报告时，后端按 sentence_fixes 的 error_type 自动创建 word / phrase / spelling / grammar 学习卡；"
            "② <b>内置题库主动加卡</b>——backend/app/data/ 下内置 600 条核心词汇（gaokao / cet4 / cet6 各 200 词，含词性、释义、例句与同反义/形近词）、"
            "60 条高频语法卡（tenses / articles / prepositions / clauses 四组各 15 条）与 60 条地道口语卡（spoken.json），合计 720 条，由 tools/check_content.py 一键质检。",
            S["Body"],
        )
    )
    srs_headers = ["反馈档位（result）", "客观题判分依据（POST /api/study/items/{id}/review）", "SM-2 状态转移（ease E / interval I / reps R / lapses L）"]
    srs_rows = [
        ["again（忘了 / 答错）", "拼写不匹配 term / 语法选错错句 / 口语相似度 < 0.50",
         "E' = clamp(E − 0.2, 1.3, 2.8)；I' = 1 天，但 due_at = now + 10 分钟（当天内还会再出现）；R' = R + 1；L' = L + 1"],
        ["hard（模糊 / 勉强）", "语法题未点选但手动输入含目标改写词 / 口语相似度 ∈ [0.50, 0.70)",
         "E' = clamp(E − 0.15, 1.3, 2.8)；I' = 1（原间隔 ≤0）否则 max(1, round(I × 1.2))；R' = R + 1；L 不变"],
        ["good（记得 / 答对）", "拼写完全匹配 / 语法选对 right 句 / 口语相似度 ≥ 0.70",
         "E' = clamp(E + 0.1, 1.3, 2.8)；I' = 1（原间隔 ≤0）否则 max(1, round(I × 2.5))；R' = R + 1；L 不变"],
    ]
    story.append(make_table(srs_headers, srs_rows, [34 * mm, 62 * mm, 78 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "间隔上限 60 天（INTERVAL_CAP_DAYS），初始 ease = 2.5。调度器仅接受 again / hard / good 三档——<b>没有 easy 档，且 again 时 reps 不归零</b>，"
            "这是口语短周期复习场景下的简化取舍，与经典 SM-2 的四档实现不同。",
            S["Body"],
        )
    )

    # ========== 7 验证 ==========
    story.append(PageBreak())
    story.append(Paragraph("7. 离线统计验证子系统（evaluation/）与内容质检", S["H1"]))
    story.append(
        Paragraph(
            "为支撑「可验证的 AI 英语口语诊断陪练」这一核心命题，evaluation/ 完全使用 Python 标准库实现心理测量学与医学统计中常用的一致性检验指标，"
            "用于量化「多位教师盲评之间的内部信度」与「系统自动评分与人类专家之间的效度」。刻意不依赖 numpy / scipy，代价是 ICC 需手写双向随机效应方差分析，"
            "收益是在任何 Python 3 环境下都能一键复现。",
            S["Body"],
        )
    )
    eval_headers = ["统计指标", "实现函数（agreement.py）", "数学定义与检验目标", "参考判读标准"]
    eval_rows = [
        ["ICC(2,1) / ICC(2,k)", "icc_2_1() / icc_2_k()\n（共用 _icc(matrix, average)）",
         "双向随机效应 ANOVA 绝对一致性：分解 MS_R / MS_C / MS_E；ICC(2,1) 分母 MS_R+(k−1)MS_E+k(MS_C−MS_E)/n，ICC(2,k) 分母 MS_R+(MS_C−MS_E)/n",
         "Koo & Li (2016)：<0.50 差，0.50–0.75 中等，0.75–0.90 良好，>0.90 优秀"],
        ["Cohen / Fleiss Kappa", "cohens_kappa() / fleiss_kappa()",
         "校正随机一致期望 P_e 后的类别型一致性系数（对齐 CEFR 档位）；Fleiss 支持 2 人以上，行=样本、列=评分者",
         "Landis & Koch (1977)：0.41–0.60 中等，0.61–0.80 较强，>0.80 几乎完全一致"],
        ["Pearson r / Spearman ρ", "pearson() / spearman()",
         "系统连续分与教师均分的线性相关与秩相关；_ranks() 对并列取平均秩",
         "r、ρ ≥ 0.75 表征系统分与人评排序高度吻合"],
        ["MAE / RMSE", "mae() / rmse()",
         "平均绝对误差与均方根误差（0–100 分制量纲），直观反映系统分偏离人评均值的幅度",
         "越小越好"],
        ["Bland-Altman 分析", "bland_altman()",
         "计算系统分减人评均分的均值偏差 bias、标准差 sd 及 95% 一致性界限 [bias ± 1.96·sd]，并统计落在界限内的样本比例",
         "bias 接近 0 说明无系统性高估/低估；≥95% 样本应落在 LoA 内"],
        ["系统档位一致性", "validate.py\n_system_band_block()",
         "系统 CEFR 档 vs 人评多数票（_majority_cefr）：完全一致率 exact_rate、相邻率 adjacent_rate（相差 ≤1 档）、平均档差 mean_abs_cefr_distance、Cohen kappa（含逐人 kappa_per_human）",
         "合成样本参考值：exact 0.70、adjacent 1.00、平均档差 0.30、kappa 0.49（中等）"],
    ]
    story.append(make_table(eval_headers, eval_rows, [32 * mm, 38 * mm, 56 * mm, 48 * mm], S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        make_callout(
            "边界行为与样本量陷阱",
            "① 有效样本 n < 3 时只返回 {n, raters, warning}，不计算任何指标；② 系统分比较要求 n ≥ 3 才输出 system_vs_human_mean；"
            "③ 档位 Kappa 要求至少 2 条完整档位样本；④ ICC 与相关性使用「人评分齐全」的过滤后样本，而 Kappa 用的是原始行中档位齐全的子集——"
            "两类缺失模式不同时，两部分报告的 n 可能不一致，需各自注明样本数。",
            S,
            warn=True,
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("离线验证与内容质检 CLI（仓库根目录，PowerShell 7）：", S["Body"]))
    cli_lines = [
        "# 1) 生成 20 条固定随机种子（seed=42）合成盲评样本 evaluation/demo_data.csv",
        "python -m evaluation.make_demo",
        "",
        "# 2) 计算人评内部信度、系统 vs 人评连续分与 CEFR 档位一致性，输出终端报告与 JSON",
        "python -X utf8 -m evaluation.validate --csv evaluation/demo_data.csv \\",
        "    --raters human1,human2 --system system \\",
        "    --bands human1_band,human2_band --system-band system_band \\",
        "    --out evaluation/demo_report.json",
        "",
        "# 3) 静态校验 600 条词库（含不规则动词屈折形态匹配）、60 语法卡、60 口语卡",
        "python tools/check_content.py    # 返回码 0 表示 720 条教研数据全部通过",
    ]
    story.append(make_code_box(cli_lines, S))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "<b>数据采集规范</b>（真人数据尚未采集）：2–3 名英语教师独立打分且互不可见；对系统分盲评；共用同一份对齐 CEFR / IELTS 描述语的 rubric；"
            "每样本至少两人评，建议 ≥20 条；保留原始录音与转写以保证可复现。"
            "答辩若被追问「这个 ICC 是真的吗」，正确答案是：<b>脚本可信、数值是合成的，真实数据正在采集</b>。",
            S["Body"],
        )
    )

    # ========== 8 安全部署验收 ==========
    story.append(Paragraph("8. 安全加固、部署运行与工程边界", S["H1"]))
    story.append(Paragraph("8.1 安全与鲁棒性加固", S["H2"]))
    sec_headers = ["安全 / 可靠性维度", "工程实现机制与代码落点"]
    sec_rows = [
        ["自带密钥零残留（BYOK）", "服务端不保存 LLM_API_KEY（.env 里写了也不读取）；用户密钥仅经 X-LLM-Key 请求头在内存中转发至上游模型，不写库、不回显、不进错误日志。"],
        ["SSRF 内网探测防护", "services/outbound.py 解析用户传入 Base URL 的 DNS 并校验 IP，默认拒绝 loopback / private / link-local 等内网地址；仅当 ALLOW_PRIVATE_LLM_HOSTS=1 时放行本地 Ollama。"],
        ["会话代次与改密踢人", "users.token_version 随 JWT 载荷下发；改密或管理员重置密码时自增 1，旧 Token 访问任何接口立即 401，响应头附 X-Auth-Reason: password_changed。"],
        ["登录防暴力破解", "routers/auth.py 维护滑动窗口失败计数器，连续输错达阈值后临时锁定并返回 429，登录成功立即清零；账号不存在与密码错误返回同一文案，避免用户枚举。"],
        ["流式原子性与幂等报告", "SSE 流式对话仅在完整接收 AI 回复后写入 turns，杜绝半截脏数据；POST /finish 对已生成报告的会话幂等返回已有报告，不重复消耗 Token。"],
        ["弱密钥自动轮换", "config.py 启动时检测 JWT_SECRET / ADMIN_KEY 是否为空或公开默认值，自动生成 token_urlsafe 随机值写回 .env；真实环境变量提供的值只告警不改写。"],
    ]
    story.append(make_table(sec_headers, sec_rows, [38 * mm, 136 * mm], S))
    story.append(Spacer(1, 2.5 * mm))

    story.append(Paragraph("8.2 安装、启动与生产部署", S["H2"]))
    story.append(
        Paragraph(
            "• <b>开发环境一键启动</b>：首次执行 <b>.\\setup.ps1</b> 自动创建 backend\\.venv 并安装前后端依赖（Node 目录按 tools\\node → ..\\.tools\\node-* → 系统 PATH 顺序探测）；"
            "日常演示双击 <b>start-all.bat</b>，脚本自动清理被占用的 8000 端口，拉起后端（127.0.0.1:8000）与前端（127.0.0.1:5173）两个窗口并打开浏览器。",
            S["Bullet"],
        )
    )
    story.append(
        Paragraph(
            "• <b>生产部署建议</b>：cd frontend &amp;&amp; npm run build 生成静态产物后，用 Nginx 托管 frontend/dist（配置 try_files $uri $uri/ /index.html 支持 History 路由回退），"
            "并将 location /api 反代至 Uvicorn / Gunicorn 进程；同时在真实进程环境变量中注入强随机 JWT_SECRET、ADMIN_KEY 与 DATABASE_URL。"
            "当前后端不托管 dist 产物，演示形态等同于「在演示机上跑两个 dev 进程」，两服务均只监听回环地址。",
            S["Bullet"],
        )
    )

    story.append(Paragraph("8.3 关键参数默认值速查", S["H2"]))
    def_headers = ["参数项", "默认值", "定义位置", "参数项", "默认值", "定义位置"]
    def_rows = [
        ["后端监听地址", "127.0.0.1:8000", "start-backend.bat", "前端监听地址", "127.0.0.1:5173", "frontend/vite.config.js"],
        ["JWT 有效期", "10080 分钟（7 天）", "app/config.py", "默认大模型", "deepseek-chat", "app/config.py"],
        ["对话保留上下文", "最近 8 条消息（约 4 轮）", "app/services/llm.py", "建议结束条件", "3 目标达成或 6 轮上限", "app/services/agent.py"],
        ["对话 / 评分温度", "0.7 / 0.2", "llm.py / scoring.py", "压分触发 / 回落", "高 20 分压回规则分 +10", "app/services/rules.py"],
        ["有声判定 RMS", "0.02（50ms 采样）", "src/utils/audio.js", "跟读通关相似度", "≥ 0.85", "app/routers/exercises.py"],
        ["停顿计入阈值", "≥ 0.15 s", "src/utils/audio.js", "SM-2 间隔上限 / ease 域", "60 天 / [1.3, 2.8]", "app/services/srs.py"],
        ["默认难度 / 词库", "medium / cet4", "app/models.py", "建议评估样本量", "≥ 20 条", "docs/validation.md"],
    ]
    story.append(
        make_table(def_headers, def_rows, [28 * mm, 29 * mm, 30 * mm, 28 * mm, 29 * mm, 30 * mm], S)
    )
    story.append(Spacer(1, 2.5 * mm))

    story.append(Paragraph("8.4 已知限制与技术债", S["H2"]))
    td_headers = ["编号", "问题", "影响", "建议"]
    td_rows = [
        ["TD-A", "finish 无「最少轮次」校验", "—", "已修复：无 user turn 时返回 400（sessions.py:321-324）"],
        ["TD-B", "role / status 仍无枚举约束（difficulty 已白名单校验）", "脏数据仍可绕过前端写入这两列", "给 status / role 加 CheckConstraint 或 Enum"],
        ["TD-C", "无 CI 配置与 lint 配置", "backend/tests 已有 167 条 unittest 全绿（test_api.py / test_scales.py，2026-11-13）", "接 CI 跑 unittest；agreement.py 已知值测试仍缺"],
        ["TD-D", "音频阈值硬编码（RMS 0.02、停顿 0.15s）", "不同麦克风 / 噪声环境下语速与停顿失真", "暴露为配置项，或做环境噪声自校准"],
        ["TD-E", "历史列表无分页；管理台 N+1 查询", "—", "已修复：sessions.py:470-484 支持 limit/offset；admin.py:84-94 已改 GROUP BY"],
        ["TD-F", "语音识别依赖 Chrome 且走云端", "网络受限时转写失败，Firefox / Safari 不可用", "已有「手动输入」兜底；如需更稳可接后端 ASR"],
        ["TD-G", "规则权重未在真人标注数据上校准", "规则分的绝对水平缺外部效度支撑", "采集 20–30 条真人评分后用 evaluation/ 反推校准权重"],
        ["TD-H", "发音维度仅由转写推断", "方法论上最大短板", "接入音素级 ASR 置信度或强制对齐（如 wav2vec2）替代「从转写猜发音」"],
    ]
    story.append(make_table(td_headers, td_rows, [16 * mm, 46 * mm, 52 * mm, 60 * mm], S))
    story.append(Spacer(1, 2.5 * mm))

    story.append(
        make_callout(
            "演进优先级建议",
            "P0：真实 LLM Key 下的完整回归（报告 source 标记已完成）；P1：采集 20–30 条真人评分产出真实 agreement 报告（把「可验证」从工程自测升级为真实结论，是本题核心加分点）；"
            "P2：补 agreement.py 已知值测试、发音维度接入声学证据；P3：场景配置化（存库 / JSON，支持教师自定义场景与 rubric）、部署方案落地（Nginx + Docker Compose）。",
            S,
        )
    )

    return story


# ---------------------------------------------------------------- 主流程
def main():
    root = Path(__file__).resolve().parent.parent
    out_paths = [
        root / "SpeakPal_技术文档.pdf",
        root / "docs" / "技术文档.pdf",
    ]
    styles = build_styles()
    for out_path in out_paths:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title="SpeakPal 技术文档",
            author="SpeakPal Team",
            subject="传智杯 AI-Web 网页开发挑战赛技术文档",
        )
        doc.build(build_story(styles), onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
        print(f"Generated: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
