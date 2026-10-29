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
    {
        "id": "hotel_checkin",
        "name": "酒店入住",
        "icon": "hotel",
        "desc": "报预订、选房型、问早餐和退房时间",
        "role": "a hotel receptionist at the front desk",
        "opening": "Good evening! Do you have a reservation with us?",
    },
    {
        "id": "airport_checkin",
        "name": "机场值机",
        "icon": "plane",
        "desc": "交证件、托运行李、选座位、问登机口",
        "role": "an airline check-in agent at the airport",
        "opening": "Good morning! May I see your passport and booking, please?",
    },
    {
        "id": "restaurant_order",
        "name": "餐厅点餐",
        "icon": "utensils",
        "desc": "点菜、说忌口、加饮料、结账买单",
        "role": "a friendly waiter at a casual restaurant",
        "opening": "Good evening! A table for how many?",
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


# 句型脚手架：A2 卡住时给三种说法，用完不扣分
SCENE_FRAMES = {
    "job_interview": [
        {"en": "I'm currently studying ... at ...", "zh": "我目前在……读……"},
        {"en": "I worked on a project where ...", "zh": "我做过一个项目，在项目里……"},
        {"en": "My role was to ...", "zh": "我的职责是……"},
    ],
    "cafe_order": [
        {"en": "I'd like a ..., please.", "zh": "我要一杯……，谢谢。"},
        {"en": "Could I get that with ...?", "zh": "可以给我加……吗？"},
        {"en": "How much is that?", "zh": "一共多少钱？"},
    ],
    "ielts_part1": [
        {"en": "I live in ... , which is ...", "zh": "我住在……，那里……"},
        {"en": "The main reason is that ...", "zh": "主要原因是……"},
        {"en": "For example, ...", "zh": "比如说……"},
    ],
    "hotel_checkin": [
        {"en": "I have a reservation under the name ...", "zh": "我用……的名字订了房。"},
        {"en": "Does the room include breakfast?", "zh": "房间含早餐吗？"},
        {"en": "What time is check-out?", "zh": "几点退房？"},
    ],
    "airport_checkin": [
        {"en": "Here is my passport and booking.", "zh": "这是我的护照和订票信息。"},
        {"en": "I'd like a window seat, please.", "zh": "我想要靠窗的座位。"},
        {"en": "Which gate is the flight departing from?", "zh": "航班在几号登机口？"},
    ],
    "restaurant_order": [
        {"en": "A table for ..., please.", "zh": "……位，谢谢。"},
        {"en": "I'll have the ..., please.", "zh": "我要一份……。"},
        {"en": "Could we have the bill, please?", "zh": "可以买单吗？"},
    ],
}


def get_frames(scene_id: str):
    if not get_scene(scene_id):
        return None
    return SCENE_FRAMES.get(scene_id, [])
