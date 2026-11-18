# SpeakPal 部署上线指南

> 更新日期：2026-11-18。价格来自各云厂商官网活动页，活动随时变化，下单前以官网为准。

## 1. 部署形态

一台 Linux 服务器跑两个容器：

| 容器 | 作用 |
|---|---|
| `app` | 一个镜像同时提供前端页面和后端 API。构建时先打包前端，再由 FastAPI 托管 `frontend/dist`（`FRONTEND_DIST`），前后端同源，不需要跨域配置 |
| `caddy` | 反向代理，自动申请并续期 HTTPS 证书，流式输出（SSE）可直接透传 |

数据库是 SQLite，存在 Docker 卷 `speakpal-data` 里（容器内 `/data/speakpal.db`），重建镜像不丢数据。

## 2. 费用

| 项目 | 选项 | 价格 | 说明 |
|---|---|---|---|
| 服务器 | 腾讯云轻量应用服务器 4核4G 3M | 新用户首年 109 元 | 2026-11-18 取自 [腾讯云轻量活动页](https://cloud.tencent.com/act/pro/lighthouse)；续费按原价折扣，不是 109 元 |
| 服务器 | 阿里云 ECS | 学生认证后每 12 个月可领 300 元优惠券 | 取自 [阿里云高校计划](https://university.aliyun.com/)，可抵扣部分云产品 |
| 域名 | `.com` / `.cn` 等 | 腾讯云「服务器 + 域名组合购」页面写域名低至 1 元（首年） | 续费价格各后缀不同，以注册商为准 |
| HTTPS 证书 | Caddy 自动申请 Let's Encrypt | 免费 | — |
| ICP 备案 | 国内服务器 + 域名必须备案 | 免费 | 由云厂商代提交到管局，需要几周，**要提前办**。备案下来之前可以先用 IP + 80 端口演示 |
| 大模型 | DeepSeek `deepseek-flash` | 每次完整练习约 0.1 元（估算） | 见下 |

**每次练习的模型成本估算**（按 DeepSeek 官网高峰价：输入未命中缓存 0.3 美元/百万 token，输出 1.2 美元/百万 token）：一次 6 轮对话加出报告，大约输入 3 万 token、输出 6 千 token，约 0.009 + 0.007 ≈ 0.016 美元，约 0.12 元。夜间和周末是半价时段。这是按提示词长度粗算的数字，上线后以 DeepSeek 控制台的实际账单为准。

体验额度的默认值 `DEMO_DAILY_TOTAL=3000` 次请求/天，一次练习大约 10 个请求，即全站每天最多约 300 次练习，最坏情况约 36 元/天。评审期间可以按需调低。

不推荐的方案：
- **Vercel / Netlify**：只能托管前端静态页，Python 后端还得另找地方。
- **Render / Railway 等海外免费档**：免费实例会休眠、磁盘不持久，SQLite 数据会丢；国内访问也不稳定。

## 3. 上线步骤

以腾讯云轻量服务器（Ubuntu 22.04 或更新版本）为例。

1. **买服务器**，在控制台防火墙放行 80、443 端口。
2. **域名解析**：在 DNS 里加一条 A 记录，指向服务器公网 IP。同时提交 ICP 备案。
3. **装 Docker**：
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
   国内服务器拉镜像慢的话，在 `/etc/docker/daemon.json` 配置云厂商提供的镜像加速地址。
4. **拉代码并配置**：
   ```bash
   git clone <仓库地址> speakpal && cd speakpal
   cp deploy.env.example deploy.env
   ```
   编辑 `deploy.env`：
   - `DOMAIN`：你的域名。备案下来之前先填 `:80`，只用 IP 访问。
   - `JWT_SECRET`、`ADMIN_KEY`：**必填**，用 `openssl rand -base64 36` 各生成一个。容器里写不回 `.env`，不填的话每次重启都会换新值，所有人被登出、管理密钥失效。
   - `DEMO_LLM_API_KEY`：评审期间填一把 DeepSeek key，评委不用自带密钥就能体验。
5. **启动**：
   ```bash
   docker compose up -d --build
   docker compose logs -f app   # 看到 Uvicorn running 即可
   ```
6. **验证**：
   - 打开 `https://你的域名`，注册账号，不填密钥直接开练，能流式对话、出报告。
   - 打开 `https://你的域名/admin`，用 `ADMIN_KEY` 登录，能看到用户、练习和反馈。
   - `curl https://你的域名/api/health` 返回 `{"status":"ok"}`。

## 4. 日常运维

| 事项 | 做法 |
|---|---|
| 更新版本 | `git pull && docker compose up -d --build` |
| 备份数据 | 每天执行一次 `docker compose cp app:/data/speakpal.db ./backup/speakpal-$(date +%F).db`，可写进 crontab |
| 看日志 | `docker compose logs --tail 200 app`，模型降级、工具调用都会打印一行 |
| 控制模型费用 | 调 `deploy.env` 里的 `DEMO_DAILY_PER_USER` / `DEMO_DAILY_TOTAL`，然后 `docker compose up -d`；不想再提供体验额度就把 `DEMO_LLM_API_KEY` 清空 |
| 用户反馈 | 用户在「设置 → 意见反馈」提交，管理台「用户反馈」表格查看 |

## 5. 已知限制

- 本仓库的 `Dockerfile` 和 `docker-compose.yml` 还没有在真实服务器上跑过一次，首次部署时请按第 3 节第 6 步逐项验证。
- SQLite 只适合单机小规模使用。用户量上来后要迁移到 PostgreSQL：除了改 `DATABASE_URL`，还要加装数据库驱动，并验证启动时的补表逻辑（`main.py:_ensure_schema`，目前按 SQLite 写的）。
