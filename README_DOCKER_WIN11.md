# MinePython — Windows 11 Docker 部署指南

本文档面向 **Windows 11 + Docker Desktop（WSL2 后端）** 的部署场景，补充主 `README.md` 中过于简略的 Docker 章节，并标注**只在 Windows 上才会踩到的坑**。

> 适用版本：MinePython v4.7+（FastAPI + SQLAlchemy 2.0 + SQLite WAL，含文件管理 / 审计 / 组织架构 / 意见反馈模块）。
> 本文档对应仓库已附带修复：`docker-compose.yml` 的 healthcheck 已从 `/docs` 改为 `/`（见文末「已修复项」）。
> 版本升级说明：应用启动时会**自动执行 Alembic 迁移**（`upgrade head`），从旧版本升级只需 `docker compose up -d --build`，新表（如 `org_departments` / `org_members` / `suggestions`）会自动创建，无需手动操作数据库。

---

## 1. 前置条件

| 组件 | 要求 | 说明 |
|------|------|------|
| Windows 11 | 22H2+ | 家庭版 / 专业版均可 |
| Docker Desktop | 4.20+（含 Compose v2） | 从 [docker.com](https://www.docker.com/products/docker-desktop/) 安装 |
| WSL2 | 已启用并设为默认 | Docker Desktop 的 Linux 容器后端 |

验证安装：

```powershell
# 管理员 PowerShell
wsl --install            # 若尚未安装 WSL2（会装 Ubuntu，需重启）
wsl --set-default-version 2

docker --version         # Docker Engine 24+
docker compose version   # 返回 v2.x（注意是空格，不是连字符）
```

> ⚠️ **必须用 `docker compose`（v2 插件）**，本文所有命令都是该语法。老的 `docker-compose`（连字符）已被弃用，不要再装。

---

## 2. Docker Desktop 关键设置（务必核对）

打开 Docker Desktop → **Settings**：

1. **General** → 勾选 ✅ **Use the WSL 2 based engine**（核心开关）。
2. **Resources → WSL Integration** → 勾选你的发行版（如 `Ubuntu`）→ **Apply & Restart**。
3. **Resources → File sharing** → 确认项目所在盘（通常是 `C:`）在共享列表里（WSL2 模式下默认已共享）。
4. （可选）**Resources → Advanced** → 给 WSL2 分配至少 2 GB 内存，避免镜像构建 OOM。

---

## 3. 把项目放到哪里最重要（Windows 专属坑）

容器以 **non-root（uid 10001）** 运行，需要向 `uploads/`、`logs/`、`server.db` 写文件。

- ✅ **推荐**：把项目放在 **WSL2 文件系统**内，例如 `\\wsl$\Ubuntu\home\<你的用户名>\MinePython`。
  这样 uid 10001 的写权限天然成立，最稳。
- ⚠️ **可用但易踩坑**：放在 Windows NTFS 路径（如 `C:\Users\Work\PycharmProjects\MinePython`）。
  通过 DrvFS 映射，绝大多数情况能写，但偶发「Permission denied」。**若遇到写入失败，把目录整体挪进 WSL2 文件系统即可。**

从 Windows 终端进入 WSL2 内的项目：

```powershell
# 直接用 Windows 路径也行（Docker Desktop 会经 WSL2 处理）
cd C:\Users\Work\PycharmProjects\MinePython
```

---

## 4. 部署步骤

### 步骤 0：生成 Fernet 密钥（**不生成必崩**，Windows 专属坑）

`docker-compose.yml` 把宿主的 `./.fernet_key` 以**文件**形式挂载进容器。应用启动时会读取它：

- 若宿主**没有**该文件 → Docker 会自动创建一个**同名目录** → 应用读目录崩溃（`IsADirectoryError`）。
- 若你用 `touch .fernet_key` 建了**空文件** → 应用读到空密钥 → `Fernet(b"")` 抛 `ValueError`，崩溃。
- ✅ **正确做法**：写入一个**有效的 44 字节 base64 密钥**：

```powershell
# 在项目根目录执行（不需要 cryptography 库，纯标准库即可）
python -c "import base64,os; open('.fernet_key','wb').write(base64.urlsafe_b64encode(os.urandom(32)))"
```

> 已帮你生成好（44 字节）。**该文件已 gitignore，切勿提交。** 一旦丢失，库里已加密的明文副本将无法解密 —— 所以必须随卷持久化（compose 已挂载）。

### 步骤 1：配置环境变量（改默认管理员密码）

复制模板并至少修改管理员密码：

```powershell
copy .env.example .env
```

编辑 `.env`（至少改这两项，其他可留默认）：

```ini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=换成强密码          # 默认 admin123 千万别留
ADMIN_NICKNAME=管理员
MAX_UPLOAD_SIZE_MB=500
TZ=Asia/Shanghai
```

> 如需从手机 / 局域网其他机器访问 Web，把 PC 局域网 IP 加进 `CORS_ORIGINS`（逗号分隔），否则浏览器会被 CORS 拦下。

### 步骤 2：构建并启动

```powershell
docker compose up -d --build
```

首次会拉取 `python:3.13-slim` 并安装依赖，约 1–3 分钟。

### 步骤 3：验证

```powershell
docker compose ps          # STATUS 应为 healthy / running
docker compose logs -f     # 看启动日志，确认 "Application startup complete"
```

浏览器访问：

| 入口 | 地址 |
|------|------|
| Web 管理界面 | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs （**生产默认 403**，见下文） |

> `/docs`、`/redoc`、`/openapi.json` 在生产（`APP_DEBUG=false`，默认）下返回 **403**。
> 这是安全设计，不是部署失败。本地调试想打开文档，可在 `.env` 设 `APP_DEBUG=true` 后 `docker compose up -d`。

---

## 5. 局域网 / 手机访问（Windows 防火墙）

同 WiFi 下用手机访问 `http://<PC局域网IP>:8000`，需两步：

1. `.env` 里 `CORS_ORIGINS` 加上 `http://<PC的IP>:8000`；
2. 放行防火墙 8000 端口（**管理员 PowerShell**）：

```powershell
netsh advfirewall firewall add rule name="FileServer" dir=in action=allow protocol=TCP localport=8000
```

查 PC 局域网 IP：`ipconfig` → 看「IPv4 地址」。

---

## 6. 常用运维命令

```powershell
docker compose ps                 # 状态
docker compose logs -f --tail=100 # 实时日志
docker compose restart            # 重启（配置/env 改了要 restart）
docker compose down               # 停止并移除容器（数据卷保留）
docker compose up -d --build      # 改了代码后重建

# 升级镜像（拉最新 python 基础镜像）
docker compose build --no-cache
docker compose up -d
```

数据持久化位置（均在项目根目录，已 bind mount，重建容器不丢）：

```
uploads/      # 上传文件
logs/         # 运行日志
server.db     # SQLite 数据库（WAL）
.fernet_key   # 加密密钥（不可丢）
```

---

## 7. Windows 部署故障速查

| 现象 | 根因 | 解决 |
|------|------|------|
| 容器一直 `unhealthy` | 旧 healthcheck 探 `/docs`（生产 403） | 已修复为 `/`，`docker compose up -d` 重新拉起即可 |
| 容器反复重启 / 日志 `IsADirectoryError` 或 `Fernet key must be 44...` | `./.fernet_key` 不存在（被 Docker 建成了目录）或为空文件 | 见「步骤 0」生成有效密钥文件 |
| 上传/写库报 `Permission denied` | NTFS 路径下 non-root uid 10001 无写权限 | 把项目挪到 WSL2 文件系统（`\\wsl$\Ubuntu\home\...\`） |
| 浏览器能开 `/` 但 API 被 CORS 拦截 | `CORS_ORIGINS` 没包含访问来源 IP | `.env` 加上来源 IP，`docker compose restart` |
| `docker: 'compose' not found` | 用了老 `docker-compose` 或 v2 未装 | 用 `docker compose`（空格）；升级 Docker Desktop |
| 构建慢 / 拉镜像失败 | 网络问题 | 配置国内镜像加速器（Docker Desktop → Settings → Docker Engine → registry-mirrors） |
| 手机访问超时 | 防火墙未放行 8000 | 见第 5 节 `netsh` 命令 |

---

## 8. 已对仓库做的修复

- `docker-compose.yml`：`healthcheck` 由 `curl -f http://localhost:8000/docs` 改为 `curl -f http://localhost:8000/`。
  原因：生产环境 `DEBUG=false` 时 `/docs` 返回 403，`curl -f` 判为失败，容器会被持续标记为 **unhealthy**。
  根路径 `/` 始终返回 200（index.html），作为探针正确。
- 已生成 `.fernet_key`（44 字节有效密钥），`docker compose up -d` 可直接启动。

---

## 9. 与 Linux 部署的差异小结

| 项 | Linux | Windows 11 |
|----|-------|-----------|
| 命令 | `docker compose` | 同左（Docker Desktop 自带 v2） |
| 后端 | native / WSL2 | 必须 WSL2 引擎 |
| 路径 | ext4 | 建议放 WSL2 内，避免 NTFS 权限坑 |
| 非 root 写权限 | 天然 | NTFS 下可能需挪到 WSL2 文件系统 |
| 防火墙 | `ufw allow 8000` | `netsh advfirewall ...` |
| 密钥文件 | 同 | 同，务必是**有效密钥**而非空文件 |
