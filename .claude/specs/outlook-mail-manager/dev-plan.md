# Outlook 邮件管理系统 - 开发计划

## 项目概述
轻量级 Web 应用，用于统一管理多个 Outlook 邮箱账号，通过 Microsoft Graph API 获取和管理邮件。

## 技术栈
- **后端**: FastAPI + Uvicorn
- **前端**: 纯 HTML/CSS/JavaScript
- **存储**: JSON 文件
- **认证**: Session Cookie + 密码哈希

## 功能清单

### 账号管理
- [x] 添加单个账号
- [x] 删除账号
- [x] 批量导入（粘贴多行数据）
- [x] 批量测活（检测 token 有效性）
- [x] 导出账号（备份）
- [x] Token 更新（更新失效的 refresh_token）
- [x] 账号搜索
- [x] 账号分组/标签
- [x] 批量删除账号
- [x] 账号状态显示（有效/失效）

### 邮件功能
- [x] 查看邮件列表
- [x] 阅读邮件详情
- [x] 删除邮件
- [x] 多文件夹（收件箱/已发送/垃圾箱/草稿箱）
- [x] 未读邮件统计
- [x] 邮件搜索（主题/发件人）

### 系统功能
- [x] 用户登录/登出
- [x] Session 管理

## 目录结构
```
webmail/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── config.py            # 配置管理
│   │   ├── models.py            # Pydantic 模型
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # 认证路由
│   │   │   ├── accounts.py      # 账号管理路由
│   │   │   └── mail.py          # 邮件操作路由
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py         # Microsoft Graph API
│   │   │   └── token_cache.py   # Token 缓存
│   │   └── storage/
│   │       ├── __init__.py
│   │       └── json_store.py    # JSON 存储
│   ├── data/
│   │   └── data.json            # 数据文件
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_accounts.py
│   │   └── test_mail.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── README.md
```

---

## 任务分解

### Task-A: 后端基础架构 + 认证系统
**依赖**: 无
**文件范围**:
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/models.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/auth.py`
- `backend/app/storage/__init__.py`
- `backend/app/storage/json_store.py`
- `backend/data/data.json`
- `backend/requirements.txt`
- `backend/tests/__init__.py`
- `backend/tests/test_auth.py`

**功能**:
1. FastAPI 应用初始化
2. 用户登录/登出 API
3. Session 管理 (Cookie)
4. 密码哈希 (bcrypt)
5. JSON 存储层 (文件锁 + 原子写入)
6. 初始管理员账号创建
7. 配置管理（环境变量）

**API**:
- `POST /api/auth/login` - 登录
- `POST /api/auth/logout` - 登出
- `GET /api/auth/me` - 当前用户

**测试命令**: `pytest backend/tests/test_auth.py -v --cov=backend/app --cov-report=term-missing`

---

### Task-B: Outlook 账号管理（完整版）
**依赖**: Task-A
**文件范围**:
- `backend/app/routers/accounts.py`
- `backend/app/models.py` (扩展)
- `backend/app/storage/json_store.py` (扩展)
- `backend/tests/test_accounts.py`

**功能**:
1. 添加单个 Outlook 账号
2. 批量导入账号（解析多行格式：邮箱----密码----refresh_token----client_id）
3. 列出所有账号（支持搜索、分组过滤）
4. 删除单个账号
5. 批量删除账号
6. 更新账号（修改 refresh_token/client_id）
7. 账号分组/标签管理
8. 导出账号数据
9. 敏感字段加密存储 (Fernet)

**API**:
- `GET /api/accounts` - 账号列表（支持 ?search=&group=）
- `POST /api/accounts` - 添加单个账号
- `POST /api/accounts/batch` - 批量导入
- `PUT /api/accounts/{id}` - 更新账号
- `DELETE /api/accounts/{id}` - 删除单个账号
- `POST /api/accounts/batch-delete` - 批量删除
- `GET /api/accounts/export` - 导出账号
- `GET /api/groups` - 获取分组列表
- `POST /api/groups` - 创建分组
- `DELETE /api/groups/{id}` - 删除分组

**测试命令**: `pytest backend/tests/test_accounts.py -v --cov=backend/app --cov-report=term-missing`

---

### Task-C: Microsoft Graph 邮件服务 + 测活
**依赖**: Task-A, Task-B
**文件范围**:
- `backend/app/services/__init__.py`
- `backend/app/services/graph.py`
- `backend/app/services/token_cache.py`
- `backend/app/routers/mail.py`
- `backend/tests/test_mail.py`

**功能**:
1. Refresh Token 换取 Access Token
2. Token 内存缓存（带过期时间）
3. 单个账号测活
4. 批量测活（并发检测所有账号）
5. 获取邮件列表（分页 + 多文件夹）
6. 邮件搜索（主题/发件人）
7. 获取邮件详情
8. 删除邮件
9. 获取未读邮件数
10. 错误处理（429 重试、token 失效处理）

**API**:
- `POST /api/accounts/{id}/verify` - 单个账号测活
- `POST /api/accounts/batch-verify` - 批量测活
- `GET /api/accounts/{id}/messages` - 邮件列表（?folder=&search=&limit=&cursor=）
- `GET /api/accounts/{id}/messages/{msg_id}` - 邮件详情
- `DELETE /api/accounts/{id}/messages/{msg_id}` - 删除邮件
- `GET /api/accounts/{id}/unread-count` - 未读数
- `GET /api/accounts/{id}/folders` - 文件夹列表

**测试命令**: `pytest backend/tests/test_mail.py -v --cov=backend/app --cov-report=term-missing`

---

### Task-D: 前端界面
**依赖**: Task-A, Task-B, Task-C
**文件范围**:
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`

**功能**:
1. 登录页面
2. 账号管理页面
   - 账号列表（状态显示、搜索、分组过滤）
   - 添加单个账号表单
   - 批量导入弹窗（文本框粘贴）
   - 批量测活按钮 + 进度显示
   - 批量删除
   - 导出按钮
   - 编辑账号（更新 token）
   - 分组管理
3. 邮件页面
   - 文件夹切换（收件箱/已发送/垃圾箱/草稿）
   - 邮件列表（分页）
   - 邮件搜索
   - 未读数显示
   - 邮件详情弹窗
   - 删除确认
4. 响应式设计
5. 加载状态 + 错误提示

**测试**: 手动测试

---

### Task-E: 集成与部署
**依赖**: Task-A, Task-B, Task-C, Task-D
**文件范围**:
- `backend/app/main.py` (静态文件挂载)
- `README.md`
- `start.py`

**功能**:
1. 前端静态文件挂载到 FastAPI
2. 环境变量配置文档
3. 部署说明（VPS）
4. 启动脚本
5. 初始化脚本（创建管理员）

---

## 并行执行策略

```
Phase 1:
  └── Task-A: 后端基础 + 认证

Phase 2 (Task-A 完成后并行):
  ├── Task-B: 账号管理
  └── Task-D: 前端界面（静态部分）

Phase 3 (Task-B 完成后):
  └── Task-C: 邮件服务 + 测活

Phase 4:
  └── Task-E: 集成部署
  └── Task-D: 前端完善（对接 API）
```

## 测试覆盖率要求
- 后端每个任务 >= 90% 代码覆盖率
- 单元测试 + 集成测试

## 数据格式

### 账号导入格式
```
邮箱----密码----refresh_token----client_id
邮箱----密码----refresh_token----client_id
...
```

### JSON 存储结构
```json
{
  "users": [
    {"id": "uuid", "username": "admin", "password_hash": "..."}
  ],
  "groups": [
    {"id": "uuid", "name": "默认分组"}
  ],
  "accounts": [
    {
      "id": "uuid",
      "email": "xxx@hotmail.com",
      "password": "encrypted",
      "refresh_token": "encrypted",
      "client_id": "xxx",
      "group_id": "uuid",
      "status": "active|invalid",
      "last_verified": "2024-01-01T00:00:00Z",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```
