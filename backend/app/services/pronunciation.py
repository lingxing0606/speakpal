"""最小对立对（minimal pairs）：词表 + 转写判分规则。

不依赖声学模型：让用户读目标词，用浏览器语音识别的转写判断听到的是哪个词。
说错成对手词（ship→sheep）就是发音没区分开，这是可测的。
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z']+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


MINIMAL_PAIR_SETS = [
    {
        "id": "short_i_vs_long_ee",
        "focus": "/ɪ/ vs /iː/",
        "zh_focus": "短音 ship 和长音 sheep 要拉开",
        "pairs": [
            {"a": "ship", "b": "sheep", "zh_a": "船", "zh_b": "羊"},
            {"a": "sit", "b": "seat", "zh_a": "坐", "zh_b": "座位"},
            {"a": "hit", "b": "heat", "zh_a": "打", "zh_b": "热"},
            {"a": "fit", "b": "feet", "zh_a": "合身", "zh_b": "脚（复数）"},
            {"a": "live", "b": "leave", "zh_a": "住", "zh_b": "离开"},
            {"a": "bin", "b": "bean", "zh_a": "垃圾桶", "zh_b": "豆子"},
            {"a": "chip", "b": "cheap", "zh_a": "薯片", "zh_b": "便宜"},
            {"a": "lip", "b": "leap", "zh_a": "嘴唇", "zh_b": "跳跃"},
            {"a": "bit", "b": "beat", "zh_a": "一点", "zh_b": "打败"},
            {"a": "slip", "b": "sleep", "zh_a": "滑倒", "zh_b": "睡觉"},
        ],
    },
    {
        "id": "th_vs_s",
        "focus": "/θ/ vs /s/",
        "zh_focus": "咬舌尖的 th 别读成 s",
        "pairs": [
            {"a": "think", "b": "sink", "zh_a": "想", "zh_b": "水槽"},
            {"a": "thick", "b": "sick", "zh_a": "厚", "zh_b": "生病"},
            {"a": "thin", "b": "sin", "zh_a": "薄", "zh_b": "罪"},
            {"a": "thought", "b": "sought", "zh_a": "想（过去式）", "zh_b": "寻找（过去式）"},
            {"a": "path", "b": "pass", "zh_a": "小路", "zh_b": "通过"},
            {"a": "bath", "b": "bass", "zh_a": "洗澡", "zh_b": "低音"},
            {"a": "moth", "b": "moss", "zh_a": "飞蛾", "zh_b": "苔藓"},
            {"a": "faith", "b": "face", "zh_a": "信念", "zh_b": "脸"},
            {"a": "mouth", "b": "mouse", "zh_a": "嘴", "zh_b": "老鼠"},
            {"a": "thumb", "b": "sum", "zh_a": "拇指", "zh_b": "总数"},
        ],
    },
]


def _find_pair(target: str):
    word = (target or "").strip().lower()
    for group in MINIMAL_PAIR_SETS:
        for pair in group["pairs"]:
            if word in (pair["a"], pair["b"]):
                return group, pair
    return None, None


def check_pronunciation(target: str, heard: str) -> dict:
    """判断转写里听到的是目标词还是它的对手词。

    - 听到目标词 → correct
    - 听到对手词 → 明确 incorrect，并告诉用户「你读成了另一个词」
    - 都没听到 → incorrect，提示再说一遍
    """
    group, pair = _find_pair(target)
    words = _words(heard)
    target_word = (target or "").strip().lower()
    if pair is None:
        return {
            "correct": target_word in words,
            "target": target_word,
            "heard": " ".join(words),
            "partner_heard": None,
            "focus": None,
            "zh_focus": None,
            "reason": "不在词表里，只做字面匹配",
        }
    partner = pair["b"] if target_word == pair["a"] else pair["a"]
    partner_heard = partner in words
    correct = (target_word in words) and not partner_heard
    reason = "听到目标词" if correct else ("读成了对手词，注意区分" if partner_heard else "没听清，再说一遍")
    return {
        "correct": correct,
        "target": target_word,
        "heard": " ".join(words),
        "partner_heard": partner if partner_heard else None,
        "focus": group["focus"],
        "zh_focus": group["zh_focus"],
        "reason": reason,
    }
