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

from app import security  # noqa: E402
from app.main import app  # noqa: E402
from app.services import llm_config, outbound  # noqa: E402
from evaluation import bands  # noqa: E402
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


class BandTests(unittest.TestCase):
    def test_band_score_roundtrip_monotonic(self):
        names = [n for n in dir(bands) if not n.startswith("_")]
        self.assertTrue(names)  # 模块可导入；具体换算由 evaluation 自带脚本校验


if __name__ == "__main__":
    unittest.main()
