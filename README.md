# daohang

基于 [WebStack-Hugo](https://github.com/shenweiyan/WebStack-Hugo) 主题的网址导航站，附带 Flask 后台管理面板。

## 项目结构

```
daohang/
├── WebStack-Hugo/          # Hugo 主题（上游 + 自定义修改）
│   ├── layouts/            # 主题模板
│   └── static/             # 主题静态资源（CSS/JS/字体/图标）
│
├── webstack-site/          # Hugo 站点源码
│   ├── config.toml         # 站点配置
│   ├── data/
│   │   ├── webstack.yml    # 导航链接数据（分类 + 网址）
│   │   ├── headers.yml     # 顶部导航栏按钮（首页/Wiki）
│   │   └── settings.yml    # 搜索背景图、Logo
│   ├── layouts/partials/   # 覆盖主题的模板文件
│   ├── static/assets/css/  # 自定义样式
│   └── public/             # Hugo 构建输出（.gitignore 已排除）
│
└── webstack-admin/         # Flask 后台管理面板
    ├── app.py              # 主程序
    └── templates/          # 管理页面模板
```

## 快速开始

### 1. 安装 Hugo

需要 Hugo extended 版本（0.100+）：

```bash
# Ubuntu/Debian
sudo snap install hugo --channel=extended

# 或从 https://github.com/gohugoio/hugo/releases 下载
```

### 2. 克隆仓库

```bash
git clone https://github.com/AiCarrox/daohang.git
cd daohang

# 主题符号链接（如果丢失）
cd webstack-site/themes
ln -s ../../WebStack-Hugo WebStack-Hugo
cd ../..
```

### 3. 配置站点

编辑 `webstack-site/config.toml`：

```toml
baseURL = "https://your-domain.com/"
title  = "你的站点名称"

[params]
    author        = "your-name"
    description   = "站点描述"
    nightMode     = true          # 深色模式为默认

[params.images]
    searchImageL    = "assets/images/bg-dna.jpg"    # 浅色模式搜索背景
    searchImageD    = "assets/images/bg-dna.jpg"    # 深色模式搜索背景
    logoExpandLight = "assets/images/bi-expand-dark.png"
    logoExpandDark  = "assets/images/bi-expand-light.png"

[params.footer]
    copyright = '&copy; 2024 - {year} Your Name'
```

编辑 `webstack-site/data/settings.yml`（搜索区背景图和 Logo）：

```yaml
backgroundImage: https://your-image-url.png
logoUrl: ''   # 留空则使用 config.toml 中的 logoExpandLight / logoCollapseLight
```

### 4. 配置导航链接

编辑 `webstack-site/data/webstack.yml`，按以下格式添加分类和链接：

```yaml
- taxonomy: "分类名称"
  icon: fas fa-folder        # FontAwesome 图标类名
  links:
    - title: "网站名称"
      url: https://example.com/
      logo: https://example.com/favicon.ico   # 可选，留空则使用默认图标
      description: "网站描述"

- taxonomy: "带子分类的示例"
  icon: fas fa-code
  list:
    - term: "子分类A"
    - term: "子分类B"
```

编辑 `webstack-site/data/headers.yml` 配置顶部导航按钮：

```yaml
- item: 首页
  icon: fa fa-home
  link: "./"
  mode: home

- item: wiki
  icon: fa fa-book
  link: "#wiki-view"
  mode: wiki
```

### 5. 构建与预览

```bash
cd webstack-site

# 本地预览（热重载）
hugo server -D

# 构建静态文件到 public/
hugo --destination public
```

Nginx 指向 `webstack-site/public/` 目录即可。

## 后台管理面板（可选）

### 安装依赖

```bash
cd webstack-admin
python3 -m venv venv
source venv/bin/activate
pip install flask gunicorn pyyaml
```

### 配置

后台管理面板需要在 `app.py` 中修改以下路径变量以匹配你的部署位置：

```python
SITE_DIR = "/path/to/daohang/webstack-site"    # Hugo 站点目录
```

设置环境变量：

```bash
export FLASK_SECRET_KEY="your-random-secret-key"       # 必须，用于 session 加密
export DEFAULT_ADMIN_PASSWORD="your-admin-password"     # 首次运行时的默认管理员密码
```

### 启动

```bash
cd webstack-admin
source venv/bin/activate
gunicorn -b 127.0.0.1:5099 app:app
```

### Nginx 代理配置

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    root /path/to/daohang/webstack-site/public;
    index index.html;

    # 后台管理面板
    location /admin {
        proxy_pass http://127.0.0.1:5099;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/admin/ {
        proxy_pass http://127.0.0.1:5099;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 自定义样式

- `webstack-site/static/assets/css/custom-style.css` — 站点自定义样式（卡片、搜索框、滚动条、移动端侧边栏等）
- `webstack-site/layouts/partials/` — 覆盖主题模板（`footer.html`、`content_header.html`、`sidebar.html` 等）

Hugo 的模板查找机制会优先使用站点 `layouts/` 下的文件，找不到再回退到主题 `WebStack-Hugo/layouts/`。

## 注意事项

- `webstack-site/themes/WebStack-Hugo` 是指向 `../../WebStack-Hugo` 的符号链接，克隆后需确认链接有效
- `users.json`、`.password_hash`、`backups/` 已被 `.gitignore` 排除，不会上传到仓库
- 管理后台修改导航数据后，会自动执行 `hugo` 重新构建 `public/` 目录
- 移动端侧边栏已改用自定义 JS 控制，不再依赖 Bootstrap Modal

## License

[WebStack-Hugo](https://github.com/shenweiyan/WebStack-Hugo) 主题遵循其原始许可证。
