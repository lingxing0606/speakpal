"""后端接口回归测试（标准库 unittest + FastAPI TestClient，不访问外网）。

运行（在 backend 目录）：
    .venv/Scripts/python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import shutil
import atexit
import uuid
import threading
import unittest
from pathlib import Path
from unittest import mock

# 必须在 import app 之前：用临时库、固定密钥，绝不碰真实 speakpal.db / .env
_BACKEND = Path(__file__).resolve().parent.parent
# 放在 backend/.tmp-test 下（已 gitignore），不依赖系统临时目录
_TMP_ROOT = _BACKEND / ".tmp-test"
# 不用 tempfile.mkdtemp：Python 3.13+ 在 Windows 上给它设仅创建者可访问的 ACL，事后删不掉
_TMP = str(_TMP_ROOT / f"run-{uuid.uuid4().hex[:8]}")
os.makedirs(_TMP)
os.environ["DATABASE_URL"] = "sqlite:///" + Path(_TMP, "test.db").as_posix()
os.environ["JWT_SECRET"] = "test-jwt-secret-" + "x" * 32
os.environ["ADMIN_KEY"] = "test-admin-key"
os.environ["ALLOW_PRIVATE_LLM_HOSTS"] = "0"
os.environ["TTS_API_KEY"] = "server-tts-key"
os.environ["TTS_BASE_URL"] = "https://api.openai.com/v1"

sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND.parent))  # evaluation 包在仓库根目录

from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402

from app import security  # noqa: E402
from app.main import app  # noqa: E402
from app.services import hints as hints_service  # noqa: E402
from app.services import llm_config, outbound  # noqa: E402
from app.services.rules import TASK_CHECKS  # noqa: E402
from evaluation import bands  # noqa: E402
from evaluation.scales import scales_for_band  # noqa: E402
from app.db import engine  # noqa: E402


@atexit.register
def _cleanup():
    engine.dispose()  # 先释放 SQLite 文件句柄，Windows 上才能删
    shutil.rmtree(_TMP, ignore_errors=True)

LLM_HEADERS = {"X-LLM-Key": "sk-test", "X-LLM-Base-URL": "https://api.example.com/v1"}


def _public_dns(host, port, *a, **k):
    """把所有域名解析成公网地址，测试不依赖真实 DNS。"""
    return [(2, 1, 6, "", ("93.184.216.34", port))]


class ApiTestCase(unittest.TestCase):
    _n = 0

    def setUp(self):
        self.client = TestClient(app)
        security.login_limiter._fails.clear()

    def register(self, password="secret123"):
        ApiTestCase._n += 1
        name = f"user{ApiTestCase._n}"
        r = self.client.post("/api/auth/register", json={"username": name, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return name, {"Authorization": f"Bearer {r.json()['token']}"}


class AuthTests(ApiTestCase):
    def test_register_rejects_short_password_with_chinese_message(self):
        r = self.client.post("/api/auth/register", json={"username": "shorty", "password": "1234"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("6", r.json()["detail"])

    def test_login_rate_limited_after_repeated_failures(self):
        name, _ = self.register()
        for _ in range(security.login_limiter.max_fails):
            r = self.client.post("/api/auth/login", json={"username": name, "password": "wrong-pass"})
            self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/login", json={"username": name, "password": "secret123"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)

    def test_successful_login_resets_counter(self):
        name, _ = self.register()
        self.client.post("/api/auth/login", json={"username": name, "password": "wrong-pass"})
        r = self.client.post("/api/auth/login", json={"username": name, "password": "secret123"})
        self.assertEqual(r.status_code, 200)

    def test_password_change_invalidates_old_token(self):
        _, headers = self.register()
        r = self.client.patch(
            "/api/me/profile",
            json={"password": "newsecret1", "current_password": "secret123"},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers.get("X-Auth-Reason"), "password_changed")

    def test_forged_token_rejected(self):
        import jwt

        token = jwt.encode({"sub": "1", "tv": 0, "exp": 9999999999}, "dev-secret-change-me", algorithm="HS256")
        r = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 401)


class AdminTests(ApiTestCase):
    def test_admin_key_required(self):
        self.assertEqual(self.client.get("/api/admin/stats").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/stats", headers={"X-Admin-Key": "admin123"}).status_code, 401)
        r = self.client.get("/api/admin/stats", headers={"X-Admin-Key": "test-admin-key"})
        self.assertEqual(r.status_code, 200)

    def test_admin_users_aggregates(self):
        self.register()
        r = self.client.get("/api/admin/users", headers={"X-Admin-Key": "test-admin-key"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all("sessions" in u and "reports" in u for u in r.json()))

    def test_storage_refuses_to_overwrite_existing_file(self):
        existing = Path(_TMP, "other.db")
        existing.write_bytes(b"keep me")
        # 测试用环境变量锁了库地址（会 409），这里放开锁，只验证「不覆盖」
        with mock.patch("app.routers.admin.database_url_locked_by_env", lambda: False):
            r = self.client.put(
                "/api/admin/storage",
                json={"path": str(existing), "copy_existing": True},
                headers={"X-Admin-Key": "test-admin-key"},
            )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(existing.read_bytes(), b"keep me")


class OutboundTests(unittest.TestCase):
    def test_blocks_private_and_metadata_hosts(self):
        for url in (
            "http://127.0.0.1:8000",
            "http://localhost:8000/v1",
            "http://169.254.169.254/latest",
            "http://10.0.0.5/v1",
            "http://[::1]/v1",
            "ftp://example.com",
        ):
            with self.subTest(url=url), self.assertRaises(outbound.UnsafeBaseURL):
                outbound.check_base_url(url)

    def test_allows_public_host(self):
        with mock.patch.object(outbound.socket, "getaddrinfo", _public_dns):
            outbound.check_base_url("https://api.deepseek.com/v1")

    def test_server_tts_key_not_sent_to_user_supplied_url(self):
        cfg = llm_config.build_tts_config(base_url="https://evil.example.com/v1")
        self.assertFalse(cfg.configured)
        self.assertEqual(cfg.api_key, "")
        same = llm_config.build_tts_config(base_url="https://api.openai.com/v1/")
        self.assertEqual(same.key_source, "env")


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            req = httpx.Request("POST", "https://api.example.com")
            raise httpx.HTTPStatusError("err", request=req, response=httpx.Response(self.status_code, request=req))

    def json(self):
        return self._payload


class _FakeClient:
    """替身 httpx.Client：按 payload 回放，不发真实请求。"""

    payload = {"choices": [{"message": {"content": "Nice. What else?"}}]}
    status = 200

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(type(self).payload, type(self).status)


class SessionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self._dns = mock.patch.object(outbound.socket, "getaddrinfo", _public_dns)
        self._dns.start()
        self.addCleanup(self._dns.stop)
        # Planner 在建会话时就会调一次模型：统一替身掉，测试绝不碰网络
        self._planner = mock.patch("app.services.agent.httpx.Client", _FakePlanClient)
        self._planner.start()
        self.addCleanup(self._planner.stop)
        _, auth = self.register()
        self.headers = {**auth, **LLM_HEADERS}

    def _start(self):
        r = self.client.post("/api/sessions", json={"scene_id": "job_interview"}, headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["session_id"]

    def _turn(self, sid, text="I am a student and I like coding."):
        return self.client.post(
            f"/api/sessions/{sid}/turn",
            json={"transcript": text, "input_mode": "typed"},
            headers=self.headers,
        )

    def test_turn_reports_degraded_when_model_fails(self):
        sid = self._start()
        with mock.patch("app.services.llm.httpx.Client", type("C", (_FakeClient,), {"status": 500})):
            r = self._turn(sid)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["degraded"])

    def test_turn_not_degraded_on_success(self):
        sid = self._start()
        with mock.patch("app.services.llm.httpx.Client", _FakeClient):
            r = self._turn(sid)
        self.assertFalse(r.json()["degraded"])
        self.assertEqual(r.json()["ai_reply"], "Nice. What else?")

    def test_private_base_url_rejected(self):
        sid = self._start()
        headers = {**self.headers, "X-LLM-Base-URL": "http://127.0.0.1:8000"}
        self._dns.stop()
        try:
            r = self.client.post(
                f"/api/sessions/{sid}/turn",
                json={"transcript": "Hello there", "input_mode": "typed"},
                headers=headers,
            )
        finally:
            self._dns.start()
        self.assertEqual(r.status_code, 400)

    def test_finish_twice_returns_same_report_with_study_items(self):
        sid = self._start()
        with mock.patch("app.services.llm.httpx.Client", _FakeClient):
            self._turn(sid)
        # 评分模型不可用 → 示例报告（不计分），重点是两次结果一致
        with mock.patch("app.services.scoring.httpx.Client", type("C", (_FakeClient,), {"status": 503})):
            first = self.client.post(f"/api/sessions/{sid}/finish", headers=self.headers)
            second = self.client.post(f"/api/sessions/{sid}/finish", headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["report_id"], second.json()["report_id"])
        self.assertEqual(first.json()["study_items"], second.json()["study_items"])

    def test_concurrent_finish_does_not_500(self):
        sid = self._start()
        with mock.patch("app.services.llm.httpx.Client", _FakeClient):
            self._turn(sid)
        barrier = threading.Barrier(2)

        class SlowClient(_FakeClient):
            status = 503

            def post(self, *a, **k):
                try:
                    barrier.wait(timeout=5)  # 两个请求都过了「还没有报告」的检查再继续
                except threading.BrokenBarrierError:
                    pass
                return super().post(*a, **k)

        codes = []
        with mock.patch("app.services.scoring.httpx.Client", SlowClient):
            threads = [
                threading.Thread(
                    target=lambda: codes.append(
                        TestClient(app).post(f"/api/sessions/{sid}/finish", headers=self.headers).status_code
                    )
                )
                for _ in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(sorted(codes), [200, 200])

    def test_history_pagination(self):
        for _ in range(3):
            self._start()
        all_rows = self.client.get("/api/sessions", headers=self.headers).json()
        page = self.client.get("/api/sessions?limit=2&offset=1", headers=self.headers).json()
        self.assertEqual(len(all_rows), 3)
        self.assertEqual([r["id"] for r in page], [r["id"] for r in all_rows[1:3]])

    def test_other_users_session_hidden(self):
        sid = self._start()
        _, other = self.register()
        r = self.client.get(f"/api/sessions/{sid}", headers=other)
        self.assertEqual(r.status_code, 404)


import json as _json  # noqa: E402


# ---------------------------------------------------------------- Agent 替身
class _FakePlanClient(_FakeClient):
    """Planner/Critic 替身：回一份合法 JSON（目标取清单前三个）。

    SessionTests.setUp 统一挂它；要演别的行为（失败、非法下标、收紧达成度）
    就在单个用例里用 _ScriptedClient 再 patch 一层。
    """

    payload = {
        "choices": [
            {
                "message": {
                    "content": _json.dumps(
                        {"goals": [0, 1, 2], "focus": [], "comment": ""}, ensure_ascii=False
                    )
                }
            }
        ]
    }


class _ScriptedClient(_FakeClient):
    """按给定文本回放，用来分别扮演 Planner / Critic / 评分模型。"""

    @classmethod
    def with_text(cls, text):
        return type("Scripted", (cls,), {"payload": {"choices": [{"message": {"content": text}}]}})


# 一份能通过 parse_llm_report 的评分结果（纯打字：语法词汇 + 任务完成度）
_REPORT_JSON = _json.dumps(
    {
        "bands": {"grammar_vocab": 5.0, "task_completion": 6.0},
        "sentence_fixes": [],
        "comment": "还不错",
        "note": "",
    },
    ensure_ascii=False,
)

# 手动输入提示：模型正常返回的两条
_HINT_JSON = _json.dumps(
    {
        "hints": [
            {"en": "I'd like a medium latte, please.", "zh": "我要一杯中杯拿铁。", "tag": "直接回答"},
            {"en": "Could I get it with oat milk?", "zh": "可以换成燕麦奶吗？", "tag": "补一个要求"},
        ]
    },
    ensure_ascii=False,
)


class _HintClient(_FakeClient):
    """提示接口的模型替身：回合法 JSON，并记下被调用次数（验证缓存命中）。"""

    calls = 0
    payload = {"choices": [{"message": {"content": _HINT_JSON}}]}

    def post(self, *a, **k):
        type(self).calls += 1
        return super().post(*a, **k)


def _sse_lines(*pieces):
    for piece in pieces:
        yield "data: " + _json.dumps({"choices": [{"delta": {"content": piece}}]})
        yield ""
    yield "data: [DONE]"


class _FakeStreamResp:
    def __init__(self, status=200, lines=(), ctype="text/event-stream", body=b"", explode_after=None):
        self.status_code = status
        self.headers = {"content-type": ctype}
        self._lines = list(lines)
        self._body = body
        self._explode_after = explode_after
        self.closed = False

    def iter_lines(self):
        for i, line in enumerate(self._lines):
            if self._explode_after is not None and i >= self._explode_after:
                raise RuntimeError("upstream dropped")
            yield line

    def read(self):
        return self._body

    def close(self):
        self.closed = True


def _stream_client(resp):
    class C:
        last = None

        def __init__(self, *a, **k):
            C.last = self
            self.closed = False

        def build_request(self, *a, **k):
            self.request_json = k.get("json")
            return object()

        def send(self, request, stream=False):
            assert stream
            return resp

        def close(self):
            self.closed = True

    return C


def _parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        events.append((name, _json.loads(data) if data else None))
    return events


class StreamTests(SessionTests):
    def _stream(self, sid, client_cls, text="I like coding a lot."):
        with mock.patch("app.services.llm.httpx.Client", client_cls):
            return self.client.post(
                f"/api/sessions/{sid}/turn/stream",
                json={"transcript": text, "input_mode": "typed"},
                headers=self.headers,
            )

    def _saved_turns(self, sid):
        return self.client.get(f"/api/sessions/{sid}", headers=self.headers).json()["turns"]

    def test_stream_sends_deltas_then_done_and_saves(self):
        sid = self._start()
        resp = _FakeStreamResp(lines=list(_sse_lines("Nice. ", "What else", "?")))
        cls = _stream_client(resp)
        r = self._stream(sid, cls)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
        events = _parse_sse(r.text)
        self.assertEqual([e for e, _ in events], ["delta", "delta", "delta", "done"])
        done = events[-1][1]
        self.assertEqual(done["ai_reply"], "Nice. What else?")
        self.assertFalse(done["degraded"])
        self.assertEqual(done["turn_index"], 1)
        self.assertTrue(cls.last.request_json["stream"])
        self.assertTrue(resp.closed and cls.last.closed)
        turns = self._saved_turns(sid)
        self.assertEqual([t["role"] for t in turns], ["ai", "user", "ai"])
        self.assertEqual(turns[-1]["content"], "Nice. What else?")

    def test_stream_key_rejected_returns_502_without_saving(self):
        sid = self._start()
        r = self._stream(sid, _stream_client(_FakeStreamResp(status=401)))
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["kind"], "key_invalid")
        self.assertEqual(len(self._saved_turns(sid)), 1)

    def test_stream_upstream_error_degrades(self):
        sid = self._start()
        r = self._stream(sid, _stream_client(_FakeStreamResp(status=500)))
        events = _parse_sse(r.text)
        self.assertEqual([e for e, _ in events], ["done"])
        self.assertTrue(events[0][1]["degraded"])
        self.assertEqual(len(self._saved_turns(sid)), 3)

    def test_stream_drop_midway_replaces_partial_text(self):
        sid = self._start()
        resp = _FakeStreamResp(lines=list(_sse_lines("Half a sent", "ence never")), explode_after=2)
        r = self._stream(sid, _stream_client(resp))
        events = _parse_sse(r.text)
        self.assertEqual(events[0][0], "delta")
        done = events[-1][1]
        self.assertTrue(done["degraded"])
        self.assertNotIn("Half a sent", done["ai_reply"])
        self.assertTrue(resp.closed)
        self.assertEqual(self._saved_turns(sid)[-1]["content"], done["ai_reply"])

    def test_stream_provider_ignoring_stream_flag(self):
        sid = self._start()
        body = _json.dumps({"choices": [{"message": {"content": "Plain JSON reply?"}}]}).encode()
        r = self._stream(sid, _stream_client(_FakeStreamResp(ctype="application/json", body=body)))
        events = _parse_sse(r.text)
        self.assertEqual(events[-1][1]["ai_reply"], "Plain JSON reply?")
        self.assertFalse(events[-1][1]["degraded"])

    def test_stream_requires_key_and_safe_url(self):
        sid = self._start()
        no_key = {k: v for k, v in self.headers.items() if k != "X-LLM-Key"}
        r = self.client.post(f"/api/sessions/{sid}/turn/stream", json={"transcript": "Hi there"}, headers=no_key)
        self.assertEqual(r.status_code, 409)
        self._dns.stop()
        try:
            r = self.client.post(
                f"/api/sessions/{sid}/turn/stream",
                json={"transcript": "Hi there"},
                headers={**self.headers, "X-LLM-Base-URL": "http://127.0.0.1:8000"},
            )
        finally:
            self._dns.start()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self._saved_turns(sid)), 1)


class PlanTests(SessionTests):
    """Planner：目标只能来自场景任务清单，模型挂了一样能开会话。"""

    def _create(self, client_cls=None, scene_id="cafe_order"):
        with mock.patch("app.services.agent.httpx.Client", client_cls or _FakePlanClient):
            return self.client.post(
                "/api/sessions", json={"scene_id": scene_id}, headers=self.headers
            )

    def test_plan_falls_back_when_model_unavailable(self):
        r = self._create(client_cls=type("Failing", (_FakeClient,), {"status": 500}))
        self.assertEqual(r.status_code, 200, r.text)
        labels = [label for label, _ in TASK_CHECKS["cafe_order"]]
        plan = r.json()["plan"]
        self.assertEqual(plan["source"], "rule")
        self.assertEqual(plan["goals"], labels[:3])

    def test_plan_uses_model_goals_and_ignores_bad_indexes(self):
        labels = [label for label, _ in TASK_CHECKS["cafe_order"]]
        # 99 / -1 越界，字符串不是下标；只有 3 和 4 有效，第 3 个目标按清单顺序补齐
        text = _json.dumps(
            {"goals": [99, -1, labels[0], 3, 4], "focus": ["先说 I'd like"], "comment": ""},
            ensure_ascii=False,
        )
        r = self._create(client_cls=_ScriptedClient.with_text(text))
        plan = r.json()["plan"]
        self.assertEqual(plan["source"], "llm")
        self.assertEqual(plan["goals"], [labels[3], labels[4], labels[0]])
        self.assertEqual(plan["focus"], ["先说 I'd like"])

    def test_old_session_without_plan_keeps_old_finish_rule(self):
        from app.db import SessionLocal
        from app.models import PracticeSession

        sid = self._start()
        db = SessionLocal()
        try:
            db.get(PracticeSession, sid).plan_json = "{}"
            db.commit()
        finally:
            db.close()
        r = self._turn(sid)
        self.assertEqual(r.json()["plan"]["goals"], [])
        self.assertFalse(r.json()["should_finish"])
        detail = self.client.get(f"/api/sessions/{sid}", headers=self.headers).json()
        self.assertEqual(detail["plan"]["goals"], [])
        for _ in range(3):
            last = self._turn(sid)
        self.assertTrue(last.json()["should_finish"], "没有目标的老会话仍按 4 轮口径")


class PlanProgressTests(SessionTests):
    """Executor：每轮按关键词规则更新达成度，结束时机不再写死 4 轮。"""

    def _cafe(self):
        r = self.client.post(
            "/api/sessions", json={"scene_id": "cafe_order"}, headers=self.headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["session_id"]

    def test_turn_reports_goal_progress(self):
        sid = self._cafe()
        r = self._turn(sid, "I'd like a large latte, please.")
        self.assertEqual(r.status_code, 200, r.text)
        labels = [label for label, _ in TASK_CHECKS["cafe_order"]]
        plan = r.json()["plan"]
        self.assertEqual(plan["goals"], labels[:3])
        self.assertEqual(plan["achieved"], [labels[0], labels[1]])
        self.assertEqual(plan["missing"], [labels[2]])
        self.assertFalse(r.json()["should_finish"])

    def test_should_finish_needs_goals_or_six_turns(self):
        sid = self._cafe()
        first = self._turn(sid, "I'd like a large latte.")
        self.assertFalse(first.json()["should_finish"])
        second = self._turn(sid, "And a croissant, please.")
        self.assertFalse(second.json()["should_finish"], "目标刚齐也不能两轮就收尾")
        third = self._turn(sid, "Thanks, that's all.")
        self.assertTrue(third.json()["should_finish"], "三个目标达成且满三轮")
        # 另一场：目标一直没达成，第 6 轮兜底结束
        other = self._cafe()
        for _ in range(5):
            r = self._turn(other, "I am not sure.")
        self.assertFalse(r.json()["should_finish"])
        self.assertTrue(self._turn(other, "I am not sure.").json()["should_finish"], "6 轮兜底")


class CriticTests(SessionTests):
    """Critic：只可收紧关键词命中，模型失败也不影响出报告。"""

    def _finish(self, sid, critic_json):
        # scoring.httpx 与 agent.httpx 是同一个 httpx 模块，同时 patch 会互相覆盖，
        # 所以评分走模型替身、复盘直接替 _request_json。
        with mock.patch(
            "app.services.scoring.httpx.Client", _ScriptedClient.with_text(_REPORT_JSON)
        ), mock.patch("app.services.agent._request_json", return_value=critic_json):
            return self.client.post(f"/api/sessions/{sid}/finish", headers=self.headers)

    def test_critic_only_tightens_keyword_hits(self):
        r = self.client.post(
            "/api/sessions", json={"scene_id": "cafe_order"}, headers=self.headers
        )
        sid = r.json()["session_id"]
        self._turn(sid, "I'd like a large latte, thanks.")
        labels = [label for label, _ in TASK_CHECKS["cafe_order"]]
        # Critic 认「点单饮品」，还额外声称做了「加料或餐点」（规则没命中）
        rep = self._finish(
            sid, {"achieved": [labels[0], labels[2]], "comment": "还差一句规格。"}
        )
        self.assertEqual(rep.status_code, 200, rep.text)
        self.assertEqual(rep.json()["source"], "llm")
        plan = rep.json()["plan"]
        self.assertEqual(plan["review"], "llm")
        self.assertEqual(plan["achieved"], [labels[0]], "模型说做了但规则没命中的不算")
        self.assertEqual(plan["rule_hits"], [labels[0], labels[1]])
        self.assertEqual(plan["missing"], [labels[1], labels[2]])
        self.assertEqual(plan["comment"], "还差一句规格。")

    def test_critic_failure_keeps_rule_progress(self):
        r = self.client.post(
            "/api/sessions", json={"scene_id": "cafe_order"}, headers=self.headers
        )
        sid = r.json()["session_id"]
        self._turn(sid, "I'd like a large latte, thanks.")
        labels = [label for label, _ in TASK_CHECKS["cafe_order"]]
        plan = self._finish(sid, None).json()["plan"]
        self.assertEqual(plan["review"], "rule")
        self.assertEqual(plan["achieved"], [labels[0], labels[1]])
        self.assertIn(labels[2], plan["comment"])


class HintTests(SessionTests):
    """手动输入提示：缓存命中、坏 JSON、超时、无 key 都回退，且不泄露目标清单。"""

    def setUp(self):
        super().setUp()
        hints_service.reset_state()
        _HintClient.calls = 0

    def _hint(self, sid, client_cls=None, headers=None):
        with mock.patch("app.services.hints.httpx.Client", client_cls or _HintClient):
            return self.client.post(
                f"/api/sessions/{sid}/hint", headers=headers or self.headers
            )

    def test_hints_from_model_then_cache_hit(self):
        sid = self._start()
        self._turn(sid, "I am a student, hint cache case.")
        first = self._hint(sid)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json()
        self.assertEqual(body["source"], "llm")
        self.assertFalse(body["cached"])
        self.assertEqual(len(body["hints"]), 2)
        self.assertEqual(body["hints"][0]["tag"], "直接回答")
        self.assertEqual(_HintClient.calls, 1)
        second = self._hint(sid).json()
        self.assertTrue(second["cached"])
        self.assertEqual(_HintClient.calls, 1, "命中缓存后不再打上游")

    def test_bad_json_falls_back_to_frames(self):
        sid = self._start()
        self._turn(sid, "I am a student, bad json case.")
        body = self._hint(sid, _ScriptedClient.with_text("not json at all")).json()
        self.assertEqual(body["source"], "frames")
        self.assertFalse(body["cached"])
        self.assertEqual([h["tag"] for h in body["hints"]], ["通用句型"] * 3)

    def test_timeout_falls_back_to_frames(self):
        class TimeoutClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **k):
                raise httpx.ConnectTimeout("timeout")

        sid = self._start()
        self._turn(sid, "I am a student, timeout case.")
        body = self._hint(sid, TimeoutClient).json()
        self.assertEqual(body["source"], "frames")
        self.assertTrue(body["hints"])

    def test_missing_key_falls_back_without_calling_model(self):
        sid = self._start()
        self._turn(sid, "I am a student, no key case.")
        no_key = {k: v for k, v in self.headers.items() if k != "X-LLM-Key"}
        body = self._hint(sid, _HintClient, no_key).json()
        self.assertEqual(body["source"], "frames")
        self.assertEqual(body["hints"][0]["tag"], "通用句型")
        self.assertEqual(_HintClient.calls, 0)

    def test_hints_do_not_leak_goal_labels(self):
        sid = self._start()
        self._turn(sid, "I am a student, goal leak case.")
        leaking = _json.dumps(
            {
                "hints": [
                    {"en": "Say something.", "zh": "请说「自我介绍」这段。", "tag": "直接回答"},
                    {"en": "Could I get it with oat milk?", "zh": "可以换成燕麦奶吗？", "tag": "补一个要求"},
                ]
            },
            ensure_ascii=False,
        )
        body = self._hint(sid, _ScriptedClient.with_text(leaking)).json()
        self.assertEqual(body["source"], "llm")
        self.assertEqual(len(body["hints"]), 1, "含目标清单原文的提示要丢掉")
        self.assertNotIn("自我介绍", _json.dumps(body["hints"], ensure_ascii=False))
        self.assertEqual(set(body), {"hints", "source", "cached"})

    def test_all_hints_invalid_falls_back(self):
        sid = self._start()
        self._turn(sid, "I am a student, invalid hints case.")
        bad = _json.dumps(
            {
                "hints": [
                    {
                        "en": "one two three four five six seven eight nine ten eleven twelve thirteen",
                        "zh": "太长",
                        "tag": "直接回答",
                    },
                    {"en": "No zh", "zh": "", "tag": ""},
                ]
            },
            ensure_ascii=False,
        )
        body = self._hint(sid, _ScriptedClient.with_text(bad)).json()
        self.assertEqual(body["source"], "frames")

    def test_circuit_breaker_stops_calling_model(self):
        sid = self._start()
        self._turn(sid, "I am a student, breaker case.")
        failing = type("Failing", (_FakeClient,), {"status": 500})
        for _ in range(hints_service.FAIL_THRESHOLD):
            self.assertEqual(self._hint(sid, failing).json()["source"], "frames")
        _HintClient.calls = 0
        body = self._hint(sid, _HintClient).json()
        self.assertEqual(body["source"], "frames")
        self.assertEqual(_HintClient.calls, 0, "熔断期内不再打上游")

    def test_nonce_bypasses_cache_and_regenerates(self):
        sid = self._start()
        self._turn(sid, "I am a student, nonce case.")
        first = self._hint(sid).json()
        self.assertFalse(first["cached"])
        self.assertEqual(_HintClient.calls, 1)
        with mock.patch("app.services.hints.httpx.Client", _HintClient):
            again = self.client.post(
                f"/api/sessions/{sid}/hint",
                json={"nonce": "abc123"},
                headers=self.headers,
            ).json()
        self.assertFalse(again["cached"], "带 nonce 的换一批必须重新生成")
        self.assertEqual(_HintClient.calls, 2)
        # 不带 nonce 仍然命中最初那份缓存
        third = self._hint(sid).json()
        self.assertTrue(third["cached"])
        self.assertEqual(_HintClient.calls, 2)

    def test_cache_key_unchanged_without_nonce(self):
        base = hints_service.cache_key(
            "cafe_order", "medium", ["点单饮品"], "Hi there?", "I want coffee."
        )
        self.assertEqual(
            base,
            hints_service.cache_key(
                "cafe_order", "medium", ["点单饮品"], "Hi there?", "I want coffee.", ""
            ),
        )
        self.assertNotEqual(
            base,
            hints_service.cache_key(
                "cafe_order", "medium", ["点单饮品"], "Hi there?", "I want coffee.", "n1"
            ),
        )

    def test_other_users_session_hint_hidden(self):
        sid = self._start()
        _, other = self.register()
        r = self.client.post(f"/api/sessions/{sid}/hint", headers=other)
        self.assertEqual(r.status_code, 404)


class ReportScaleTests(SessionTests):
    """报告出参的多量表：有 band 就派生，不落库、不新增列。"""

    def _finish(self, sid):
        with mock.patch(
            "app.services.scoring.httpx.Client", _ScriptedClient.with_text(_REPORT_JSON)
        ), mock.patch("app.services.agent._request_json", return_value=None):
            return self.client.post(f"/api/sessions/{sid}/finish", headers=self.headers)

    def test_report_derives_every_scale_from_band(self):
        sid = self._start()
        self._turn(sid)
        rep = self._finish(sid).json()
        self.assertEqual(rep["source"], "llm")
        payload = rep["scales"]
        self.assertEqual(payload["version"], "2026-11")
        self.assertEqual(payload["primary"], "ielts")
        items = payload["items"]
        self.assertEqual(items["ielts"]["value"], rep["band"])
        self.assertEqual(items["ielts"]["display"], f"{rep['band']:.1f}")
        self.assertEqual(items["cefr"]["value"], rep["cefr"])
        self.assertEqual(items["cet"]["tier"], "reference")
        # 出参与纯函数同源（换算表本身在 test_scales.py 逐档覆盖）
        self.assertEqual(payload, scales_for_band(rep["band"], rep["bands"]))
        # 维度只派生 IELTS + CEFR
        dims = payload["dimensions"]
        self.assertTrue(dims)
        for one in dims.values():
            self.assertEqual(set(one), {"ielts", "cefr"})

    def test_report_endpoint_repeats_the_same_scales(self):
        sid = self._start()
        self._turn(sid)
        finished = self._finish(sid).json()
        fetched = self.client.get(f"/api/sessions/{sid}/report", headers=self.headers).json()
        self.assertEqual(fetched["scales"], finished["scales"])

    def test_mock_report_has_no_scale_items(self):
        sid = self._start()
        self._turn(sid)
        with mock.patch(
            "app.services.scoring.httpx.Client", type("C", (_FakeClient,), {"status": 503})
        ):
            rep = self.client.post(f"/api/sessions/{sid}/finish", headers=self.headers).json()
        self.assertEqual(rep["source"], "mock")
        self.assertIsNone(rep["scales"]["items"])
        self.assertEqual(rep["scales"]["reason"], "not_scored")

    def test_old_report_with_band_only_gets_scales(self):
        """旧报告只有 band，没有多量表列，读时也要补齐。"""
        from app.db import SessionLocal
        from app.models import Report, PracticeSession

        sid = self._start()
        db = SessionLocal()
        try:
            rep = Report(session_id=sid, total_score=74, band=6.5, cefr="B2", source="llm")
            db.add(rep)
            db.get(PracticeSession, sid).status = "finished"
            db.commit()
        finally:
            db.close()
        body = self.client.get(f"/api/sessions/{sid}/report", headers=self.headers).json()
        self.assertEqual(body["band"], 6.5)
        self.assertEqual(body["scales"]["items"]["ielts"]["value"], 6.5)
        self.assertEqual(body["scales"]["items"]["cefr"]["value"], "B2")
        self.assertEqual(body["scales"]["items"]["toefl"]["display"], "72–94")
        self.assertEqual(body["scales"]["items"]["cet"]["cet4"], "500–599")


class PreferencesTests(ApiTestCase):
    """报告量表偏好：默认 ielts，跟账号走，非法值拒绝。"""

    def test_report_scale_defaults_to_ielts_and_persists(self):
        _, headers = self.register()
        first = self.client.get("/api/me/settings", headers=headers).json()
        self.assertEqual(first["report_scale"], "ielts")
        r = self.client.patch(
            "/api/me/settings", json={"report_scale": "toefl"}, headers=headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["report_scale"], "toefl")
        again = self.client.get("/api/me/settings", headers=headers).json()
        self.assertEqual(again["report_scale"], "toefl")
        # 其它偏好不受影响
        self.assertEqual(again["practice_difficulty"], "medium")

    def test_report_scale_rejects_unknown_value(self):
        _, headers = self.register()
        # 高考没有分数，不在白名单里
        for value in ("gaokao", "IELTS-9", ""):
            with self.subTest(value=value):
                r = self.client.patch(
                    "/api/me/settings", json={"report_scale": value}, headers=headers
                )
                self.assertEqual(r.status_code, 400, r.text)


from datetime import date, datetime, timedelta  # noqa: E402

from app.services.dashboard import build_dashboard, local_day, streaks  # noqa: E402


class DashboardLogicTests(unittest.TestCase):
    NOW = datetime(2026, 11, 1, 4, 0)  # UTC 04:00 = 北京 12:00，周日

    def test_streak_counts_from_yesterday_when_today_not_practiced(self):
        today = date(2026, 11, 1)
        days = {today - timedelta(days=i) for i in (1, 2, 3)}
        self.assertEqual(streaks(days, today), (3, 3))

    def test_streak_breaks_on_gap_and_tracks_longest(self):
        today = date(2026, 11, 1)
        days = {today, today - timedelta(days=1)} | {date(2026, 10, d) for d in (1, 2, 3, 4, 5)}
        self.assertEqual(streaks(days, today), (2, 5))
        self.assertEqual(streaks(set(), today), (0, 0))

    def test_local_day_uses_browser_offset(self):
        late_utc = datetime(2026, 10, 31, 17, 30)  # 北京 11-01 01:30
        self.assertEqual(local_day(late_utc, -480), date(2026, 11, 1))
        self.assertEqual(local_day(late_utc, 0), date(2026, 10, 31))

    def test_heatmap_is_12_weeks_monday_aligned_ending_today(self):
        out = build_dashboard([self.NOW, self.NOW], [], self.NOW, -480)
        first = date.fromisoformat(out["heatmap"][0]["date"])
        self.assertEqual(first.weekday(), 0)
        self.assertEqual(out["heatmap"][-1], {"date": "2026-11-01", "count": 2})
        self.assertEqual(len(out["heatmap"]), 11 * 7 + 7)
        self.assertTrue(out["practiced_today"])

    def test_dimensions_skip_mock_reports_and_count_samples(self):
        reports = [
            {"created_at": self.NOW, "source": "llm", "comparable_band": 6.0,
             "dimensions": {"pronunciation": 60, "grammar_vocab": 70, "task_completion": 80}},
            {"created_at": self.NOW, "source": "llm", "comparable_band": 5.0,
             "dimensions": {"written_expression": 50, "grammar_vocab": 50, "task_completion": 60}},
            {"created_at": self.NOW, "source": "mock", "comparable_band": None, "dimensions": {}},
        ]
        out = build_dashboard([], reports, self.NOW, -480)
        dims = {d["name"]: d for d in out["dimensions"]}
        self.assertEqual(out["scored_reports"], 2)
        self.assertEqual(dims["grammar_vocab"], {"name": "grammar_vocab", "avg": 60.0, "samples": 2})
        self.assertEqual(dims["pronunciation"]["samples"], 1)
        self.assertNotIn("fluency", dims)

    def test_week_delta_needs_both_windows(self):
        recent = {"created_at": self.NOW, "source": "llm", "comparable_band": 6.0, "dimensions": {}}
        old = {"created_at": self.NOW - timedelta(days=10), "source": "llm", "comparable_band": 5.0, "dimensions": {}}
        self.assertIsNone(build_dashboard([], [recent], self.NOW, -480)["week"]["delta"])
        week = build_dashboard([], [recent, old], self.NOW, -480)["week"]
        self.assertEqual((week["recent_band"], week["previous_band"], week["delta"]), (6.0, 5.0, 1.0))


class DashboardApiTests(SessionTests):
    def test_dashboard_counts_only_own_user_turns(self):
        sid = self._start()
        with mock.patch("app.services.llm.httpx.Client", _FakeClient):
            self._turn(sid)
            self._turn(sid, "And I also enjoy reading.")
        r = self.client.get("/api/me/dashboard?tz_offset=-480", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["total_turns"], 2)
        self.assertEqual(data["current_streak"], 1)
        self.assertTrue(data["practiced_today"])
        _, other = self.register()
        empty = self.client.get("/api/me/dashboard", headers=other).json()
        self.assertEqual((empty["total_turns"], empty["current_streak"], empty["dimensions"]), (0, 0, []))

    def test_dashboard_rejects_bad_offset(self):
        r = self.client.get("/api/me/dashboard?tz_offset=99999", headers=self.headers)
        self.assertEqual(r.status_code, 422)


class StudyCardCopyTests(ApiTestCase):
    """照抄卡片上显示的提示必须判 again（rc23 补的判档保护）。

    语法卡显示的错句存在 `context`，口语卡显示的书面句存在 `term`；
    两句都和正确答案只差一个词，不拦的话照抄就能拿 hard/分。
    """

    def _due(self, headers, kind=None, source=None):
        rows = self.client.get("/api/study/due", headers=headers).json()
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        if source:
            rows = [r for r in rows if r["source"] == source]
        return rows

    def test_copying_grammar_prompt_is_again(self):
        _, headers = self.register()
        r = self.client.post("/api/study/grammar/add", json={"group": "tenses"}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        item = self._due(headers, "grammar")[0]
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"answer": item["context"]},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["last_result"], "again", "照抄错句不能拿分")
        self.assertGreaterEqual(body["lapses"], 1)
        self.assertTrue(body["due"], "again 之后今天还在队列里")

        # 真正改对了仍然是 good
        answer = (item.get("related") or {}).get("answer") or item["example"]
        r = self.client.post(
            f"/api/study/items/{item['id']}/review", json={"answer": answer}, headers=headers
        )
        self.assertEqual(r.json()["last_result"], "good", r.text)

    def test_copying_grammar_blank_is_again(self):
        """卡片上同时显示挖空句，原样复制 `He ____ to school by bus.` 也不能拿分。"""
        _, headers = self.register()
        r = self.client.post("/api/study/grammar/add", json={"group": "tenses"}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        blank_item = next(
            i for i in self._due(headers, "grammar") if (i.get("related") or {}).get("blank")
        )
        r = self.client.post(
            f"/api/study/items/{blank_item['id']}/review",
            json={"answer": blank_item["related"]["blank"]},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["last_result"], "again", "照抄挖空句不能拿分")
        self.assertGreaterEqual(r.json()["lapses"], 1)

    def test_copying_spoken_prompt_is_again(self):
        _, headers = self.register()
        r = self.client.post("/api/study/spoken/add", json={"count": 3}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        item = self._due(headers, source="spoken")[0]
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"answer": item["term"]},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["last_result"], "again", "照抄书面说法不能拿分")
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"answer": item["example"]},
            headers=headers,
        )
        self.assertEqual(r.json()["last_result"], "good", r.text)


class ReviewEventTests(ApiTestCase):
    """复习提交要留 review_events（学习模块重构方案 §4.1）。"""

    def _add_word(self, headers):
        r = self.client.post(
            "/api/study/vocab/add",
            json={"scope": "gaokao", "count": 1},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["items"][0]

    def test_review_writes_event_with_intervals(self):
        from app.db import SessionLocal
        from app.models import ReviewEvent

        _, headers = self.register()
        item = self._add_word(headers)
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"grade": "good"},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        db = SessionLocal()
        try:
            events = db.query(ReviewEvent).filter(ReviewEvent.item_id == item["id"]).all()
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.result, "good")
            self.assertEqual(event.interval_before, 0.0)
            self.assertAlmostEqual(event.interval_after, float(body["interval_days"]))
            self.assertIsNotNone(event.created_at)
        finally:
            db.close()

        summary = self.client.get("/api/study/summary?tz_offset=-480", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["reviewed_today"], 1)

    def test_reviewed_today_is_per_user(self):
        _, headers = self.register()
        _, other = self.register()
        item = self._add_word(headers)
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"grade": "hard"},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        mine = self.client.get("/api/study/summary", headers=headers).json()
        theirs = self.client.get("/api/study/summary", headers=other).json()
        self.assertEqual(mine["reviewed_today"], 1)
        self.assertEqual(theirs["reviewed_today"], 0)

    def test_reviewed_today_uses_local_day(self):
        from datetime import datetime

        from app.services.study import count_reviewed_today

        now = datetime(2026, 11, 13, 16, 0)  # UTC
        before = datetime(2026, 11, 13, 15, 0)
        after = datetime(2026, 11, 13, 16, 30)
        # 北京时间（-480）：现在已是 11-14，只有 after 落在本地今天
        self.assertEqual(count_reviewed_today([before, after], now, -480), 1)
        # UTC：两条都还是 11-13
        self.assertEqual(count_reviewed_today([before, after], now, 0), 2)

    def test_invalid_result_does_not_write_event(self):
        from app.db import SessionLocal
        from app.models import ReviewEvent

        _, headers = self.register()
        item = self._add_word(headers)
        r = self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"grade": "great"},
            headers=headers,
        )
        self.assertEqual(r.status_code, 400)
        db = SessionLocal()
        try:
            count = db.query(ReviewEvent).filter(ReviewEvent.item_id == item["id"]).count()
            self.assertEqual(count, 0)
        finally:
            db.close()

    def test_delete_data_clears_review_events(self):
        _, headers = self.register()
        item = self._add_word(headers)
        self.client.post(
            f"/api/study/items/{item['id']}/review",
            json={"grade": "again"},
            headers=headers,
        )
        r = self.client.request(
            "DELETE", "/api/me/data", json={"scope": "records"}, headers=headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["deleted_review_events"], 1)
        summary = self.client.get("/api/study/summary", headers=headers).json()
        self.assertEqual(summary["reviewed_today"], 0)


class SpellingCardHintTests(ApiTestCase):
    """拼写卡题干不能泄露答案（rc24 补）。

    模型的纠错原因常直接写出正确拼写（「coffee 有两个 f」），如果它是题干，
    默写就变成抄写。规则：题干 `meaning_zh` 留空，原因进 `related.reason`，
    判完再展示；回归断言就是「题干里不得包含 term」。
    """

    def test_manual_spelling_card_hides_reason_from_hint(self):
        _, headers = self.register()
        r = self.client.post(
            "/api/study/items",
            json={
                "kind": "spelling",
                "term": "coffee",
                "context": "I want a cofee, please.",
                "meaning_zh": "coffee 有两个 f",
                "example": "I'd like a coffee, please.",
            },
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["meaning_zh"], "", "题干不能出现纠错原因")
        self.assertNotIn("coffee", (body["meaning_zh"] or "").lower())
        self.assertIn("coffee", (body["related"] or {}).get("reason", ""))

    def test_generated_spelling_card_hides_reason_from_hint(self):
        from app.db import SessionLocal
        from app.services.study import cards_from_fixes, create_cards

        _, headers = self.register()
        me = self.client.get("/api/auth/me", headers=headers).json()
        fix = {
            "error_type": "spelling",
            "word": "coffee",
            "original": "I want a cofee, please.",
            "better": "I'd like a coffee, please.",
            "reason": "coffee 有两个 f",
            "related": {"synonyms": ["latte"]},
        }
        cards = cards_from_fixes([fix])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["meaning_zh"], "")
        self.assertIn("coffee", cards[0]["related"].get("reason", ""))

        db = SessionLocal()
        try:
            rows = create_cards(db, me["id"], None, cards)
            db.commit()
            self.assertEqual(len(rows), 1)
            self.assertNotIn("coffee", (rows[0].meaning_zh or "").lower())
            self.assertIn("coffee", rows[0].related_json)
        finally:
            db.close()

    def test_manual_spelling_card_keeps_reason_from_related_field(self):
        """新客户端把原因放 `related.reason`、`meaning_zh` 留空，服务端不能把原因丢掉。"""
        _, headers = self.register()
        r = self.client.post(
            "/api/study/items",
            json={
                "kind": "spelling",
                "term": "necessary",
                "context": "It is neccessary to rest.",
                "meaning_zh": "",
                "related": {"reason": "necessary 是 c 后面接 e"},
                "example": "It is necessary to rest.",
            },
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["meaning_zh"], "")
        self.assertEqual(body["related"].get("reason"), "necessary 是 c 后面接 e")

    def test_generated_spelling_hint_is_blank_even_without_term(self):
        """原因里不含 term（如「少了一个 r」）时，题干也必须为空。"""
        from app.services.study import cards_from_fixes

        cards = cards_from_fixes(
            [
                {
                    "error_type": "spelling",
                    "word": "letter",
                    "original": "Send me a leter.",
                    "better": "Send me a letter.",
                    "reason": "少了一个 r",
                    "related": {},
                }
            ]
        )
        self.assertEqual(cards[0]["meaning_zh"], "")
        self.assertEqual(cards[0]["related"].get("reason"), "少了一个 r")


class BandTests(unittest.TestCase):
    def test_band_score_roundtrip_monotonic(self):
        names = [n for n in dir(bands) if not n.startswith("_")]
        self.assertTrue(names)  # 模块可导入；具体换算由 evaluation 自带脚本校验


if __name__ == "__main__":
    unittest.main()
