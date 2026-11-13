"""学习卡与笔记（docs/design.md §16.5）。"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import Note, PracticeSession, ReviewEvent, StudyItem, User
from ..schemas import (
    GrammarCardOut,
    GrammarGroupOut,
    GrammarOut,
    LibraryAddIn,
    LibraryAddOut,
    NoteIn,
    NoteOut,
    SpokenCardOut,
    SpokenOut,
    StudyItemIn,
    StudyItemOut,
    StudyReviewIn,
    TodayGroupOut,
    TodayOut,
    VocabAddIn,
    VocabAddOut,
    VocabOut,
)
from ..security import get_current_user
from ..services import library, wordbank
from ..services.srs import schedule
from ..services.study import (
    KINDS,
    count_reviewed_today,
    is_due,
    item_out,
    judge_spelling,
    normalize_related,
    safe_spelling_hint,
)
from ..timeutil import utc_iso, utcnow

router = APIRouter(prefix="/api", tags=["study"])

MAX_TERM = 128
# 学习卡来源（docs/design.md §16.1）：报告里加的 / 词库新词 / 复习补的 / 语法课 / 口语课
SOURCES = ("report", "vocab", "review", "grammar", "spoken")
SOURCE_REPORT = "report"


def _item_or_404(db: OrmSession, user_id: int, item_id: int) -> StudyItem:
    row = db.get(StudyItem, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="学习卡不存在")
    return row


@router.get("/study/due", response_model=list[StudyItemOut])
def due_items(
    limit: int | None = None,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """今天要到期的卡：date(due_at) <= today，按到期时间升序。

    默认返回全部到期卡：`/study/summary` 的 `due_count` 统计所有到期卡，
    这里如果默认只给 50 张，首页说 60 个、学习页只能复习 50 个，两边对不上。
    `limit` 仍然可传（给需要分页的调用方），不传就不截断。
    """
    now = utcnow()
    rows = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user.id)
        .order_by(StudyItem.due_at.asc(), StudyItem.id.asc())
        .all()
    )
    due = [row for row in rows if is_due(row, now)]
    if limit is not None:
        due = due[: max(1, limit)]
    return [item_out(row, now) for row in due]


@router.get("/study/summary")
def study_summary(
    # 与 JS 的 new Date().getTimezoneOffset() 同口径：北京时间传 -480
    tz_offset: int = Query(default=0, ge=-840, le=840),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """首页与学习页的聚合接口：字段名按设计文档（*_count）。

    `due_count` 与 `/study/due` 同源同量；分类型的 due_*_count 给 tab 上的数字用。
    `reviewed_today` 按用户本地日统计今天的复习提交数（review_events）。
    """
    now = utcnow()
    rows = db.query(StudyItem).filter(StudyItem.user_id == user.id).all()
    notes_count = db.query(Note).filter(Note.user_id == user.id).count()
    review_times = [
        row[0]
        for row in db.query(ReviewEvent.created_at)
        .filter(ReviewEvent.user_id == user.id)
        .all()
    ]
    due = [row for row in rows if is_due(row, now)]
    due_by_key: dict[str, int] = {}
    for row in due:
        due_by_key[_today_key(row)] = due_by_key.get(_today_key(row), 0) + 1
    return {
        "due_count": len(due),
        "reviewed_today": count_reviewed_today(review_times, now, tz_offset),
        "notes_count": int(notes_count or 0),
        "total": len(rows),
        "word_count": sum(1 for row in rows if row.kind == "word"),
        "phrase_count": sum(1 for row in rows if row.kind == "phrase"),
        "spelling_count": sum(1 for row in rows if row.kind == "spelling"),
        "grammar_count": sum(1 for row in rows if row.kind == "grammar"),
        "due_word_count": due_by_key.get("word", 0),
        "due_spelling_count": due_by_key.get("spelling", 0),
        "due_grammar_count": due_by_key.get("grammar", 0),
        "due_spoken_count": due_by_key.get("spoken", 0),
        "due_phrase_count": due_by_key.get("phrase", 0),
    }


@router.post("/study/items", response_model=StudyItemOut)
def create_item(
    body: StudyItemIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """手动加入学习清单（报告页「加入学习清单」走这条）。

    按 `(user_id, kind, term)` 去重：前端「已加入清单」只是内存状态，刷新后会恢复可点，
    重复点不能变成两张卡（否则首页到期数 +2、学习页同一个词问两遍）。
    已经存在时直接返回那张卡，前端据返回的 id 置灰即可。
    """
    kind = (body.kind or "").strip().lower()
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="kind 只能是 word / phrase / spelling")
    term = (body.term or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="term 不能为空")
    source = (body.source or SOURCE_REPORT).strip().lower()
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail="source 只能是 report / vocab / review")
    _check_session_owner(db, user.id, body.source_session_id)

    wanted = term.lower()
    existing = next(
        (
            row
            for row in db.query(StudyItem)
            .filter(StudyItem.user_id == user.id, StudyItem.kind == kind)
            .all()
            if (row.term or "").lower() == wanted
        ),
        None,
    )
    if existing is not None:
        return item_out(existing)

    context = (body.context or "").strip()
    meaning_zh = (body.meaning_zh or "").strip()
    related = normalize_related(body.related)
    reason = str((body.related or {}).get("reason") or "").strip()
    if kind == "spelling":
        # 拼写卡题干一律留空；原因可能来自 meaning_zh（旧客户端）或 related.reason（新客户端）
        meaning_zh, from_hint = safe_spelling_hint(term, meaning_zh)
        keep = from_hint or reason
        if keep:
            related["reason"] = keep
    elif reason:
        related["reason"] = reason

    row = StudyItem(
        user_id=user.id,
        kind=kind,
        term=term[:MAX_TERM],
        context=context,
        meaning_zh=meaning_zh,
        example=(body.example or "").strip(),
        related_json=__import__("json").dumps(related, ensure_ascii=False),
        source_session_id=body.source_session_id,
        source=source,
        due_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return item_out(row)


@router.post("/study/items/{item_id}/review", response_model=StudyItemOut)
def review_item(
    item_id: int,
    body: StudyReviewIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """按卡的题型判档：拼写默写、语法填空/整句改写、口语改写走 `answer`；
    单词卡和报告来的句型卡才用 `grade` 自评。"""
    row = _item_or_404(db, user.id, item_id)
    answer = (body.answer or "").strip()
    related = item_out(row).related
    if row.kind == "grammar" or row.source == "spoken":
        if not answer:
            raise HTTPException(status_code=400, detail="这类卡要用 answer 提交改写后的说法")
        if row.kind == "grammar":
            # 卡片上同时显示错句（row.context）和挖空句（related.blank），两句照抄都要判 again
            result = library.judge_card(
                "grammar",
                answer,
                row.example or "",
                row.context or "",
                str(related.get("answer") or ""),
                str(related.get("blank") or ""),
            )
        else:
            # 口语卡上显示的是书面说法（row.term）：照抄必须判 again
            result = library.judge_card("spoken", answer, row.example or "", row.term or "")
    elif answer:
        if row.kind != "spelling":
            raise HTTPException(status_code=400, detail="只有拼写卡需要默写判定")
        result, _distance = judge_spelling(answer, row.term)
    else:
        result = (body.grade or body.result or "").strip().lower()
    interval_before = float(row.interval_days or 0)
    try:
        ease, interval, reps, lapses, due_at = schedule(
            row.ease, row.interval_days or 0, row.reps or 0, row.lapses or 0, result
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row.ease = ease
    row.interval_days = interval
    row.reps = reps
    row.lapses = lapses
    row.due_at = due_at
    # 每次提交都留一条日志：复习统计与笔记「今天复习过」都靠它
    db.add(
        ReviewEvent(
            user_id=user.id,
            item_id=row.id,
            result=str(result or "").strip().lower(),
            interval_before=interval_before,
            interval_after=float(interval),
        )
    )
    db.commit()
    db.refresh(row)
    out = item_out(row)
    out.last_result = result
    return out


@router.delete("/study/items/{item_id}")
def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _item_or_404(db, user.id, item_id)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "item_id": item_id}


# ---------------------------------------------------------------- 新词词库
# 每日新词上限已取消（用户要求「选多少加多少」）：保留 used_today 供展示，
# 但不再有 DAILY_NEW_WORDS 常量，也不再用它截断 added / 禁用按钮。
MAX_VOCAB_PULL = 200  # 一次最多取多少个词，防手滑传个 99999


def _learned_word_terms(db: OrmSession, user_id: int) -> set[str]:
    """已经进过学习清单的单词（小写），用来避开重复推荐。"""
    rows = (
        db.query(StudyItem.term)
        .filter(StudyItem.user_id == user_id, StudyItem.kind == "word")
        .all()
    )
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _vocab_used_today(db: OrmSession, user_id: int) -> int:
    """今天用词库加了几张新词卡（只用于展示，不再限制）。"""
    today = utcnow().date()
    rows = (
        db.query(StudyItem.created_at)
        .filter(
            StudyItem.user_id == user_id,
            StudyItem.kind == "word",
            StudyItem.source == "vocab",
        )
        .all()
    )
    return sum(1 for (created,) in rows if created and created.date() == today)


def _scope_or_default(raw: str | None, user: User) -> str:
    scope = (raw or "").strip().lower() or (user.word_scope or "").strip().lower()
    if scope not in wordbank.scope_ids():
        scope = wordbank.default_scope()
    return scope


@router.get("/study/vocab", response_model=VocabOut)
def vocab_next(
    scope: str | None = None,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """「今天学几个新词」：取该范围里用户还没有卡的词，顺带给出范围和进度。"""
    scope_id = (scope or "").strip().lower() or None
    if scope_id and scope_id not in wordbank.scope_ids():
        raise HTTPException(status_code=400, detail="单词范围不存在")
    scope_id = _scope_or_default(scope_id, user)
    limit = max(1, min(limit, MAX_VOCAB_PULL))
    learned = _learned_word_terms(db, user.id)
    info = wordbank.totals(scope_id, learned)
    return VocabOut(
        scope=scope_id,
        name=info["name"],
        desc=info["desc"],
        total=info["total"],
        learned=info["learned"],
        remaining=info["remaining"],
        used_today=_vocab_used_today(db, user.id),
        items=wordbank.next_words(scope_id, learned, limit),
        scopes=wordbank.scopes_out(learned),
    )


@router.post("/study/vocab/add", response_model=VocabAddOut)
def vocab_add(
    body: VocabAddIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """把新词落成卡（kind=word, source=vocab），复用 §16 的 SRS，不另起调度。

    去重按 `(user_id, term, kind)`（词不分大小写）；每日新词上限 20，
    超出的部分不计入 `added`，用 `limited` 报给前端，而不是静默丢弃。
    """
    scope_id = (body.scope or "").strip().lower() or None
    if scope_id and scope_id not in wordbank.scope_ids():
        raise HTTPException(status_code=400, detail="单词范围不存在")
    scope_id = _scope_or_default(scope_id, user)

    learned = _learned_word_terms(db, user.id)
    requested: list[str] = []
    for raw in body.terms or []:
        term = str(raw or "").strip()
        if term:
            requested.append(term)
    if not requested and body.count:
        count = max(1, min(int(body.count), MAX_VOCAB_PULL))
        requested = [w["term"] for w in wordbank.next_words(scope_id, learned, count)]
    if not requested:
        raise HTTPException(status_code=400, detail="没有要加入的新词")

    added_rows = []
    skipped = 0
    seen = set()
    for term in requested:
        key = term.lower()
        if key in learned or key in seen:
            skipped += 1
            continue
        seen.add(key)
        found = wordbank.find(term, scope_id)
        if not found:
            skipped += 1
            continue
        entry, found_scope = found
        card = wordbank.word_out(entry, found_scope)
        row = StudyItem(
            user_id=user.id,
            kind="word",
            term=card["term"][:MAX_TERM],
            context="",
            meaning_zh=(card["pos"] + " " + card["meaning_zh"]).strip(),
            example=card["example"],
            related_json=__import__("json").dumps(card["related"], ensure_ascii=False),
            source="vocab",
            due_at=utcnow(),  # 新词当天进复习队列
        )
        db.add(row)
        added_rows.append(row)

    if not added_rows and not skipped:
        raise HTTPException(status_code=404, detail="词库里没有这些词")
    db.commit()
    for row in added_rows:
        db.refresh(row)
    return VocabAddOut(
        added=len(added_rows),
        skipped=skipped,
        limited=0,
        used_today=_vocab_used_today(db, user.id),
        items=[item_out(row) for row in added_rows],
    )


# ---------------------------------------------------------------- 语法卡 / 口语卡
def _learned_keys(db: OrmSession, user_id: int, kind: str) -> set[str]:
    rows = (
        db.query(StudyItem.term)
        .filter(StudyItem.user_id == user_id, StudyItem.kind == kind)
        .all()
    )
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _add_cards(db: OrmSession, user_id: int, cards: list[dict]) -> tuple[list[StudyItem], int]:
    """按 (user_id, kind, term) 去重后建卡；返回 (新建的卡, 跳过数)。"""
    existing = {
        (row.kind, (row.term or "").strip().lower())
        for row in db.query(StudyItem).filter(StudyItem.user_id == user_id).all()
    }
    added: list[StudyItem] = []
    skipped = 0
    for card in cards:
        key = (card["kind"], card["term"].strip().lower())
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        row = StudyItem(
            user_id=user_id,
            kind=card["kind"],
            term=card["term"][:MAX_TERM],
            context=card.get("context") or "",
            meaning_zh=card.get("meaning_zh") or "",
            example=card.get("example") or "",
            related_json=__import__("json").dumps(card.get("related") or {}, ensure_ascii=False),
            source=card["source"],
            due_at=utcnow(),  # 加进来当天就能复习
        )
        db.add(row)
        added.append(row)
    return added, skipped


@router.get("/study/grammar", response_model=GrammarOut)
def grammar_library(
    group: str | None = None,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """四组语法卡（时态/冠词/介词/从句），带 learned 标记和挖空。"""
    wanted = (group or "").strip().lower() or None
    if wanted and wanted not in library.GRAMMAR_GROUP_ORDER:
        raise HTTPException(status_code=400, detail="语法分组不存在")
    learned = _learned_keys(db, user.id, "grammar")
    groups = []
    total = learned_count = 0
    for data in library.grammar_groups():
        if wanted and data["group"] != wanted:
            continue
        cards = []
        for item in data["items"]:
            blank, answer = library.blank_and_answer(item.get("wrong") or "", item.get("right") or "")
            done = item["point"].strip().lower() in learned
            cards.append(
                GrammarCardOut(
                    id=str(item["id"]),
                    group=data["group"],
                    group_name=data["name"],
                    point=str(item.get("point") or "").strip(),
                    rule=str(item.get("rule") or "").strip(),
                    wrong=str(item.get("wrong") or "").strip(),
                    right=str(item.get("right") or "").strip(),
                    blank=blank,
                    answer=answer,
                    learned=done,
                )
            )
        done_in_group = sum(1 for c in cards if c.learned)
        total += len(cards)
        learned_count += done_in_group
        groups.append(
            GrammarGroupOut(
                id=data["group"],
                name=data["name"],
                desc=data["desc"],
                total=len(cards),
                learned=done_in_group,
                items=cards,
            )
        )
    return GrammarOut(groups=groups, total=total, learned=learned_count)


@router.post("/study/grammar/add", response_model=LibraryAddOut)
def grammar_add(
    body: LibraryAddIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """加语法卡：给 group 加整组，给 ids 加指定卡。"""
    group = (body.group or "").strip().lower() or None
    if group and group not in library.GRAMMAR_GROUP_ORDER:
        raise HTTPException(status_code=400, detail="语法分组不存在")
    ids = {str(x).strip() for x in (body.ids or []) if str(x).strip()}
    if not group and not ids:
        raise HTTPException(status_code=400, detail="给出 group 或 ids")
    cards = []
    for card in library.grammar_cards():
        if ids and card["id"] not in ids:
            continue
        if group and card["group"] != group:
            continue
        cards.append(
            {
                "kind": "grammar",
                "term": card["point"],
                "context": card["wrong"],
                "meaning_zh": card["rule"],
                "example": card["right"],
                "related": {"blank": card["blank"], "answer": card["answer"]},
                "source": "grammar",
            }
        )
    if not cards:
        raise HTTPException(status_code=404, detail="没有找到这些语法卡")
    added, skipped = _add_cards(db, user.id, cards)
    db.commit()
    for row in added:
        db.refresh(row)
    return LibraryAddOut(
        added=len(added),
        skipped=skipped,
        remaining=max(0, len(cards) - len(added)),
        items=[item_out(row) for row in added],
    )


@router.get("/study/spoken", response_model=SpokenOut)
def spoken_library(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    """60 张口语句型卡：书面说法 → 更自然的口语说法 + 为什么。"""
    learned = _learned_keys(db, user.id, "phrase")
    items = []
    for card in library.spoken_items():
        items.append(
            SpokenCardOut(
                id=str(card["id"]),
                formal=str(card.get("formal") or "").strip(),
                natural=str(card.get("natural") or "").strip(),
                why=str(card.get("why") or "").strip(),
                learned=str(card.get("formal") or "").strip().lower() in learned,
            )
        )
    return SpokenOut(
        total=len(items),
        learned=sum(1 for i in items if i.learned),
        items=items,
    )


@router.post("/study/spoken/add", response_model=LibraryAddOut)
def spoken_add(
    body: LibraryAddIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """加口语卡：给 ids 加指定卡，或只给 count 加前几张，都不给时加前 10 张。"""
    ids = {str(x).strip() for x in (body.ids or []) if str(x).strip()}
    count = max(1, min(int(body.count or 10), MAX_VOCAB_PULL))
    existing = {
        (row.term or "").strip().lower()
        for row in db.query(StudyItem)
        .filter(StudyItem.user_id == user.id, StudyItem.kind == "phrase")
        .all()
    }
    cards = []
    for card in library.spoken_items():
        if ids and card["id"] not in ids:
            continue
        if not ids and str(card["formal"]).strip().lower() in existing:
            continue  # 已经有的不占「这次加几张」的名额
        cards.append(
            {
                "kind": "phrase",
                "term": card["formal"],
                "context": "",
                "meaning_zh": card.get("why") or "",
                "example": card["natural"],
                "related": {},
                "source": "spoken",
            }
        )
        if not ids and len(cards) >= count:
            break
    if not cards:
        raise HTTPException(status_code=404, detail="没有找到这些口语卡")
    added, skipped = _add_cards(db, user.id, cards)
    db.commit()
    for row in added:
        db.refresh(row)
    return LibraryAddOut(
        added=len(added),
        skipped=skipped,
        remaining=max(0, len(cards) - len(added)),
        items=[item_out(row) for row in added],
    )


# ---------------------------------------------------------------- 今天（合并队列）
TODAY_GROUPS = (
    ("word", "单词"),
    ("spelling", "拼写"),
    ("grammar", "语法"),
    ("spoken", "口语"),
    ("phrase", "句型"),
)


def _today_key(row: StudyItem) -> str:
    if row.kind == "grammar":
        return "grammar"
    if row.kind == "phrase":
        return "spoken" if row.source == "spoken" else "phrase"
    return row.kind or "word"


@router.get("/study/today", response_model=TodayOut)
def today_queue(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    """「今天」合并队列：到期卡按类型分组，组内按到期时间升序。"""
    now = utcnow()
    rows = (
        db.query(StudyItem)
        .filter(StudyItem.user_id == user.id)
        .order_by(StudyItem.due_at.asc(), StudyItem.id.asc())
        .all()
    )
    buckets: dict[str, list[StudyItem]] = {}
    for row in rows:
        if not is_due(row, now):
            continue
        buckets.setdefault(_today_key(row), []).append(row)
    groups = [
        TodayGroupOut(
            key=key,
            label=label,
            count=len(buckets.get(key, [])),
            items=[item_out(row, now) for row in buckets.get(key, [])],
        )
        for key, label in TODAY_GROUPS
        if buckets.get(key)
    ]
    notes_count = db.query(Note).filter(Note.user_id == user.id).count()
    return TodayOut(groups=groups, total=sum(g.count for g in groups), notes_count=int(notes_count or 0))


# ------------------------------------------------------------------ 笔记
def _note_out(row: Note) -> NoteOut:
    return NoteOut(
        id=row.id,
        title=row.title or "",
        body=row.body or "",
        session_id=row.session_id,
        created_at=utc_iso(row.created_at),
        updated_at=utc_iso(row.updated_at),
    )


def _check_session_owner(db: OrmSession, user_id: int, session_id: int | None) -> None:
    """笔记/学习卡可以挂到某次练习上，但只能挂自己的。"""
    if session_id is None:
        return
    session = db.get(PracticeSession, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")


def _note_or_404(db: OrmSession, user_id: int, note_id: int) -> Note:
    row = db.get(Note, note_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return row


def _title_or_first_line(title: str | None, body: str) -> str:
    """不填标题就取正文首行前 40 字。"""
    text = (title or "").strip()
    if text:
        return text[:128]
    first = (body or "").strip().splitlines()[0] if (body or "").strip() else ""
    return first.strip()[:40]


@router.get("/notes", response_model=list[NoteOut])
def list_notes(user: User = Depends(get_current_user), db: OrmSession = Depends(get_db)):
    rows = (
        db.query(Note)
        .filter(Note.user_id == user.id)
        .order_by(Note.updated_at.desc())
        .all()
    )
    return [_note_out(row) for row in rows]


@router.post("/notes", response_model=NoteOut)
def create_note(
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    text = (body.body or "").strip()
    title = _title_or_first_line(body.title, text)
    if not text and not title:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    _check_session_owner(db, user.id, body.session_id)
    row = Note(user_id=user.id, title=title, body=text, session_id=body.session_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _note_out(row)


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    return _note_out(_note_or_404(db, user.id, note_id))


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    body: NoteIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _note_or_404(db, user.id, note_id)
    text = (body.body or "").strip()
    title = _title_or_first_line(body.title, text)
    if not text and not title:
        raise HTTPException(status_code=400, detail="笔记不能是空的")
    row.title = title
    row.body = text
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _note_out(row)


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    row = _note_or_404(db, user.id, note_id)
    db.delete(row)
    db.commit()
    return {"deleted": 1, "note_id": note_id}
