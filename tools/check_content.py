"""内容校验：词库 / 语法卡 / 口语卡（Chief 要求可重复跑）。

用法（仓库根目录）：
    D:\\python\\python.exe tools/check_content.py
返回码 0 = 全过；1 = 有错误。纯标准库，不联网、不装依赖。

检查项：
1. 字段齐全（词：term/pos/meaning_zh/example/example_zh；语法：id/point/rule/wrong/right；
   口语：id/formal/natural/why）。
2. 词库例句里真的出现该词或它的屈折/不规则形式（防凑数）。
3. 跨档不重复（同一 term 不能同时出现在两个词库）。
4. 没有占位串（空释义、例句等于单词本身、例句里带 TODO/xx/待补）。
5. 语法卡「错句 ≠ 正确句」，口语卡「书面 ≠ 口语」，编号不重复。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backend" / "app" / "data"

sys.path.insert(0, str(ROOT / "backend"))
try:  # 判档逻辑本身只有标准库依赖，可以直接 import 来断言
    from app.services import library as cardlib  # noqa: E402
except Exception as exc:  # pragma: no cover - 只在这份脚本里兜底
    cardlib = None
    print(f"WARN  无法导入判档逻辑（app.services.library）：{exc}")

EXPECTED_WORDS = 200
EXPECTED_GRAMMAR_GROUPS = ("tenses", "articles", "prepositions", "clauses")
EXPECTED_PER_GROUP = 15
EXPECTED_SPOKEN = 60

CJK = re.compile(r"[\u4e00-\u9fff]")
WORD = re.compile(r"[a-z0-9']+")
BANNED = ("todo", "tbd", "待补", "placeholder", "xxx", "lorem")

# 常见不规则变化：例句里出现任一形式算命中
IRREGULAR = {
    "be": ["am", "is", "are", "was", "were", "been", "being"],
    "begin": ["began", "begun"],
    "bite": ["bit", "bitten"],
    "blow": ["blew", "blown"],
    "break": ["broke", "broken"],
    "bring": ["brought"],
    "build": ["built"],
    "buy": ["bought"],
    "catch": ["caught"],
    "choose": ["chose", "chosen"],
    "come": ["came"],
    "cost": ["cost"],
    "deal": ["dealt"],
    "do": ["did", "done", "does"],
    "draw": ["drew", "drawn"],
    "drink": ["drank", "drunk"],
    "drive": ["drove", "driven"],
    "eat": ["ate", "eaten"],
    "fall": ["fell", "fallen"],
    "feed": ["fed"],
    "feel": ["felt"],
    "fight": ["fought"],
    "find": ["found"],
    "fly": ["flew", "flown", "flies"],
    "forget": ["forgot", "forgotten"],
    "forgive": ["forgave", "forgiven"],
    "freeze": ["froze", "frozen"],
    "get": ["got", "gotten"],
    "give": ["gave", "given"],
    "go": ["went", "gone"],
    "grow": ["grew", "grown"],
    "hang": ["hung"],
    "have": ["has", "had"],
    "hear": ["heard"],
    "hide": ["hid", "hidden"],
    "hit": ["hit"],
    "hold": ["held"],
    "hurt": ["hurt"],
    "keep": ["kept"],
    "know": ["knew", "known"],
    "lead": ["led"],
    "leave": ["left"],
    "lend": ["lent"],
    "lie": ["lay", "lain"],
    "lose": ["lost"],
    "make": ["made"],
    "mean": ["meant"],
    "meet": ["met"],
    "pay": ["paid"],
    "read": ["read"],
    "ride": ["rode", "ridden"],
    "rise": ["rose", "risen"],
    "run": ["ran"],
    "say": ["said"],
    "see": ["saw", "seen"],
    "sell": ["sold"],
    "send": ["sent"],
    "shake": ["shook", "shaken"],
    "shine": ["shone"],
    "shoot": ["shot"],
    "show": ["showed", "shown"],
    "sing": ["sang", "sung"],
    "sit": ["sat"],
    "sleep": ["slept"],
    "speak": ["spoke", "spoken"],
    "spend": ["spent"],
    "stand": ["stood"],
    "steal": ["stole", "stolen"],
    "stick": ["stuck"],
    "swim": ["swam", "swum"],
    "take": ["took", "taken"],
    "teach": ["taught"],
    "tear": ["tore", "torn"],
    "tell": ["told"],
    "think": ["thought"],
    "throw": ["threw", "thrown"],
    "understand": ["understood"],
    "wake": ["woke", "woken"],
    "wear": ["wore", "worn"],
    "win": ["won"],
    "write": ["wrote", "written"],
}

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def token_forms(term: str) -> set[str]:
    """该词在例句里可能的写法（原形 + 常见屈折 + 不规则）。"""
    t = term.lower().strip()
    if not t:
        return set()
    forms = {t, t + "s", t + "es", t + "ed", t + "d", t + "ing", t + "er", t + "est"}
    if t.endswith("y"):
        forms |= {t[:-1] + "ies", t[:-1] + "ied", t[:-1] + "ier", t[:-1] + "iest"}
    if t.endswith("e"):
        forms |= {t[:-1] + "ing", t[:-1] + "ed"}
    if len(t) >= 3 and t[-1] not in "aeiouywxz":
        forms |= {t + t[-1] + "ed", t + t[-1] + "ing"}
    forms |= set(IRREGULAR.get(t, []))
    return forms


def example_has_term(term: str, example: str) -> bool:
    words = set(WORD.findall((example or "").lower()))
    forms = token_forms(term)
    if forms & words:
        return True
    # 短语（如 "give me a hand"）按整串子串判断
    if " " in term and term.lower() in (example or "").lower():
        return True
    return False


def check_words() -> None:
    scope_terms: dict[str, set[str]] = {}
    for scope in ("gaokao", "cet4", "cet6"):
        path = DATA / "wordbanks" / f"{scope}.json"
        if not path.exists():
            fail(f"[wordbank] 缺少 {path.relative_to(ROOT)}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"[wordbank:{scope}] JSON 解析失败：{exc}")
            continue
        words = data.get("words") or []
        if len(words) != EXPECTED_WORDS:
            fail(f"[wordbank:{scope}] 词数 {len(words)}，应为 {EXPECTED_WORDS}")
        terms = [str(w.get("term") or "").strip().lower() for w in words]
        if len(terms) != len(set(terms)):
            dup = sorted({t for t in terms if terms.count(t) > 1})
            fail(f"[wordbank:{scope}] 同档重复：{dup}")
        scope_terms[scope] = set(terms)
        if not data.get("name"):
            fail(f"[wordbank:{scope}] 缺少 name")
        for w in words:
            term = str(w.get("term") or "").strip()
            example = str(w.get("example") or "").strip()
            for key in ("term", "pos", "meaning_zh", "example", "example_zh"):
                if not str(w.get(key) or "").strip():
                    fail(f"[wordbank:{scope}] {term or '?'} 缺字段 {key}")
            if not CJK.search(str(w.get("meaning_zh") or "")):
                fail(f"[wordbank:{scope}] {term} 的 meaning_zh 不是中文：{w.get('meaning_zh')}")
            if not CJK.search(str(w.get("example_zh") or "")):
                fail(f"[wordbank:{scope}] {term} 的 example_zh 不是中文")
            if example.lower().strip(" .!?") == term.lower():
                fail(f"[wordbank:{scope}] {term} 的 example 只是单词本身")
            if not example_has_term(term, example):
                fail(f"[wordbank:{scope}] {term} 的例句里没有这个词：{example}")
            lowered = f"{term} {example}".lower()
            if any(bad in lowered for bad in BANNED):
                fail(f"[wordbank:{scope}] {term} 含占位串")
    scopes = list(scope_terms)
    for i in range(len(scopes)):
        for j in range(i + 1, len(scopes)):
            overlap = scope_terms.get(scopes[i], set()) & scope_terms.get(scopes[j], set())
            if overlap:
                fail(f"[wordbank] 跨档重复 {scopes[i]}/{scopes[j]}：{sorted(overlap)}")


def check_grammar() -> None:
    ids: set[str] = set()
    total = 0
    for group in EXPECTED_GRAMMAR_GROUPS:
        path = DATA / "grammar" / f"{group}.json"
        if not path.exists():
            fail(f"[grammar] 缺少 {path.relative_to(ROOT)}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"[grammar:{group}] JSON 解析失败：{exc}")
            continue
        items = data.get("items") or []
        total += len(items)
        if len(items) != EXPECTED_PER_GROUP:
            fail(f"[grammar:{group}] 张数 {len(items)}，应为 {EXPECTED_PER_GROUP}")
        if not data.get("name"):
            fail(f"[grammar:{group}] 缺少 name")
        if data.get("group") != group:
            fail(f"[grammar:{group}] group 字段不一致：{data.get('group')}")
        for item in items:
            cid = str(item.get("id") or "").strip()
            if not cid:
                fail(f"[grammar:{group}] 有卡缺 id")
            elif cid in ids:
                fail(f"[grammar:{group}] id 重复：{cid}")
            else:
                ids.add(cid)
            for key in ("point", "rule", "wrong", "right"):
                if not str(item.get(key) or "").strip():
                    fail(f"[grammar:{group}] {cid} 缺字段 {key}")
            wrong = str(item.get("wrong") or "")
            right = str(item.get("right") or "")
            rule = str(item.get("rule") or "")
            if wrong.strip().lower() == right.strip().lower():
                fail(f"[grammar:{group}] {cid} 的错句和正确句一样")
            if CJK.search(wrong) or CJK.search(right):
                fail(f"[grammar:{group}] {cid} 的例句里混了中文")
            if not CJK.search(rule):
                fail(f"[grammar:{group}] {cid} 的 rule 应该是中文解释")
            if len(str(item.get("point") or "")) > 12:
                warnings.append(f"[grammar:{group}] {cid} 语法点偏长：{item.get('point')}")
            for key in ("wrong", "right", "rule"):
                if any(bad in str(item.get(key) or "").lower() for bad in BANNED):
                    fail(f"[grammar:{group}] {cid} 的 {key} 含占位串")
    if total != EXPECTED_PER_GROUP * len(EXPECTED_GRAMMAR_GROUPS):
        fail(f"[grammar] 总张数 {total}，应为 {EXPECTED_PER_GROUP * len(EXPECTED_GRAMMAR_GROUPS)}")


def check_spoken() -> None:
    path = DATA / "spoken.json"
    if not path.exists():
        fail(f"[spoken] 缺少 {path.relative_to(ROOT)}")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        fail(f"[spoken] JSON 解析失败：{exc}")
        return
    items = data.get("items") or []
    if len(items) != EXPECTED_SPOKEN:
        fail(f"[spoken] 张数 {len(items)}，应为 {EXPECTED_SPOKEN}")
    ids: set[str] = set()
    for item in items:
        cid = str(item.get("id") or "").strip()
        if not cid:
            fail("[spoken] 有卡缺 id")
        elif cid in ids:
            fail(f"[spoken] id 重复：{cid}")
        else:
            ids.add(cid)
        formal = str(item.get("formal") or "").strip()
        natural = str(item.get("natural") or "").strip()
        why = str(item.get("why") or "").strip()
        for key, value in (("formal", formal), ("natural", natural), ("why", why)):
            if not value:
                fail(f"[spoken] {cid} 缺字段 {key}")
        if formal and natural and formal.lower() == natural.lower():
            fail(f"[spoken] {cid} 的书面和口语说法一样")
        if CJK.search(formal) or CJK.search(natural):
            fail(f"[spoken] {cid} 的英文里混了中文")
        if not CJK.search(why):
            fail(f"[spoken] {cid} 的 why 应该是中文")
        if natural and len(WORD.findall(natural.lower())) < 2:
            fail(f"[spoken] {cid} 的口语说法太短，不像完整句子：{natural}")


def check_grading() -> None:
    """判档断言：照抄卡片上显示的提示必须 again，改对了必须 good。

    语法卡显示的是错句，口语卡显示的是书面说法；这两句和正确答案往往只差一个词，
    不拦的话照抄就能拿 hard/分（rc22 报过这个漏洞）。换内容时这条会第一时间报警。
    """
    if cardlib is None:
        fail("[grading] 判档逻辑没导入，无法验证「照抄提示必须 again」")
        return
    for group in EXPECTED_GRAMMAR_GROUPS:
        path = DATA / "grammar" / f"{group}.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            cid = str(item.get("id") or "?")
            wrong = str(item.get("wrong") or "")
            right = str(item.get("right") or "")
            blanked, blank_answer = cardlib.blank_and_answer(wrong, right)
            copied = cardlib.judge_card("grammar", wrong, right, wrong, blank_answer, blanked)
            if copied != "again":
                fail(f"[grading] {cid} 照抄错句被判成 {copied}，应为 again")
            if blanked:
                copied_blank = cardlib.judge_card(
                    "grammar", blanked, right, wrong, blank_answer, blanked
                )
                if copied_blank != "again":
                    fail(f"[grading] {cid} 照抄挖空句被判成 {copied_blank}，应为 again")
            fixed = cardlib.judge_card(
                "grammar", blank_answer or right, right, wrong, blank_answer, blanked
            )
            if fixed != "good":
                fail(f"[grading] {cid} 改对了却判成 {fixed}，应为 good")
    path = DATA / "spoken.json"
    if path.exists():
        for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            cid = str(item.get("id") or "?")
            formal = str(item.get("formal") or "")
            natural = str(item.get("natural") or "")
            copied = cardlib.judge_card("spoken", formal, natural, formal)
            if copied != "again":
                fail(f"[grading] {cid} 照抄书面说法被判成 {copied}，应为 again")
            fixed = cardlib.judge_card("spoken", natural, natural, formal)
            if fixed != "good":
                fail(f"[grading] {cid} 照抄口语说法却判成 {fixed}，应为 good")


def main() -> int:
    check_words()
    check_grammar()
    check_spoken()
    check_grading()
    for warn in warnings:
        print("WARN ", warn)
    for err in errors:
        print("FAIL ", err)
    print()
    print(f"内容校验：{len(errors)} 个错误，{len(warnings)} 个提醒")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
