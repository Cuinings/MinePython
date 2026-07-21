# File Server v4.2

支持用户系统的本地文件服务器，提供文件上传/下载/分类管理 RESTful API 及 Web 管理界面。

## 功能

| 模块 | 说明 |
|------|------|
| 用户系统 | 注册/登录(支持昵称), Token 认证, 密码加盐 SHA-256 |
| 管理员面板 | 添加/编辑/删除用户, 审批注册, 查看密码哈希 |
| 文件管理 | 上传/下载/删除/列表, 批量上传, 元数据追踪(上传者/IP/时间) |
| 分类管理 | 自动归类(70+扩展名→8个分类), 手动分类, 新建/删除分类 |
| Web 界面 | 登录→文件浏览→上传 三屏流程, 中/英/俄三语切换 |
| Swagger | 在线 API 文档 + 交互测试 |

## 环境要求

- Python 3.9+
- pip

## 安装

### 本地运行

```bash
# 创建虚拟环境
python -m venv venv

# 激活 (Windows)
venv\Scripts\activate

# 激活 (Linux/macOS)
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动
python server.py
```

### Docker 一键部署

```bash
docker compose up -d
```

访问 `http://localhost:8000`。

启动后访问：

| 入口 | 地址 |
|------|------|
| Web 管理界面 | `http://localhost:8000` |
| Swagger API 文档 | `http://localhost:8000/docs` |
| ReDoc 文档 | `http://localhost:8000/redoc` |

## 目录结构

```
MinePython/
├── server.py              # 瘦入口（启动 + 启动信息）
├── app/                   # 后端包
│   ├── __init__.py
│   ├── main.py            # FastAPI 组装 + Web UI 服务
│   ├── config.py          # 配置常量（路径、扩展名映射）
│   ├── database.py        # SQLite 连接、建表、迁移
│   ├── models.py          # Pydantic 请求/响应模型
│   ├── utils.py           # 密码哈希、文件分类、大小格式化
│   ├── auth.py            # 登录/注册 + 认证守卫
│   ├── admin.py           # 管理员用户 CRUD
│   ├── files.py           # 文件列表/上传/下载/删除
│   └── categories.py      # 分类管理
├── index.html             # 前端单页应用（HTML/CSS/JS）
├── server.db              # SQLite 数据库（自动生成）
├── uploads/               # 文件存储目录（自动生成）
│   ├── 图片/
│   ├── 文档/
│   ├── 视频/
│   ├── 音频/
│   ├── 压缩包/
│   ├── 代码/
│   ├── 安装包/
│   └── 其他/
└── README.md
```

## 数据库

SQLite，自动建表 `server.db`，含两张表：

```sql
-- 用户表
users (id, username, password, nickname, token, role, status, created_at)

-- 文件记录表
files (id, filename, category, filepath, size, uploaded_by, uploaded_ip, uploaded_at)
```

## API 概览

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | 否 | 注册（支持昵称） |
| POST | `/api/auth/login` | 否 | 登录 |
| GET | `/api/admin/users` | Admin | 用户列表（含昵称、密码哈希） |
| POST | `/api/admin/users` | Admin | 管理员创建用户 |
| PUT | `/api/admin/users/{id}` | Admin | 修改用户所有信息 |
| DELETE | `/api/admin/users/{id}` | Admin | 删除用户 |
| PUT | `/api/admin/users/{id}/approve` | Admin | 审批通过 |
| GET | `/api/admin/pending` | Admin | 待审批用户列表 |
| GET | `/api/files` | 否 | 文件列表 `?category=xxx` |
| POST | `/api/upload` | 可选 | 上传文件 |
| POST | `/api/upload/multiple` | 可选 | 批量上传 |
| GET | `/api/download/{category}/{filename}` | 否 | 下载 |
| DELETE | `/api/files/{category}/{filename}` | 否 | 删除 |
| GET | `/api/categories` | 否 | 分类列表 |
| DELETE | `/api/categories/{name}` | 否 | 删除分类 |
| POST | `/api/organize` | 否 | 整理根目录散落文件 |

认证方式: 请求头 `Authorization: Bearer <token>`

## 手机访问

1. 确保手机与 PC 连同一 WiFi
2. 查看 PC 局域网 IP：`ipconfig`（Windows）/ `ifconfig`（Linux）
3. 手机浏览器访问 `http://<PC的IP>:8000`
4. 如无法访问，放行防火墙端口 8000：

```bash
# Windows 管理员终端
netsh advfirewall firewall add rule name="FileServer" dir=in action=allow protocol=TCP localport=8000

# Linux
sudo ufw allow 8000
```

## 生产部署

### 使用 gunicorn (Linux)

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

### systemd 服务 (Linux)

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
