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
