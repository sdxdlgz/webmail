# Outlook 邮件管理系统

轻量级 Web 应用，用于统一管理多个 Outlook 邮箱账号。支持多用户、分组管理、邮件查看等功能。

## 功能特性

### 用户系统
- 多用户支持，数据隔离
- 管理员/普通用户角色
- 用户注册（可配置开关）
- 首次登录强制修改密码

### 账号管理
- 添加/编辑/删除邮箱账号
- 批量导入账号（支持文本粘贴和文件上传）
- 批量测活（检测 token 有效性）
- 导出账号数据
- 账号分组管理
- 搜索和筛选

### 邮件功能
- 查看邮件列表（支持分页）
- 阅读邮件详情（自动标记已读）
- 删除邮件
- 多文件夹支持（收件箱/已发送/垃圾箱等）
- 未读邮件统计
- 邮件搜索
- 按分组筛选邮箱

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 拉取镜像
docker pull your-username/webmail:latest

# 运行容器
docker run -d \
  --name webmail \
  -p 8000:8000 \
  -v webmail-data:/app/backend/data \
  -e DEFAULT_ADMIN_PASSWORD=your-secure-password \
  -e TOKEN_ENC_KEY=your-fernet-key \
  your-username/webmail:latest
```

或使用 Docker Compose：

```yaml
version: '3.8'
services:
  webmail:
    image: your-username/webmail:latest
    container_name: webmail
    ports:
      - "8000:8000"
    volumes:
      - webmail-data:/app/backend/data
    environment:
      - DEFAULT_ADMIN_PASSWORD=your-secure-password
      - TOKEN_ENC_KEY=your-fernet-key
    restart: unless-stopped

volumes:
  webmail-data:
```

### 方式二：手动部署

#### 1. 安装依赖

```bash
cd webmail
pip install -r backend/requirements.txt
```

#### 2. 启动服务

```bash
python start.py
```

或者使用 uvicorn 直接启动：

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### 3. 访问应用

打开浏览器访问 `http://localhost:8000`

默认登录账号：
- 用户名: `admin`
- 密码: `admin123`

> 首次登录会强制要求修改密码

## 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 监听端口 | `8000` |
| `DATA_FILE_PATH` | 数据文件路径 | `backend/data/data.json` |
| `TOKEN_ENC_KEY` | Token 加密密钥 (Fernet) | 空 (不加密) |
| `DEFAULT_ADMIN_USERNAME` | 默认管理员用户名 | `admin` |
| `DEFAULT_ADMIN_PASSWORD` | 默认管理员密码 | `admin123` |
| `CORS_ORIGINS` | CORS 允许的源 | `localhost` |
| `SESSION_COOKIE_SECURE` | Cookie Secure 标志 | `false` |
| `SESSION_COOKIE_SAMESITE` | Cookie SameSite 属性 | `lax` |

### 生成加密密钥

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

## 账号数据格式

批量导入时，每行一个账号，格式如下：

```
邮箱----密码----refresh_token----client_id
```

示例：
```
user@hotmail.com----password123----M.C526_BAY.0.U.-xxx...----8b4ba9dd-3ea5-4e5f-86f1-ddba2230dcf2
```

## VPS 部署

### 使用 systemd

创建服务文件 `/etc/systemd/system/webmail.service`：

```ini
[Unit]
Description=Outlook Mail Manager
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/webmail
Environment="TOKEN_ENC_KEY=your-fernet-key"
Environment="DEFAULT_ADMIN_PASSWORD=your-secure-password"
ExecStart=/usr/bin/python3 start.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable webmail
sudo systemctl start webmail
```

### 使用 Nginx 反向代理

创建配置文件 `/etc/nginx/sites-available/webmail`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

启用站点并获取 SSL 证书：

```bash
sudo ln -s /etc/nginx/sites-available/webmail /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

## 安全建议

1. **修改默认密码**: 首次部署后立即修改默认管理员密码
2. **启用 HTTPS**: 生产环境务必使用 HTTPS
3. **设置加密密钥**: 配置 `TOKEN_ENC_KEY` 加密存储的 refresh_token
4. **限制访问**: 使用防火墙或 Nginx 限制访问来源
5. **定期备份**: 备份 `backend/data/data.json` 数据文件

## API 文档

启动服务后访问 `http://localhost:8000/docs` 查看 Swagger API 文档。

## 技术栈

- **后端**: Python 3.11 + FastAPI + Uvicorn
- **前端**: 原生 HTML/CSS/JavaScript
- **存储**: JSON 文件
- **API**: Microsoft Graph API
- **容器**: Docker

## 许可证

MIT License
