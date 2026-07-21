# File Server（文件服务器 v4.4）

带用户系统的本地文件服务器：提供文件上传 / 下载 / 分类管理的 RESTful API 与 Web 管理界面。后端基于 **FastAPI + SQLAlchemy 2.0 + SQLite（WAL）**，落地 **RBAC 细粒度权限**、**Service 分层**、**Alembic 迁移**与一套**安全基线**（argon2 哈希、明文加密、登录限流、结构化日志）。

支持：注册/登录、多角色权限、审批流、文件分类管理、批量操作、审计日志、文件预览，以及中 / 英 / 俄三语 Web 界面与 Swagger 文档。

---

## 功能特性

| 模块 | 说明 |
|------|------|
| 用户系统 | 注册 / 登录（支持昵称）、Token 认证、首次强制改密、登出、改密、注销 |
| 认证安全 | argon2id 密码哈希；明文密码经 Fernet 对称加密存储；登录失败账户锁 + IP 维度窗口节流（429）；默认口令首次强制改密 |
| RBAC 权限 | 4 角色（admin / reviewer / uploader / user）× 10 权限码，接口级鉴权 |
| 管理员面板 | 添加 / 编辑 / 删除用户、审批注册、批量创建、孤儿文件清理 |
| 审计日志 | 关键动作写入 `audit_log` 并捕获客户端 IP；独立页面 `audit.html` 查看（彩色标签 / 刷新 / 导出 CSV） |
| 文件管理 | 上传 / 下载 / 删除 / 列表；批量上传、批量删除、批量下载（流式）；分类过滤 + 分页 + 文件名搜索；元数据追踪（上传者 / IP / 时间）；大文件上传进度条 |
| 文件预览 | 后端 `/api/preview/{path}` 复用下载鉴权 + `Content-Disposition: inline` + Range；前端弹层预览 |
| 分类管理 | 自动归类（扩展名→分类，规则可配置）+ 手动分类 + 新建 / 删除分类 + 散落文件归位 |
| 结构化日志 | `RotatingFileHandler` JSON 单行 + 控制台可读文本；密钥实时脱敏；请求访问日志带 `X-Request-ID` |
| Web 界面 | 登录 → 文件浏览 → 上传 流程；中 / 英 / 俄三语切换 |
| 部署 | Docker（non-root）+ docker-compose + Nginx + systemd；CI 测试门禁 |
| Swagger | 在线 API 文档与交互测试（`/docs`，生产环境默认 403 关闭） |

---

## 技术栈与架构

- **Web 框架**：FastAPI（ASGI）
- **ORM / 数据库**：SQLAlchemy 2.0 + SQLite（WAL）；`DATABASE_URL` 可切换（长期项见末节）
- **分层**：`Client → 中间件 → API(薄路由 + 权限守卫) → Service(业务) → Repository/ORM → Persistence`；认证 / RBAC 横切
  - `app/services/` 承载业务（auth / file / category / user 四层），路由仅保留 HTTP 层与 `Depends` 权限守卫，避免 Fat Router
- **会话**：自研 `tokens` 表，签发带 `expires_at` 的 Token（受 `TOKEN_TTL_HOURS` 控制），后台定时清理过期会话
- **配置**：集中于 `app/config.py`（env 单一入口），支持 CORS、Token、登录限流、批量下载上限、日志等旋钮
- **迁移**：Alembic 跟踪 schema（`Base.metadata` 为单一真源）

---

## 环境要求

- Python 3.9+
- pip（或 Docker）

---

## 安装与运行

### 本地运行

```bash
# 创建并激活虚拟环境
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

pip install -r requirements.txt
python server.py
```

启动后访问：

| 入口 | 地址 |
|------|------|
| Web 管理界面 | `http://localhost:8000` |
| Swagger API 文档 | `http://localhost:8000/docs` |
| ReDoc 文档 | `http://localhost:8000/redoc` |

> 首次启动会自动建库、种子化 RBAC 角色/权限，并执行 Alembic 迁移（纳管数据库）。

### Docker 一键部署

```bash
docker compose up -d
```

---

## 目录结构

```
MinePython/
├── server.py                  # 瘦入口（uvicorn 启动）
├── alembic.ini                # Alembic 配置（sqlalchemy.url 运行时注入）
├── requirements.txt           # 依赖（含 alembic / argon2-cffi / cryptography）
├── migrations/                # Alembic 迁移
│   ├── env.py                 # 接 Base.metadata 与 engine
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial.py    # 基线：7 张业务表
│       └── 0002_ext_category.py  # 分类映射表（P1-4）
├── app/                       # 后端包
│   ├── main.py                # FastAPI 组装 + Web UI 服务 + 中间件
│   ├── config.py              # 配置常量（env 单一入口）
│   ├── database.py            # ORM 模型、引擎、会话、迁移、RBAC 种子
│   ├── models.py              # Pydantic 请求/响应模型
│   ├── utils.py               # 密码哈希、文件分类委托、大小格式化
│   ├── auth.py                # 认证路由 + 守卫（get_current_user / require_*）
│   ├── admin.py               # 管理员：用户 CRUD / 审批 / 审计 / 清理
│   ├── files.py               # 文件：列表/上传/下载/预览/删除/批量
│   ├── categories.py          # 分类管理 + 映射 CRUD
│   ├── audit.py               # 审计日志查看
│   ├── cleanup.py             # 孤儿文件扫描 / 清理
│   ├── logging_config.py      # 结构化日志（JSON + 脱敏 + 轮转）
│   └── services/              # 业务层（HTTP 无关）
│       ├── auth_service.py
│       ├── file_service.py
│       ├── category_service.py
│       └── user_service.py
├── static/
│   ├── common.css             # 全局样式
│   └── js/                    # 前端模块（经典脚本，全局可变状态共享）
│       ├── util.js  i18n.js  theme.js  toast.js
│       └── auth.js  pending.js  init.js
├── index.html  files.html  users.html  audit.html   # 前端页面（热重载）
├── server.db                  # SQLite 数据库（自动生成）
├── uploads/                   # 文件存储目录（自动生成）
│   ├── 图片/ 文档/ 视频/ 音频/ 压缩包/ 代码/ 安装包/ 其他/
└── README.md
```

---

## 数据库

SQLite（经 SQLAlchemy ORM 访问），自动建表 `server.db`：

```sql
users       (id, username, password, nickname, role, status, created_at)
files       (id, filename, category, filepath, size, uploaded_by, uploaded_ip, uploaded_at)
audit_log   (id, username, action, target, ip, created_at)
roles           (id, name, description)                 -- RBAC
permissions      (id, code, description)                -- RBAC
role_permissions (role_id, permission_id)               -- RBAC 关联表
tokens          (id, user_id, token, expires_at, device, created_at)  -- 多会话 / 过期
ext_category    (id, extension, category, created_at)   -- 扩展名→分类映射（P1-4）
```

### 数据库迁移（Alembic）

Schema 由 [Alembic](https://alembic.sqlalchemy.org/) 跟踪，不再依赖 `create_all` 硬建表：

- `alembic.ini` + `migrations/env.py` 复用 `app.database` 的 `Base.metadata` 与 `engine`（单一真源），`sqlalchemy.url` 在 `alembic.ini` 中留空、运行时注入。
- `0001_initial.py` 为基线 migration（7 张业务表 + `alembic_version`）；`0002_ext_category.py` 新增分类映射表。
- 应用启动（`init_db()`）自动纳管：新库 / 旧库 → `alembic stamp head`；已纳管库 → `alembic upgrade head`（幂等）。Alembic 未安装时回退 `create_all`，应用仍可启动。

常用命令：

```bash
pip install -r requirements.txt        # 已含 alembic
alembic upgrade head                   # 应用所有待执行迁移（生产部署门禁）
alembic revision -m "add column x"     # 改动 ORM 后生成新迁移
alembic upgrade head --sql             # 仅打印将执行的 SQL（离线审查）
```

---

## 角色与权限（RBAC）

启动时自动种子化以下角色与权限映射（可在 `app/database.py` 的 `ROLES` / `PERMISSIONS` 中调整）：

| 角色 | 权限 |
|------|------|
| `admin` | 全部权限（含查看全部审计 `audit:view`） |
| `reviewer` | 浏览 / 上传 / 下载 / 删本人文件、查看用户、审批用户、`audit:view` + `audit:view_self` |
| `uploader` | 浏览 / 上传 / 下载 / 删除本人文件 + `audit:view_self` |
| `user` | 浏览 / 上传 / 下载 / 删除本人文件 + `audit:view_self` |

权限码：`file:list` `file:upload` `file:download` `file:delete_self` `file:delete_any` `category:manage` `user:read` `user:manage` `user:approve` `audit:view`（查看全部）`audit:view_self`（查看本人，所有登录用户持有）。

登录响应与 `/api/auth/me` 均返回当前用户的有效权限列表，便于前端按权限隐藏 UI。

---

## API 概览

> 认证方式：请求头 `Authorization: Bearer <token>`。带「权限」的列表示所需权限码，未持有时返回 403。

### 认证（Auth）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | 否 | 注册（支持昵称，默认 `user` 角色、待审批） |
| POST | `/api/auth/login` | 否 | 登录（限流 / 锁定 / 状态校验，返回 token 与权限列表） |
| POST | `/api/auth/logout` | 登录 | 登出（失效当前会话） |
| GET | `/api/auth/me` | 登录 | 当前用户资料与权限 |
| PUT | `/api/auth/me/password` | 登录 | 修改密码 |
| POST | `/api/auth/me/deactivate` | 登录 | 注销账号 |

### 文件（Files）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/files` | file:list | 文件列表 `?category=&search=&page=&page_size=` |
| POST | `/api/upload` | file:upload | 单文件上传（`category=auto` 自动分类或指定） |
| POST | `/api/upload/multiple` | file:upload | 批量上传 |
| GET | `/api/download/{path}` | file:download | 下载 |
| GET | `/api/preview/{path}` | file:download | 预览（inline + Range） |
| DELETE | `/api/files/{path}` | file:delete_self(本人) 或 file:delete_any | 删除 |
| POST | `/api/files/batch-delete` | file:delete_self / file:delete_any | 批量删除 |
| POST | `/api/files/batch-download` | file:download | 批量下载（磁盘临时文件 + 分块流式 + 文件数/总大小双上限） |

### 分类（Categories）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/categories` | file:list | 分类列表（含每类文件数 / 总大小） |
| GET | `/api/categories/mapping` | category:manage | 扩展名 → 分类映射规则列表 |
| PUT | `/api/categories/mapping` | category:manage | 新增 / 更新映射规则 `{extension, category}` |
| DELETE | `/api/categories/mapping/{extension}` | category:manage | 删除映射规则 |
| DELETE | `/api/categories/{name}` | category:manage | 删除分类（连带文件与目录） |
| POST | `/api/organize` | category:manage | 把根目录散落文件按扩展名归位到分类子目录 |

### 管理（Admin）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/admin/users` | user:read | 用户列表（已剥离密码哈希） |
| POST | `/api/admin/users` | user:manage | 创建用户（可指定角色） |
| PUT | `/api/admin/users/{id}` | user:manage | 修改用户 |
| DELETE | `/api/admin/users/{id}` | user:manage | 删除用户（不可删自己 / 默认账号） |
| POST | `/api/admin/users/batch` | user:manage | 批量创建 |
| GET | `/api/admin/pending` | user:read | 待审批用户列表 |
| PUT | `/api/admin/users/{id}/approve` | user:approve | 审批通过 |
| PUT | `/api/admin/users/{id}/reject` | user:approve | 审批拒绝 |
| GET | `/api/admin/audit` | audit:view | 审计日志（全部） |
| POST | `/api/admin/cleanup` | admin | 孤儿文件清理（`dry_run` 预览 / 真实清理，写审计） |

### 审计（Audit）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/audit/logs` | audit:view_self | 审计日志（独立入口 `audit.html`，**所有登录用户可见**；普通用户仅见本人，管理员 / 审核员见全部） |

### 页面（静态）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` , `/index.html` , `/files.html` , `/users.html` , `/audit.html` | Web 管理界面（热重载） |

---

## 安全基线

- **密码**：argon2id 哈希；旧 `salt:sha256` 在登录时透明升级为 argon2（向后兼容）。
- **明文密码**：经 Fernet 对称加密存储（`.fernet_key`，已 gitignore）。
- **登录防护**：失败达阈值账户锁 + IP 维度窗口节流，返回 `429` 与剩余锁定秒数。
- **CORS**：收紧到显式 origins（非 `*` + credentials）。
- **响应头**：HSTS / `X-Frame-Options: DENY` / `X-Content-Type-Options: nosniff` / `Referrer-Policy` / CSP / `Permissions-Policy`。
- **错误收敛**：生产环境全局异常仅返回 `detail`，`error` 仅 DEBUG 环境附加；`/docs` / `/redoc` / `/openapi.json` 生产环境默认 403。

> 生产环境变量（见 `.env.example`）：`CORS_ORIGINS` / `TOKEN_TTL_HOURS` / `TOKEN_CLEANUP_INTERVAL_SECONDS` / `ADMIN_PASSWORD` / `MAX_UPLOAD_SIZE_MB` / `LOG_LEVEL` / `LOGIN_IP_MAX_FAILS` / `LOGIN_IP_WINDOW_SECONDS` / `DEBUG` 等。

---

## 生产部署

### Docker（推荐）

```bash
docker compose up -d
```

`docker-compose.yml` 以 non-root（uid 10001）运行，挂载 `uploads` / `server.db` / `logs` / `.fernet_key` 卷并注入生产环境变量，附 healthcheck。

### gunicorn（Linux）

```bash
pip install gunicorn
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name files.example.com;
    client_max_body_size 500M;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### systemd 服务（Linux）

```ini
# /etc/systemd/system/fileserver.service
[Unit]
Description=File Server
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

---

## 手机访问

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

## 测试

```bash
pip install -r requirements.txt
pytest                          # 全套测试
pytest tests/test_security.py   # 仅安全 / 并发边界用例
```

测试覆盖：基础 API、登录锁 / IP 节流 / 多会话隔离 / Token 过期清理、响应 Schema、批量下载上限、分类映射 CRUD、孤儿清理、大文件上传、Alembic 迁移。**全套 62 passed**。CI（`.github/workflows/docker.yml`）以 `pytest` 作为合并门禁。

---

## 状态与已知项

**已交付（功能完整，全套测试通过）：**

- 认证 / RBAC / 审批流 / 用户管理
- 文件管理（上传 / 下载 / 预览 / 批量 / 分页 / 搜索 / 进度条）
- 分类管理（可配置扩展名映射）
- 审计日志、孤儿文件清理
- 安全基线（argon2 / Fernet / 限流 / CORS / 响应头 / 错误收敛 / docs 生产 403）
- 结构化日志、Alembic 迁移、Service 分层、前端模块化、Docker 部署

**长期可选（未实施，按需推进）：**

- `ARCH-9` JWT + refresh：以 access + refresh token 替代自研 `tokens` 表，实现无状态扩展。
- `ARCH-10` Postgres / 异步 IO：将 `DATABASE_URL` 切到 Postgres（`asyncpg` + `run_in_threadpool`），支持多实例横向扩展。

**已知能力缺口（非缺陷）：** 密码找回 / 邮件、文件版本历史、全文内容检索、分享外链、存储配额、多实例横向扩展（依赖 ARCH-10）。

---

## Android 客户端调用示例

```kotlin
// Retrofit 接口定义
interface FileApi {
    @POST("api/auth/login")
    suspend fun login(@Body body: AuthRequest): Response<AuthResponse>

    @GET("api/files")
    suspend fun listFiles(@Query("category") category: String? = null): Response<FileListResponse>

    @Multipart
    @POST("api/upload")
    suspend fun uploadFile(
        @Part file: MultipartBody.Part,
        @Part("category") category: RequestBody,
        @Header("Authorization") token: String? = null,
    ): Response<UploadResponse>

    @Streaming
    @GET("api/download/{path}")
    suspend fun downloadFile(@Path("path", encoded = true) path: String): Response<ResponseBody>
}
```
