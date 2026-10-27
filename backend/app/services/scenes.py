SCENES = [
    {
        "id": "job_interview",
        "name": "求职面试",
        "icon": "briefcase",
        "desc": "和 AI 面试官聊一轮自我介绍与项目经历",
        "role": "a friendly technical interviewer at a tech company",
        "opening": "Hi, thanks for coming in today. Could you tell me a bit about yourself?",
    },
    {
        "id": "cafe_order",
        "name": "咖啡店点单",
        "icon": "coffee",
        "desc": "点单、加料、结账的日常对话",
        "role": "a barista at a busy coffee shop",
        "opening": "Hi there! What can I get for you today?",
    },
    {
        "id": "ielts_part1",
        "name": "雅思 Part 1",
        "icon": "book",
        "desc": "雅思口语第一部分常见话题",
        "role": "an IELTS speaking examiner",
        "opening": "Let's talk about where you live. Do you live in a house or an apartment?",
    },
]


def get_scene(scene_id: str):
    for s in SCENES:
        if s["id"] == scene_id:
            return s
    return None


def public_scenes():
    return [
        {"id": s["id"], "name": s["name"], "icon": s["icon"], "desc": s["desc"]}
        for s in SCENES
    ]
