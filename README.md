# MinePython

带用户系统与 RBAC 细粒度权限的本地文件管理、审计与 **APK 一键安装（WebUSB/ADB）** 平台 **MinePython**。

后端基于 **FastAPI（ASGI）+ SQLAlchemy 2.0 + SQLite（WAL）**，落地 **Service 分层**、**Alembic 迁移**与一套 **安全基线**（argon2id 哈希、明文密码 Fernet 对称加密、登录限流、结构化日志、安全响应头）。代码按四个相互独立、可单进程启动的模块组织于 `modules/` 包：`user` / `files` / `audit` / `apidocs`。

支持：注册/登录、多角色权限、审批流、文件分类管理、批量操作、审计日志、文件预览、**通过浏览器把 APK 一键安装到 Android 设备**，以及中 / 英 / 俄三语 Web 界面与 Swagger 文档。

---

## 目录

1. [功能特性](#1-功能特性)
2. [技术栈与架构](#2-技术栈与架构)
3. [目录结构](#3-目录结构)
4. [环境要求](#4-环境要求)
5. [安装与运行](#5-安装与运行)
6. [配置（环境变量全表）](#6-配置环境变量全表)
7. [数据库 Schema 与迁移](#7-数据库-schema-与迁移)
8. [角色与权限（RBAC）](#8-角色与权限rbac)
9. [API 完整参考](#9-api-完整参考)
10. [ADB / WebUSB 一键安装](#10-adb--webusb-一键安装)
11. [前端页面](#11-前端页面)
12. [安全基线](#12-安全基线)
13. [生产部署](#13-生产部署)
14. [手机访问](#14-手机访问)
15. [测试](#15-测试)
16. [状态、已知限制与路线图](#16-状态已知限制与路线图)
17. [故障排查（Git 工作流）](#17-故障排查git-工作流)
18. [辅助脚本](#18-辅助脚本)

---

## 1. 功能特性

| 模块 | 说明 |
| --- | --- |
| 用户系统 | 注册 / 登录（支持昵称）/ JWT 认证（access + refresh）/ 首次强制改密 / 登出 / 改密 / 注销 / 资料更新（`/api/auth/me` PUT） |
| 认证安全 | argon2id 密码哈希；明文密码经 Fernet 对称加密存储；登录失败账户锁 + IP 维度窗口节流（429）；默认口令首次强制改密 |
| RBAC 权限 | **5 角色**（admin / reviewer / uploader / user / anonymous）× **12 权限码**，接口级鉴权 |
| 管理员面板 | 添加 / 编辑 / 删除用户、审批注册、批量创建、孤儿文件清理、站点名与上传上限在线调整 |
| 审计日志 | 关键动作写入 `audit_log` 并捕获客户端 IP；独立页面 `audit.html` 查看（彩色标签 / 刷新 / 导出 CSV） |
| 文件管理 | 上传 / 下载 / 删除 / 列表；批量上传、批量删除、批量下载（流式）；分类过滤 + 分页 + 文件名搜索；元数据追踪（上传者 / IP / 时间）；大文件上传进度条 |
| 文件预览 | 后端 `/api/preview/{path}` 复用下载鉴权 + `Content-Disposition: inline` + Range；前端弹层预览 |
| 分类管理 | 自动归类（扩展名→分类，规则可在 `ext_category` 表增删改）+ 手动分类 + 新建 / 删除分类 + 散落文件归位（`/organize`） |
| 配额与限流 | 管理员可设**每用户存储配额**（MB）与**上传频率上限**（窗口内次数），均通过 `.env` 持久化 |
| ADB 一键安装 | 后端 `/api/adb/*` 调用宿主机 `adb`，把指定 APK 安装到已连接设备；支持 USB 与 WiFi（TCP/IP）连接；Web 端基于 WebUSB 在浏览器内完成设备授权 |
| 结构化日志 | `RotatingFileHandler` JSON 单行 + 控制台可读文本；密钥实时脱敏；请求访问日志带 `X-Request-ID` |
| Web 界面 | 登录 → 文件浏览 → 上传 流程；中 / 英 / 俄三语切换；亮/暗主题 |
| 部署 | Docker（non-root）+ docker-compose + Nginx + systemd；CI 测试门禁；可选 HTTPS（WebUSB 必需） |
| Swagger | 在线 API 文档与交互测试（`/docs`，生产环境默认 403 关闭） |

---

## 2. 技术栈与架构

- **Web 框架**：FastAPI（ASGI）
- **ORM / 数据库**：SQLAlchemy 2.0；默认 **SQLite（WAL）**，设 `DATABASE_URL` 可切到 **Postgres（psycopg3 同步驱动）**——多实例指向同一数据库即可横向扩展（见末节路线图 ARCH-10）
- **分层**：`Client → 中间件 → API(薄路由 + 权限守卫) → Service(业务) → Repository/ORM → Persistence`；认证 / RBAC 横切
  - `modules/user/services/`（`auth_service.py` / `user_service.py`）与 `modules/files/services/`（`file_service.py` / `category_service.py`）承载业务；路由仅保留 HTTP 层与 `Depends` 权限守卫，避免 Fat Router
- **会话（ARCH-9）**：无状态 **access JWT**（HS256，签名校验，热路径零 DB 查询，支持多实例横向扩展）+ 服务端 **refresh_tokens** 表（仅存刷新令牌的 SHA-256 哈希，可随时吊销以立即登出 / 改密）；`token` 字段保留为 `access_token` 的向后兼容别名。后台定时清理过期刷新令牌
- **配置**：集中于 `modules/user/config.py`（env 单一入口），支持 CORS、JWT、登录限流、上传上限/配额/限流、批量上下限、ADB、日志等旋钮
- **迁移**：Alembic 跟踪 schema（`Base.metadata` 为单一真源）
- **单进程模块化**：`user` / `files` / `audit` / `apidocs` 四个模块各自可独立启动（端口 8001–8004）；统一入口 `server.py` / `python -m modules` 把它们挂到同一应用（端口 8000）
  - 依赖方向：`files → user`，`audit → user`；`user` 不依赖任何业务模块，故可被安全复用，无循环依赖

---

## 3. 目录结构

```
MinePython/
├── server.py                  # 统一入口（uvicorn 启动，端口 8000）
├── modules/__main__.py        # `python -m modules` 入口（同 server.py）
├── alembic.ini                # Alembic 配置（sqlalchemy.url 运行时注入）
├── requirements.txt           # 依赖（含 alembic / argon2-cffi / cryptography）
├── .env / .env.example        # 运行时配置（参见第 6 节）
├── .fernet_key                # Fernet 密钥（gitignore，首次启动自动生成；Docker 需预置有效密钥）
├── migrations/                # Alembic 迁移
│   ├── env.py                 # 接 Base.metadata 与 engine
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial.py    # 基线：业务表（users/tokens/files/audit_log/roles/permissions/role_permissions）
│       ├── 0002_ext_category.py  # 分类映射表 ext_category
│       └── 0003_refresh_tokens.py  # ARCH-9：丢弃旧 tokens 表，新建 refresh_tokens（哈希存储）
├── modules/                   # 后端包（单进程模块化：四个独立模块）
│   ├── __init__.py
│   ├── common.py              # 公共层：FastAPI 工厂、中间件（CORS/日志/安全头/docs 开关）、静态/页面、启动任务
│   ├── combined.py            # 合并入口：把四模块挂到同一应用（端口 8000）
│   ├── user/                  # 基座模块：配置、数据库、RBAC、认证、用户/管理员控制台
│   │   ├── config.py          # 配置常量（env 单一入口）
│   │   ├── database.py        # ORM 模型、引擎、会话、迁移、RBAC 种子
│   │   ├── models.py          # Pydantic 请求/响应模型
│   │   ├── utils.py           # 密码哈希、Fernet 加解密、文件分类、大小格式化、删除
│   │   ├── auth.py            # 认证路由 + 守卫（get_current_user / require_*）
│   │   ├── admin.py           # 管理员：用户 CRUD / 审批 / 审计 / 站点设置 / 清理
│   │   ├── logging_config.py  # 结构化日志（JSON + 脱敏 + 轮转）
│   │   ├── services/          # 业务层（HTTP 无关）
│   │   │   ├── auth_service.py
│   │   │   └── user_service.py
│   │   └── __main__.py        # 独立启动（端口 8001）
│   ├── files/                 # 文件服务器模块（依赖 user）
│   │   ├── files.py           # 文件：列表/上传/下载/预览/删除/批量
│   │   ├── categories.py      # 分类管理 + 映射 CRUD
│   │   ├── cleanup.py         # 孤儿文件扫描 / 清理
│   │   ├── adb.py             # ADB 一键安装（设备/安装/连接/断开）
│   │   ├── services/          # 业务层
│   │   │   ├── file_service.py
│   │   │   └── category_service.py
│   │   └── __main__.py        # 独立启动（端口 8002）
│   ├── audit/                 # 审计模块（依赖 user）
│   │   ├── audit.py           # 审计日志查看（/api/audit/logs）
│   │   └── __main__.py        # 独立启动（端口 8003）
│   └── apidocs/               # API 文档模块（独立文档门户）
│       ├── __init__.py        # create_apidocs_app()：Swagger / ReDoc / /api 门户
│       └── __main__.py        # 独立启动（端口 8004）
├── static/
│   ├── common.css             # 全局样式
│   └── js/                    # 前端模块（经典脚本，全局可变状态共享）
│       ├── util.js  i18n.js  theme.js  toast.js
│       ├── auth.js  pending.js  init.js
│       ├── webadb.bundle.js  webadb2.bundle.js   # WebUSB ADB 浏览器端 bundle
│       ├── webadb-importmap.json  webadb2-importmap.json
│       └── vendor/  vendor2/  # 第三方依赖（含 @yume-chan/adb 等）
├── index.html  login.html  register.html  files.html  users.html  audit.html  settings.html  api.html  # 前端页面（热重载）
├── nginx.conf                 # Nginx 反向代理模板（需用 envsubst 渲染）
├── Dockerfile                 # 基于 python:3.13-slim，non-root 运行
├── docker-compose.yml         # 一键编排（挂载 uploads/logs/db/.fernet_key/.env/ssl）
├── entrypoint.sh              # Docker 入口（修正挂载文件属主后降权运行）
├── .github/workflows/docker.yml  # CI：pytest 门禁 + 构建推送 ghcr.io
├── gen_cert.py                # 生成自签 SSL 证书（启用 HTTPS / WebUSB）
├── server.db                  # SQLite 数据库（自动生成，gitignore）
├── uploads/                   # 文件存储目录（自动生成）
│   ├── 图片/ 文档/ 视频/ 音频/ 压缩包/ 代码/ 安装包/ 其他/
└── README.md
```

---

## 4. 环境要求

- **Python 3.10+**（已在 3.13 验证；Docker 镜像基于 `python:3.13-slim`）
- `pip`（或 Docker / Docker Compose）
- 可选：启用 **ADB 一键安装** 需在运行服务端主机安装 [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)（`adb` 在 `PATH` 或经 `ADB_PATH` 指定）
- 可选：启用 **HTTPS（WebUSB 必需）** 需生成自签证书（见 [第 13 节](#13-生产部署)）

---

## 5. 安装与运行

### 本地运行（推荐用虚拟环境）

```bash
# 创建并激活虚拟环境
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

pip install -r requirements.txt

# 统一入口（端口 8000，挂载全部四模块）
python server.py
# 或等价地：
python -m modules
```

启动后访问：

| 入口 | 地址 |
| --- | --- |
| Web 管理界面 | `http://localhost:8000` |
| Swagger API 文档 | `http://localhost:8000/docs`（仅 `APP_DEBUG=true` 时可用） |
| ReDoc 文档 | `http://localhost:8000/redoc`（仅 `APP_DEBUG=true` 时可用） |
| API 门户页 | `http://localhost:8000/api` |

> 首次启动会自动建库、种子化 RBAC 角色/权限与默认分类映射，并执行 Alembic 迁移（纳管数据库）。
> 默认管理员账号：`admin` / `admin123`（首次登录会被强制要求改密）。**生产环境务必改密**。

### 单独启动某个模块（开发 / 解耦部署）

每个模块都有 `__main__.py`，可单独监听其端口（8001–8004）：

```bash
python -m modules.user      # 用户/认证/管理，端口 8001
python -m modules.files     # 文件/分类/ADB，端口 8002
python -m modules.audit     # 审计，端口 8003
python -m modules.apidocs   # API 文档门户，端口 8004
```

> 常规使用请走统一入口（8000）。独立模式主要用于开发联调或对模块做反向代理拆分。

### Docker 一键部署

```bash
# 1) 预置 .env（至少保证文件存在；否则 Docker 会把挂载点建成目录）
cp .env.example .env
# 2) 预置 Fernet 密钥（Docker 内若 .fernet_key 为空文件会崩溃，见第 17 节）
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .fernet_key
# 3) 启动
docker compose up -d --build
```

---

## 6. 配置（环境变量全表）

所有配置经 `modules/user/config.py` 加载（单一事实源）。`.env.example` 为模板。变量优先级：真实环境变量 > `.env` 文件 > 代码默认值。下表为完整清单。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `MinePython` | 站点/工程显示名（页面标题、页头、API 文档标题）。管理员在 `/api/admin/site` 改后写入 `.env` 持久化 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 统一入口端口 |
| `USER_MODULE_PORT` | `8001` | `modules.user` 独立启动端口 |
| `FILES_MODULE_PORT` | `8002` | `modules.files` 独立启动端口 |
| `AUDIT_MODULE_PORT` | `8003` | `modules.audit` 独立启动端口 |
| `APIDOCS_MODULE_PORT` | `8004` | `modules.apidocs` 独立启动端口 |
| `ADMIN_USERNAME` | `admin` | 默认管理员用户名 |
| `ADMIN_PASSWORD` | `admin123` | 默认管理员密码（首次登录强制改密；生产务必修改） |
| `ADMIN_NICKNAME` | `管理员` | 默认管理员昵称 |
| `JWT_SECRET` | 自动生成 `.jwt_secret` 文件 | JWT 签名密钥；**多实例部署必须所有实例一致**（否则互不相认 access token）。生产环境务必显式设置（或接入密钥库），不要用自动生成文件 |
| `JWT_ISSUER` | `minepython` | JWT `iss` 声明，校验时强制匹配 |
| `JWT_ALGORITHM` | `HS256` | 签名算法（当前仅 HS256） |
| `JWT_ACCESS_TTL_MINUTES` | `30` | access JWT 有效期（分钟）；刻意很短——因无状态无法主动吊销，靠 refresh 续期 |
| `JWT_REFRESH_TTL_DAYS` | `7` | refresh token 有效期（天），即"保持登录"窗口；可随时吊销（登出 / 改密 / 停权） |
| `REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS` | `3600` | 过期 refresh token 后台清理间隔（秒）；`0` 关闭 |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | 审计日志保留天数，超过则被后台清理；`0` 永久保留 |
| `PERMISSION_CACHE_REFRESH_SECONDS` | `300` | 内存角色→权限缓存从 DB 重载间隔（秒），保证多实例下权限变更最终一致；`0` 仅启动时加载 |
| `RATE_LIMIT_STORE` | 空（内存） | 上传限流共享存储；设为 `redis://host:6379/0` 可跨实例计数（ARCH-10），留空为单进程内存限流 |
| `REFRESH_TOKEN_IN_COOKIE` | `false` | `true` 时 refresh token 以 httpOnly+SameSite Cookie 下发（而非 JSON body），缩小 XSS 暴露面；仅 HTTPS 生产环境启用，本地 http 开发保持关闭 |
| `DATABASE_URL` | 空（默认 SQLite） | 设为 `postgresql://user:pass@host:5432/db` 切换到 Postgres（自动归一化为 psycopg3 同步驱动）；留空则用本地 `server.db` |
| `DB_POOL_SIZE` | `10` | Postgres 连接池大小（仅 `DATABASE_URL` 设置时生效） |
| `DB_MAX_OVERFLOW` | `20` | Postgres 连接池溢出上限 |
| `DB_POOL_RECYCLE` | `1800` | Postgres 连接回收秒数（防空闲连接被服务端断开） |
| `MAX_LOGIN_FAILS` | `5` | 同一用户名连续失败达到此数 → 账户锁定 |
| `LOGIN_LOCK_SECONDS` | `900` | 账户锁定时长（秒，15 分钟） |
| `LOGIN_IP_MAX_FAILS` | `20` | 同一 IP 在窗口内失败达到此数 → 返回 429 |
| `LOGIN_IP_WINDOW_SECONDS` | `300` | IP 节流窗口（秒，5 分钟） |
| `CORS_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | 允许调用 API 的源（逗号分隔；绝不与 `*` + credentials 混用） |
| `MAX_UPLOAD_SIZE_MB` | `500` | 单文件上传上限（MB）；管理员可在 `/api/admin/upload-limit` 调整并持久化 |
| `ALLOWED_EXTENSIONS` | 空（允许全部） | 仅允许的后缀白名单（逗号分隔，含点，如 `.pdf,.apk`） |
| `BLOCKED_EXTENSIONS` | `.php,.phtml,.php3,.php4,.php5,.asp,.aspx,.jsp,.jspx,.cgi,.pl` | 拒绝的后缀黑名单（服务端脚本类，防上传 RCE） |
| `UPLOAD_RATE_LIMIT` | `0`（关闭） | 单用户在 `UPLOAD_RATE_WINDOW_SECONDS` 内最多发起的上传次数；`0` 关闭 |
| `UPLOAD_RATE_WINDOW_SECONDS` | `60` | 上传频率窗口（秒） |
| `MAX_USER_UPLOAD_BYTES` | `0`（关闭） | 单用户累计存储配额（MB）；`0` 关闭 |
| `MAX_BATCH_UPLOAD_FILES` | `100` | 单批上传文件数上限 |
| `MAX_BATCH_DOWNLOAD_FILES` | `500` | 单批下载文件数上限 |
| `MAX_BATCH_DOWNLOAD_BYTES` | `2147483648`（2 GB） | 单批下载总大小上限（未压缩） |
| `ADB_PATH` | `adb` | `adb` 可执行文件路径（不在 PATH 时显式指定，如 `C:/android-sdk/platform-tools/adb.exe`） |
| `ADB_TIMEOUT` | `300` | 单次 `adb install` 超时上限（秒） |
| `ORPHAN_CLEANUP_INTERVAL_SECONDS` | `0` | 孤儿文件后台扫描间隔（秒）；`0` 关闭（仍可用 `/api/admin/cleanup` 手动触发） |
| `ORPHAN_CLEANUP_AUTO` | `false` | 为 `true` 时后台扫描直接删除孤儿（默认仅报告；删除会写审计日志，慎用） |
| `LOG_DIR` | `logs` | 日志目录 |
| `LOG_FILE_NAME` | `app.log` | 日志文件名（JSON 单行轮转） |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL） |
| `LOG_MAX_BYTES` | `10485760`（~10 MB） | 单日志文件大小上限，超出轮转 |
| `LOG_BACKUPS` | `5` | 保留的轮转备份数 |
| `APP_DEBUG` | `false` | 调试模式。`true` 时开放 `/docs` `/redoc` `/openapi.json` 并返回详细错误串；生产务必保持 `false` |
| `SSL_CERTFILE` / `SSL_KEYFILE` | 空 | 同时设置且文件存在 → 启用 HTTPS（WebUSB 必需）；缺失则安全降级为 HTTP |
| `TZ` | `Asia/Shanghai` | 容器时区（docker-compose 注入） |

> 分类映射（`ext_category`）由代码常量 `EXT_CATEGORY`（70+ 扩展名 → 8 大类）首次种子化，之后以数据库为唯一真源，可通过分类映射 CRUD 接口运行时增删改。

---

## 7. 数据库 Schema 与迁移

SQLite（经 SQLAlchemy ORM 访问），自动建表 `server.db`：

```
users            (id, username, password, password_plain, nickname, token[遗留列,当前未使用], role, status, is_default, force_pw_change, created_at, last_login_ip)
refresh_tokens   (id, user_id, token_hash, expires_at, device, created_at)  -- 仅存刷新令牌哈希；access 为无状态 JWT
files            (id, filename, category, filepath, size, uploaded_by, uploaded_ip, uploaded_at)
audit_log        (id, username, action, target, ip, created_at)
ext_category     (id, extension, category, created_at)                       -- 扩展名→分类映射
roles            (id, name, description)                                      -- RBAC
permissions      (id, code, description)                                      -- RBAC
role_permissions (role_id, permission_id)                                     -- RBAC 关联
```

### 数据库迁移（Alembic）

Schema 由 [Alembic](https://alembic.sqlalchemy.org/) 跟踪，不再依赖 `create_all` 硬建表：

- `alembic.ini` + `migrations/env.py` 复用 `modules.user.database` 的 `Base.metadata` 与 `engine`（单一真源），`sqlalchemy.url` 在 `alembic.ini` 中留空、运行时注入。
- `0001_initial.py` 为基线 migration（7 张业务表 + `alembic_version`）；`0002_ext_category.py` 新增分类映射表。
- 应用启动（`init_db()`）自动纳管：新库 / 旧库 → `create_all` 保证表存在 + `alembic stamp head`；已纳管库 → `alembic upgrade head`（幂等）。Alembic 未安装时回退 `create_all`，应用仍可启动。
- 兼容旧库：对 v4.1 之前缺失的列（`nickname` / `role` / `status` / `is_default` / `force_pw_change` / `password_plain` / `last_login_ip`）做 `ALTER TABLE` 补齐；并把遗留明文 `password_plain` 重新加密。

常用命令：

```bash
pip install -r requirements.txt        # 已含 alembic
alembic upgrade head                   # 应用所有待执行迁移（生产部署门禁）
alembic revision -m "add column x"     # 改动 ORM 后生成新迁移
alembic upgrade head --sql             # 仅打印将执行的 SQL（离线审查）
```

---

## 8. 角色与权限（RBAC）

启动时自动种子化以下 **5 个角色**与权限映射（可在 `modules/user/database.py` 的 `ROLES` / `PERMISSIONS` 中调整；每次启动会用种子覆盖映射，保证权威）：

| 角色 | 权限 |
| --- | --- |
| `admin` | **全部 12 项权限** |
| `reviewer` | `file:list` `file:upload` `file:download` `file:delete_self` `file:adb_install` `user:read` `user:approve` `audit:view` `audit:view_self` |
| `uploader` | `file:list` `file:upload` `file:download` `file:delete_self` `file:adb_install` `audit:view_self` |
| `user` | 同 `uploader`（可上传/下载/删除本人文件 + ADB 安装 + 查看本人审计） |
| `anonymous` | `file:list` `file:download`（只读，无需登录；用于公开只读场景） |

**12 个权限码**：

| 权限码 | 含义 |
| --- | --- |
| `file:list` | 浏览文件列表 |
| `file:upload` | 上传文件 |
| `file:download` | 下载文件 |
| `file:delete_self` | 删除本人上传的文件 |
| `file:delete_any` | 删除任意文件 |
| `file:adb_install` | 通过 ADB 把 APK 安装到设备 |
| `category:manage` | 管理分类（删分类 / 整理 / 改映射） |
| `user:read` | 查看用户列表 |
| `user:manage` | 创建 / 修改 / 删除用户 |
| `user:approve` | 审批用户注册 |
| `audit:view` | 查看全部审计日志（管理员 / 审核员） |
| `audit:view_self` | 查看本人审计记录（所有登录用户持有） |
| `audit:purge` | 清空全部审计日志（仅管理员；清空后保留一条 `audit_clear` 留存记录） |

登录响应与 `/api/auth/me` 均返回当前用户的有效权限列表，便于前端按权限隐藏 UI。

> 默认注册的新用户角色为 `user`、状态为 `pending`，需管理员在 `/api/admin/pending` 审批通过后方可登录。

---

## 9. API 完整参考

> **认证**：请求头 `Authorization: Bearer <access JWT>`。标注「登录」的接口需携带任一有效 access JWT；标注「权限」的列表示所需权限码，未持有时返回 403。前端 `static/js/auth.js` 含全局 `fetch` 拦截器：自动注入 `Authorization`、遇 `401` 静默用 refresh token 续期并重试一次，无需改造各页面。
> **基础路径**：所有接口以 `/api` 为前缀（如 `/api/auth/login`）。

### 认证（Auth）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 否 | 注册（支持昵称，默认 `user` 角色、待审批） |
| POST | `/api/auth/login` | 否 | 登录（限流 / 锁定 / 状态校验）；返回 `access_token` + `refresh_token` + 权限列表，`token` 为 `access_token` 的向后兼容别名 |
| POST | `/api/auth/refresh` | 否 | 用有效 `refresh_token` 换发新的 `access_token` + `refresh_token`（轮换）；refresh token 失效 / 过期 / 被吊销则返回 401 |
| POST | `/api/auth/logout` | 登录 | 登出（吊销当前 refresh token；已签发的短效 access JWT 在 TTL 内仍可用——无状态设计权衡，详见第 2 / 16 节） |
| GET | `/api/auth/me` | 登录 | 当前用户资料与权限 |
| PUT | `/api/auth/me` | 登录 | 更新个人资料（昵称等） |
| PUT | `/api/auth/me/password` | 登录 | 修改密码（成功后吊销该用户全部 refresh token，强制所有设备重新登录） |
| POST | `/api/auth/me/deactivate` | 登录 | 注销账号（不可注销默认管理员 / 自己）；注销会吊销其全部 refresh token |

### 文件（Files）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/files` | `file:list` | 文件列表 `?category=&search=&page=&page_size=` |
| POST | `/api/upload` | `file:upload` | 单文件上传（`category=auto` 自动分类或指定）；前端以每文件并发调用本接口 |
| GET | `/api/download/{path}` | `file:download` | 下载 |
| GET | `/api/preview/{path}` | `file:download` | 预览（inline + Range） |
| DELETE | `/api/files/{path}` | `file:delete_self`（本人）或 `file:delete_any` | 删除 |
| POST | `/api/files/batch-delete` | `file:delete_self` / `file:delete_any` | 批量删除 |
| POST | `/api/files/batch-download` | `file:download` | 批量下载（临时文件 + 分块流式 + 文件数/总大小双上限） |

### 分类（Categories）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/categories` | `file:list` | 分类列表（含每类文件数 / 总大小） |
| GET | `/api/categories/mapping` | `category:manage` | 扩展名 → 分类映射规则列表 |
| PUT | `/api/categories/mapping` | `category:manage` | 新增 / 更新映射规则 `{extension, category}` |
| DELETE | `/api/categories/mapping/{extension}` | `category:manage` | 删除映射规则 |
| DELETE | `/api/categories/{name}` | `category:manage` | 删除分类（连带文件与目录） |
| POST | `/api/organize` | `category:manage` | 把根目录散落文件按扩展名归位到分类子目录 |

### 管理（Admin）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/admin/users` | `user:read` | 用户列表（已剥离密码哈希） |
| POST | `/api/admin/users` | `user:manage` | 创建用户（可指定角色） |
| PUT | `/api/admin/users/{id}` | `user:manage` | 修改用户 |
| DELETE | `/api/admin/users/{id}` | `user:manage` | 删除用户（不可删自己 / 默认账号） |
| POST | `/api/admin/users/batch` | `user:manage` | 批量创建 |
| GET | `/api/admin/pending` | `user:read` | 待审批用户列表 |
| PUT | `/api/admin/users/{id}/approve` | `user:approve` | 审批通过 |
| PUT | `/api/admin/users/{id}/reject` | `user:approve` | 审批拒绝 |
| GET | `/api/admin/audit` | `audit:view` | 审计日志（全部） |
| GET | `/api/admin/site` | `admin` | 读取当前站点名 |
| PUT | `/api/admin/site` | `admin` | 修改站点名（写 `.env` 持久化 + 审计） |
| GET | `/api/admin/upload-limit` | `admin` | 读取当前单文件上传上限（MB） |
| PUT | `/api/admin/upload-limit` | `admin` | 调整单文件上传上限（MB，写 `.env` 持久化 + 审计） |
| GET | `/api/admin/setting/{key}` | `admin` | 通用 KV 设置（白名单：`site_name` / `max_upload_size_mb` / `max_user_upload_mb` / `upload_rate_limit`） |
| PUT | `/api/admin/setting/{key}` | `admin` | 更新上述 KV 设置（持久化 + 审计） |
| POST | `/api/admin/cleanup` | `admin` | 孤儿文件清理（`dry_run` 预览 / 真实清理，写审计） |

### 审计（Audit）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/audit/logs` | `audit:view_self` | 审计日志（独立入口 `audit.html`，**所有登录用户可见**；普通用户仅见本人，管理员 / 审核员见全部） |

### ADB（APK 一键安装）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/adb/devices` | `file:adb_install` | 列出通过 adb 连接的设备（序列号 / 型号 / 授权状态） |
| POST | `/api/adb/install` | `file:adb_install` | 把指定 APK 安装到设备（`adb install -r`，自动替换旧版） |
| POST | `/api/adb/connect` | `file:adb_install` | 通过 WiFi（TCP/IP）让服务端 adb 连上手机（`host:port`） |
| POST | `/api/adb/disconnect` | `file:adb_install` | 断开某 WiFi 设备的 adb 连接 |

> 详见 [第 10 节](#10-adb--webusb-一键安装)。

### 页面与公共接口（静态）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` , `/index.html` | 主界面（热重载） |
| GET | `/login.html` , `/register.html` , `/files.html` , `/users.html` , `/audit.html` , `/settings.html` , `/api` | 各功能页 / API 门户（热重载） |
| GET | `/api/app-info` | 公开品牌信息（名称 / 版本 / WebUSB bundle 是否存在），前端据此渲染标题与页头 |

---

## 10. ADB / WebUSB 一键安装

在 Web 界面「文件浏览」页中，对 `.apk` 文件可选择「一键安装」，由后端调用**运行服务端主机**上的 `adb` 把 APK 装到已连接设备。Web 端使用 **WebUSB** 在浏览器内完成设备授权握手，因此**必须满足前置条件**：

### 前置条件

1. **服务端主机**已安装 Android SDK Platform-Tools（含 `adb`），且 `adb` 在 `PATH`，或在 `.env` 设 `ADB_PATH` 指向可执行文件。
2. **手机**已开启「USB 调试」（开发者选项）；若用 WiFi 安装，还需开启「无线调试 / 网络 ADB」并给出 `IP:端口`。
3. **浏览器**需用 Chrome / Edge（支持 WebUSB），且页面必须运行在**安全上下文**——即 **HTTPS**（局域网可用 `gen_cert.py` 生成自签证书，见第 13 节）。手机本身**不要**打开该网页，应在**连接手机的电脑**的浏览器中打开。

### 工作流程

1. 前端 `GET /api/adb/devices` 列出已连接设备（含型号、授权状态）。
2. 用户点「安装」→ 前端 `POST /api/adb/install`（`{path, serial?}`）：
   - 仅接受 `.apk`，路径必须落在 `UPLOAD_DIR` 内（防 `..` 越权）。
   - 未指定 `serial` 时：仅 1 台已授权设备则自动选用；多台返回 `needs_serial` 让前端弹选；无设备返回 `needs_device`。
3. 后端执行 `adb -s <serial> install -r <apk>`，受 `ADB_TIMEOUT` 兜底；结果（成功/失败、输出、耗时）写审计日志。
4. WiFi 场景：先 `POST /api/adb/connect {host, port}` 让服务端 adb 连上手机，再安装；`POST /api/adb/disconnect` 断开。

### 接口健壮性

- `adb` 未安装 / 不在 PATH → 明确提示「未检测到 adb」。
- 设备离线 / 未授权 / 多设备 → 返回清晰中文提示，而非 500。
- `host` / `port` 经白名单校验，避免注入。

---

## 11. 前端页面

| 页面 | 作用 |
| --- | --- |
| `index.html` | 主界面入口（登录后默认进入文件浏览） |
| `login.html` | 登录页 |
| `register.html` | 注册页（提交后等待管理员审批） |
| `files.html` | 文件浏览 / 上传 / 下载 / 预览 / 批量操作 / ADB 安装 |
| `users.html` | 用户管理（管理员：CRUD / 审批 / 批量创建） |
| `audit.html` | 审计日志查看（彩色标签 / 刷新 / 导出 CSV） |
| `settings.html` | 管理员设置（站点名、上传上限、配额、限流等） |
| `api.html` | API 文档门户页（聚合 Swagger / ReDoc 入口） |

所有页面支持 **中 / 英 / 俄** 三语切换与亮/暗主题；页面标题与页头从 `/api/app-info` 动态读取站点名，改 `APP_NAME` 即可整体换名、无需改代码。

---

## 12. 安全基线

- **密码**：argon2id 哈希（OWASP 推荐参数）；旧 `salt:sha256` 在登录时透明升级为 argon2（向后兼容）。
- **明文密码**：经 Fernet 对称加密存储于 `password_plain`（仅用于管理员「显示明文」，**绝不参与鉴权**），密钥在 `.fernet_key`（gitignore）。
- **登录防护**：失败达阈值账户锁 + IP 维度窗口节流，返回 `429` 与剩余锁定秒数。
- **CORS**：收紧到显式 origins（非 `*` + credentials）。
- **响应头**：HSTS / `X-Frame-Options: DENY`（预览页 `SAMEORIGIN`）/ `X-Content-Type-Options: nosniff` / `Referrer-Policy` / CSP（含 `frame-ancestors`）/ `Permissions-Policy`。
- **缓存**：全局 `Cache-Control: no-store`，避免 WebUSB 的 import map / ES module 被浏览器缓存导致安装失败。
- **错误收敛**：生产环境全局异常仅返回 `detail`，`error` 仅 `APP_DEBUG=true` 时附加；`/docs` / `/redoc` / `/openapi.json` 生产环境默认 403。
- **上传防护**：默认拦截服务端脚本类扩展名（`.php/.asp/.jsp/...`），`.apk/.exe/.sh/.html/.js/.py` 等首类内容不拦截，改以 no-inline / nosniff 中性化处理。

---

## 13. 生产部署

### Docker（推荐）

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .fernet_key
docker compose up -d --build
```

`docker-compose.yml` 以 **non-root（uid 10001）** 运行，挂载 `uploads` / `logs` / `server.db` / `.fernet_key` / `.env` / `ssl` 卷并注入生产环境变量，附 **TLS 感知 healthcheck**（优先 HTTPS，失败回退 HTTP，探测 `/` 而非 `/docs` 因为生产 `/docs` 返回 403）。

> **横向扩展（多实例）**：在 `.env` 设 `DATABASE_URL=postgresql://...` 让所有实例指向同一 Postgres；`docker compose --profile db up -d` 会拉起 `docker-compose.yml` 中 **profile 门控**的 `db` 服务（默认不启动）。**关键**：所有实例必须设**相同 `JWT_SECRET`**，否则彼此无法验签 access token。不设 `DATABASE_URL` 时仍用本地 `server.db`，仅限单实例。

> **管理员设置持久化（Docker）**：`docker-compose.yml` 挂载 `./.env:/app/.env`，管理员在设置页改的「站点名 / 最大上传限制 / 配额 / 限流」会写进容器内的 `.env`，**重启后保留**。
> ⚠️ **部署前必须先在宿主创建 `./.env` 文件（可为空）**，否则 Docker 会把挂载点建成目录，应用无法写入、持久化静默失效。

### 启用 HTTPS（WebUSB 必需）

WebUSB 需要安全上下文，页面须通过 HTTPS 提供：

```bash
# 1) 生成自签证书（按提示输入或使用局域网 IP 参数）
python gen_cert.py            # 在 ./ssl 生成 cert.pem / key.pem（含 localhost + 所有本机 IP 的 SAN）
# 或：python gen_cert.py 192.168.1.10,192.168.1.11

# 2) 在 .env 设置（Docker 把 ./ssl 挂载到 /app/ssl）
SSL_CERTFILE=/app/ssl/cert.pem
SSL_KEYFILE=/app/ssl/key.pem
# 主机直跑则填绝对路径，再启动 server.py
```

> 自签证书浏览器会报「不安全」提示，局域网/内网使用只需在 Chrome/Edge 中点「继续前往」一次即可。手机不要打开此网页。

### gunicorn（Linux）

```bash
pip install gunicorn
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Nginx 反向代理

`nginx.conf` 为模板，含 `${MAX_UPLOAD_SIZE_MB}` 占位符，需用 `envsubst` 渲染（nginx 的 `client_max_body_size` 在 worker 启动时固定，改上限后需重新渲染 + `nginx -s reload`；应用层会在下次请求立即生效）：

```bash
export MAX_UPLOAD_SIZE_MB=500
envsubst < nginx.conf > /etc/nginx/conf.d/minepython.conf
nginx -s reload
```

### systemd 服务（Linux）

```ini
# /etc/systemd/system/fileserver.service
[Unit]
Description=MinePython
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/fileserver
ExecStart=/opt/fileserver/venv/bin/gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fileserver
```

> **Windows 11 + WSL2 部署** 的专属坑（保留设备名、`.fernet_key` 必须有效、NTFS 权限、healthcheck 改动等）详见仓库附带的 `README_DOCKER_WIN11.md`。

---

## 14. 手机访问

1. 手机与 PC 连同一 WiFi；
2. 查看 PC 局域网 IP：`ipconfig`（Windows）/ `ifconfig`（Linux）；
3. 手机浏览器访问 `http://<PC的IP>:8000`；
4. 如无法访问，放行防火墙端口 8000：

```bash
# Windows（管理员）
netsh advfirewall firewall add rule name="FileServer" dir=in action=allow protocol=TCP localport=8000
# Linux
sudo ufw allow 8000
```

---

## 15. 测试

```bash
pip install -r requirements.txt pytest httpx python-dotenv
pytest                          # 全套测试
pytest tests/test_security.py   # 仅安全 / 并发边界用例
```

测试覆盖（`tests/` 下 15 个用例文件，共 130 个用例，CI 门禁全绿）：

- `test_api.py` — 基础 API、应用信息、文档门禁
- `test_security.py` — 登录锁 / IP 节流 / 多会话隔离 / refresh token 过期清理（purge）/ 登出吊销、响应 Schema、批量下载上限、异常收敛
- `test_auth_self_service.py` — 个人资料更新、改密强制重新登录、refresh 轮换与吊销、注销（ARCH-9 语义）
- `test_admin_management.py` — 用户 CRUD / 审批 / 批量 审批·拒绝·删除 / 站点与上传上限设置
- `test_ucenter_smoke.py` — UCenter 冒烟（注册 / 审批 / 登录 / 注销）
- `test_default_admin_deactivate_protected.py` — 默认管理员不可注销保护
- `test_files_batch.py` — 批量删除 / 批量下载（ZIP / 字节上限）/ 公开 app-info
- `test_upload_security.py` — 上传安全（扩展名 / 大小 / 越权）
- `test_category_mapping.py` / `test_category_management.py` — 分类映射 CRUD 与分类管理
- `test_cleanup.py` — 孤儿文件清理
- `test_large_upload.py` — 大文件上传
- `test_migrations.py` — Alembic 迁移（含 `0003` refresh_tokens）
- `test_adb.py` — ADB 一键安装（设备列举 / 安装 / 连接·断开，adb 调用已打桩）

CI（`.github/workflows/docker.yml`）在 `master` push / PR 与 `v*` tag 时运行 `pytest` 作为合并门禁，通过后再构建并推送镜像到 `ghcr.io`。

---

## 16. 状态、已知限制与路线图

**已交付（功能完整，全套测试通过）：**

- 认证 / RBAC（5 角色 12 权限）/ 审批流 / 用户管理
- 文件管理（上传 / 下载 / 预览 / 批量 / 分页 / 搜索 / 进度条）
- 分类管理（可配置扩展名映射）
- **ADB 一键安装（WebUSB，USB + WiFi）**
- 审计日志、孤儿文件清理、配额与上传限流
- 安全基线（argon2 / Fernet / 限流 / CORS / 响应头 / 错误收敛 / docs 生产 403）
- 结构化日志、Alembic 迁移、Service 分层、前端模块化、Docker 部署、可选 HTTPS

**长期可选（未实施，按需推进）：**

- ~~`ARCH-9` JWT + refresh：以 access + refresh token 替代自研 `tokens` 表，实现无状态扩展。~~ **（已实施）** 无状态 access JWT + 服务端 `refresh_tokens`（哈希）表；详见 `modules/user/services/auth_service.py`。
- ~~`ARCH-10` Postgres / 异步 IO：将 `DATABASE_URL` 切到 Postgres（`asyncpg` + `run_in_threadpool`），支持多实例横向扩展。~~ **（已实施）** 引擎由 `DATABASE_URL` 驱动：默认本地 SQLite，设为 `postgresql://…` 时自动切换 psycopg3 同步驱动（非全量 async 重写），多实例共享同一数据库即可横向扩展；阻塞型 DB 调用经 `run_in_threadpool` 卸载，避免阻塞事件循环。

**已知能力缺口（非缺陷）：** 密码找回 / 邮件、文件版本历史、全文内容检索、分享外链。

---

## 17. 故障排查（Git 工作流）

### 1. `git add` 报错：`invalid path 'nul' unable to add 'nul' to index`

**根因**：`nul` 是 Windows 保留设备名（空设备），内核禁止把它当普通文件打开，Git 在 Windows 上无法将其加入索引。根目录的 `nul` 通常是某次误重定向（如 `> nul` 写错）产生的垃圾文件，无保留价值。

**已处理**：仓库根 `.gitignore` 已忽略 `nul` 及其他保留名（`con`/`prn`/`aux`/`com1-9`/`lpt1-9`），以及 `__pycache__/`、`*.pyc`、`.venv*/`、`*.db`/`*.db-wal`、`logs/`、`uploads/`、`*.log` 等，`git add .` 不会再尝试添加 `nul`。建议顺手删掉该垃圾文件：

```bash
# Git Bash / MSYS（用 //./ 设备前缀绕开保留名限制）
rm -f //./C:/Users/Work/PycharmProjects/MinePython/nul
# 或系统 CMD
del \\.\C:\Users\Work\PycharmProjects\MinePython\nul
# 或 PowerShell
Remove-Item -LiteralPath "\\.\C:\Users\Work\PycharmProjects\MinePython\nul" -Force
```

### 2. `git add` 大量警告：`LF will be replaced by CRLF`

**原因**：`core.autocrlf=true`（Windows 默认）提示 vendored 的 `.js/.ts/.json/.md` 当前为 LF，将来 checkout 会转成 CRLF。**仅为提示，不阻塞提交。**

**已处理**：仓库根 `.gitattributes` 已对源代码统一以 LF 存储/检出（`*.bat`/`*.cmd` 保留 CRLF，图片/压缩包/证书标记为二进制），此类警告不再出现。若此前已跟踪文件换行符混乱，可 `git add --renormalize .` 一次性规范化。

### 3. `git push` 报错：`fatal: unable to access '...github.com...': Recv failure: Connection was reset`

**现象**：TCP 连接被重置（RST），多发生在受限网络（公司 / 校园网，或部分地区访问 GitHub 不稳定）或大体积 push 走 HTTP/2 时。属于网络层问题，非仓库或认证错误。

按以下顺序排查：

**① 重试 + 关闭 HTTP/2（最常见有效）**

```bash
git config --global http.version HTTP/1.1
git config --global http.postBuffer 524288000
git push
```

**② 本机有代理（Clash / Shadowsocks / V2Ray）**

```bash
git config --global http.proxy  http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
# 若是 socks5 代理：socks5://127.0.0.1:1080
git push
```

用完取消代理：`git config --global --unset http.proxy` 与 `git config --global --unset https.proxy`。

**③ 端口 22 被封 → 改用 SSH over 443（最稳兜底）**

编辑 `~/.ssh/config`（没有则新建）：

```
Host github.com
  Hostname ssh.github.com
  Port 443
```

然后切换远程协议（需先在 GitHub 添加你的 SSH 公钥）：

```bash
git remote set-url origin git@github.com:Cuinings/MinePython.git
git push
```

**④ 临时用 GitHub 加速镜像**

```bash
git remote set-url origin https://ghproxy.com/https://github.com/Cuinings/MinePython.git
git push
# 推送成功后改回官方地址
git remote set-url origin https://github.com/Cuinings/MinePython.git
```

> 注意：部分镜像仅支持拉取、推送不一定稳定，成功后务必改回官方地址。

**排查定位**：`curl -I https://github.com` 同样 reset / 超时 → 确属网络被重置，按 ②③ 处理；若 curl 正常但 git 仍失败 → 优先试 ①。

### 4. Docker 启动报 `IsADirectoryError` / `ValueError: Fernet key ...`

`.fernet_key` 必须是一个**含有效 44 字节 base64 密钥的文件**：

- 宿主**没有**该文件 → Docker 自动创建同名**目录** → 应用读目录崩溃。
- `touch .fernet_key` 建了**空文件** → 应用读到空密钥 → `Fernet(b"")` 抛 `ValueError`。

**正确做法**（部署前预置）：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .fernet_key
```

本地直跑（非 Docker）时若文件缺失，应用会自动生成并写入，无需手动操作。

---

## 18. 辅助脚本

| 脚本 | 作用 |
| --- | --- |
| `gen_cert.py` | 生成自签 SSL 证书（含本机所有 IP 的 SAN），用于启用 HTTPS / WebUSB |
| `download_webadb.py` / `download_webadb2.py` / `download_webadb.bat` | 拉取 WebUSB ADB 浏览器端 bundle（离线/内网环境用） |
| `diagnose.bat` | Windows 一键诊断（端口/进程/日志） |
| `run_https.bat` / `start_https.py` | 以 HTTPS 启动的便捷封装 |
| `_port_check.py` / `_test_m.py` / `_extract.py` | 开发期临时小工具（非运行必需） |

---

> 文档版本对应代码：**MinePython v4.6.0**。如实现与本文有出入，以 `modules/` 下源码与 `.env.example` 为准。
