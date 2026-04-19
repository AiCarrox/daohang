import os
import sys
import json
import time
import hashlib
import secrets
import shutil
import subprocess
import fcntl
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

import yaml
from flask import Flask, request, jsonify, session, render_template, redirect

# ── Config ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = "/home/cc-dan/projects/webstack-share/webstack-site"
YAML_PATH = os.path.join(SITE_DIR, "data", "webstack.yml")
SETTINGS_YAML_PATH = os.path.join(SITE_DIR, "data", "settings.yml")
HUGO_CMD = f"cd {SITE_DIR} && hugo --minify"
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
PASSWORD_FILE = os.path.join(BASE_DIR, ".password_hash")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
MAX_BACKUPS = 50
DEFAULT_USERS = ["陌殇", "杨洪洪洪洪", "CARROT", "嘻哈哈", "小苏肉", "逆地无天", "止戈"]
DEFAULT_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "changeme")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_PATH='/',
    PERMANENT_SESSION_LIFETIME=30 * 24 * 3600,  # 30 days
)

# ── Rate limiting ───────────────────────────────────────
_login_attempts = {}

def check_rate_limit(ip):
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    _login_attempts[ip] = attempts
    return len(attempts) < 5

def record_attempt(ip):
    _login_attempts.setdefault(ip, []).append(time.time())

# ── Auth helpers ────────────────────────────────────────
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt, h

def load_users():
    if not os.path.exists(USERS_FILE):
        users = []
        for username in DEFAULT_USERS:
            salt, password_hash = hash_password(DEFAULT_PASSWORD)
            users.append({"username": username, "salt": salt, "hash": password_hash})
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def get_public_users():
    return [user['username'] for user in load_users()]


def verify_user_password(username, password):
    for user in load_users():
        if user['username'] != username:
            continue
        _, password_hash = hash_password(password, user['salt'])
        return password_hash == user['hash']
    return False


def update_user_password(username, new_password):
    users = load_users()
    for user in users:
        if user['username'] == username:
            salt, password_hash = hash_password(new_password)
            user['salt'] = salt
            user['hash'] = password_hash
            save_users(users)
            return True
    return False


def verify_password(password):
    if not os.path.exists(PASSWORD_FILE):
        return False
    with open(PASSWORD_FILE, 'r') as f:
        data = json.load(f)
    _, h = hash_password(password, data['salt'])
    return h == data['hash']

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({"ok": False, "error": "未登录"}), 401
        return f(*args, **kwargs)
    return decorated

# ── YAML manager ───────────────────────────────────────
def load_data():
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data or []

def save_data(data):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(BACKUP_DIR, f"webstack_{ts}.yml")
    shutil.copy2(YAML_PATH, backup)
    cleanup_backups()

    content = yaml_serialize(data)

    lock_path = YAML_PATH + ".lock"
    with open(lock_path, 'w') as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            tmp = YAML_PATH + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(content)
            # validate
            with open(tmp, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
            os.rename(tmp, YAML_PATH)
        except Exception:
            shutil.copy2(backup, YAML_PATH)
            raise
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)

def yaml_serialize(data):
    """Custom serializer preserving the format Hugo expects."""
    lines = ["---\n"]
    for cat in data:
        lines.append(f"\n- taxonomy: \"{cat['taxonomy']}\"")
        lines.append(f"  icon: {cat.get('icon', 'fas fa-folder')}")
        if 'list' in cat:
            lines.append("  list:")
            for term in cat['list']:
                lines.append(f"    - term: \"{term['term']}\"")
                lines.append("      links:")
                for link in term.get('links', []):
                    _append_link(lines, link, 8)
        else:
            lines.append("  links:")
            for link in (cat.get('links') or []):
                _append_link(lines, link, 4)
    return '\n'.join(lines) + '\n'

def _append_link(lines, link, indent):
    sp = ' ' * indent
    title = link.get('title', '').replace('"', '\\"')
    desc = link.get('description', '').replace('"', '\\"')
    lines.append(f'{sp}- title: "{title}"')
    lines.append(f'{sp}  url: {link.get("url", "")}')
    if link.get('logo'):
        lines.append(f'{sp}  logo: {link["logo"]}')
    lines.append(f'{sp}  description: "{desc}"')

def cleanup_backups():
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("webstack_")],
        reverse=True
    )
    for f in files[MAX_BACKUPS:]:
        os.remove(os.path.join(BACKUP_DIR, f))

# ── Hugo builder ───────────────────────────────────────
def build_site():
    try:
        result = subprocess.run(
            HUGO_CMD, shell=True, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Hugo 构建超时"

# ── Settings Logic ──────────────────────────────────────
def load_settings():
    if not os.path.exists(SETTINGS_YAML_PATH):
        return {}
    try:
        with open(SETTINGS_YAML_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {}

def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_YAML_PATH), exist_ok=True)
        with open(SETTINGS_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        return True, None
    except Exception as e:
        return False, str(e)

# ── Routes: Auth ───────────────────────────────────────
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/admin/auth/check', methods=['GET'])
def auth_check():
    return jsonify({
        "ok": bool(session.get('authenticated')),
        "username": session.get('username'),
        "users": get_public_users(),
    })

@app.route('/api/admin/login', methods=['POST'])
def login():
    ip = request.headers.get('X-Real-IP', request.remote_addr)
    if not check_rate_limit(ip):
        return jsonify({"ok": False, "error": "尝试次数过多，请稍后再试"}), 429
    record_attempt(ip)

    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    remember = data.get('remember', False)

    if verify_user_password(username, password):
        session.permanent = bool(remember)
        session['authenticated'] = True
        session['username'] = username
        session['login_time'] = time.time()
        return jsonify({"ok": True, "username": username})
    return jsonify({"ok": False, "error": "用户名或密码错误"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route('/api/admin/password', methods=['POST'])
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    current_password = body.get('current_password', '')
    new_password = body.get('new_password', '')
    username = session.get('username', '')

    if not verify_user_password(username, current_password):
        return jsonify({"ok": False, "error": "当前密码错误"}), 400
    if not new_password:
        return jsonify({"ok": False, "error": "新密码不能为空"}), 400

    update_user_password(username, new_password)
    return jsonify({"ok": True, "message": "密码修改成功"})

@app.route('/api/admin/settings', methods=['GET'])
@login_required
def api_get_settings():
    return jsonify({"ok": True, "data": load_settings()})

@app.route('/api/admin/settings', methods=['POST'])
@login_required
def api_post_settings():
    req = request.get_json(silent=True) or {}
    if "data" not in req or not isinstance(req["data"], dict):
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    ok, err = save_settings(req["data"])
    if not ok:
        return jsonify({"ok": False, "error": f"保存设置失败: {err}"}), 500

    build_ok, build_msg = build_site()
    if not build_ok:
        return jsonify({"ok": False, "error": f"配置已保存，但重建静态站点失败: {build_msg}"}), 500

    return jsonify({"ok": True, "message": "配置已保存并重建成功"})

# ── Routes: Data ───────────────────────────────────────
@app.route('/api/admin/data', methods=['GET'])
@login_required
def get_data():
    return jsonify({"ok": True, "data": load_data()})

@app.route('/api/admin/data', methods=['POST'])
@login_required
def save_data_route():
    body = request.get_json(silent=True) or {}
    data = body.get('data')
    if not isinstance(data, list):
        return jsonify({"ok": False, "error": "数据格式无效"}), 400
    try:
        save_data(data)
        ok, output = build_site()
        return jsonify({"ok": ok, "message": "保存成功并已重建" if ok else "站点重建失败"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/admin/favicon', methods=['GET'])
@login_required
def get_favicon():
    url = request.args.get('url', '')
    try:
        domain = urlparse(url if '://' in url else 'https://' + url).netloc
        if domain:
            return jsonify({"ok": True, "favicon": f"https://favicon.im/{domain}"})
    except Exception:
        pass
    return jsonify({"ok": False, "error": "URL 无效"}), 400

@app.route('/api/admin/rebuild', methods=['POST'])
@login_required
def rebuild():
    ok, output = build_site()
    return jsonify({"ok": ok, "message": output})

@app.route('/api/admin/export')
@login_required
def export_data():
    fmt = request.args.get('format', 'yaml')
    if fmt == 'json':
        data = load_data()
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return app.response_class(
            content, mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=webstack.json'}
        )
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    return app.response_class(
        content, mimetype='text/yaml',
        headers={'Content-Disposition': 'attachment; filename=webstack.yml'}
    )

@app.route('/api/admin/import', methods=['POST'])
@login_required
def import_data():
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "未提供文件"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    raw = f.read().decode('utf-8')
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({"ok": False, "error": "YAML 或 JSON 文件无效"}), 400
    if not isinstance(data, list):
        return jsonify({"ok": False, "error": "数据必须是分类列表"}), 400
    for i, cat in enumerate(data):
        if not isinstance(cat, dict) or 'taxonomy' not in cat:
            return jsonify({"ok": False, "error": f"第 {i} 项不是有效分类"}), 400
    try:
        save_data(data)
        ok, output = build_site()
        return jsonify({"ok": ok, "message": "导入成功并已重建" if ok else "站点重建失败"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── Main ───────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5099)
