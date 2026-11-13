"""AI 助记、自由扩充与三步学词（学习模块重构方案 §2.2 方案 A 的后端）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import StudyItem, User
from ..schemas import (
    StudyItemOut,
    WordAssistIn,
    WordAssistOut,
    WordImportIn,
    WordImportOut,
    WordLearnIn,
    WordSentenceIn,
    WordSentenceOut,
)
from ..security import get_current_user
from ..services import wordbank
from ..services.llm_config import LLMConfig, get_llm_config
from ..services.study import item_out, learned_word_terms
from ..services.word_assist import (
    MAX_IMPORT,
    assist_word,
    check_sentence,
    is_word,
    normalize_term,
    parse_import,
    word_card_fields,
)
from ..timeutil import utcnow

router = APIRouter(prefix="/api/study/words", tags=["study"])

MAX_TERM = 128


def _word_or_none(db: OrmSession, user_id: int, term: str) -> StudyItem | None:
    wanted = term.strip().lower()
    return next(
        (
            row
            for row in db.query(StudyItem)
            .filter(StudyItem.user_id == user_id, StudyItem.kind == "word")
            .all()
            if (row.term or "").strip().lower() == wanted
        ),
        None,
    )


def _new_word(fields: dict, source: str = "custom") -> StudyItem:
    return StudyItem(
        kind="word",
        term=str(fields.get("term") or "")[:MAX_TERM],
        context=str(fields.get("context") or ""),
        meaning_zh=str(fields.get("meaning_zh") or ""),
        example=str(fields.get("example") or ""),
        related_json=json.dumps(
            fields.get("related") or {"synonyms": [], "antonyms": [], "similar": []},
            ensure_ascii=False,
        ),
        source=source,
        due_at=utcnow(),
    )


@router.post("/assist", response_model=WordAssistOut)
def word_assist(
    body: WordAssistIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    """词根 / 联想 / 搭配 / 场景例句；不写学习卡，只给前端展示。"""
    term = normalize_term(body.term)
    if not is_word(term):
        raise HTTPException(status_code=400, detail="term 必须是一个英文单词")
    return WordAssistOut(**assist_word(term, body.meaning_zh, db, llm))


@router.post("/sentence-check", response_model=WordSentenceOut)
def sentence_check(
    body: WordSentenceIn,
    user: User = Depends(get_current_user),
    llm: LLMConfig = Depends(get_llm_config),
):
    """用步造句反馈；失败一律中性通过，不阻塞学习流程。"""
    term = normalize_term(body.term)
    if not is_word(term):
        raise HTTPException(status_code=400, detail="term 必须是一个英文单词")
    sentence = (body.sentence or "").strip()
    if not sentence:
        raise HTTPException(status_code=400, detail="sentence 不能为空")
    return WordSentenceOut(**check_sentence(term, sentence, llm))


@router.post("/import", response_model=WordImportOut)
def import_words(
    body: WordImportIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
    llm: LLMConfig = Depends(get_llm_config),
):
    """粘贴导入词库外的词：命中词库用静态卡，未命中可走 AI 补卡，失败也落卡。"""
    items = parse_import(body.text)
    if not items:
        raise HTTPException(status_code=400, detail="没有可导入的单词")
    if len(items) > MAX_IMPORT:
        raise HTTPException(status_code=400, detail=f"一次最多导入 {MAX_IMPORT} 个词")

    learned = learned_word_terms(db, user.id)
    added: list[StudyItem] = []
    skipped = 0
    for entry in items:
        key = entry["term"].lower()
        if key in learned:
            skipped += 1
            continue
        found = wordbank.find(entry["term"])
        if found:
            word, scope = found
            card = wordbank.word_out(word, scope)
            fields = {
                "term": card["term"],
                "meaning_zh": f"{card['pos']} {card['meaning_zh']}".strip(),
                "example": card["example"],
                "related": card["related"],
            }
        else:
            fields = word_card_fields(entry["term"], entry["meaning_zh"], db, llm, body.use_ai)
        row = _new_word(fields)
        row.user_id = user.id
        db.add(row)
        learned.add(key)
        added.append(row)

    db.commit()
    for row in added:
        db.refresh(row)
    return WordImportOut(
        added=len(added),
        skipped=skipped,
        items=[item_out(row) for row in added],
    )


@router.post("/learn", response_model=StudyItemOut)
def learn_word(
    body: WordLearnIn,
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """认 / 拼 / 用三步都完成后落卡并进当天复习；已有卡只补缺失字段。"""
    term = normalize_term(body.term)
    if not is_word(term):
        raise HTTPException(status_code=400, detail="term 必须是一个英文单词")
    if not (body.recognized and body.spelled and body.used):
        raise HTTPException(status_code=400, detail="认、拼、用三步都完成后才能加入复习")

    meaning = (body.meaning_zh or "").strip()
    example = (body.example or "").strip()
    context = (body.context or "").strip()
    row = _word_or_none(db, user.id, term)
    if row is not None:
        # 自由扩充先落的是裸卡：学完后只补空字段，不覆盖已有内容
        if meaning and not (row.meaning_zh or "").strip():
            row.meaning_zh = meaning
        if example and not (row.example or "").strip():
            row.example = example
        if context and not (row.context or "").strip():
            row.context = context
        db.commit()
        db.refresh(row)
        return item_out(row)

    row = _new_word(
        {
            "term": term,
            "meaning_zh": meaning,
            "example": example,
            "context": context,
        }
    )
    row.user_id = user.id
    db.add(row)
    db.commit()
    db.refresh(row)
    return item_out(row)
