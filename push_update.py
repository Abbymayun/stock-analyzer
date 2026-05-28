#!/usr/bin/env python3
"""推送更新数据到GitHub"""
import json, os, base64, urllib.request, urllib.error, subprocess
from datetime import datetime

TOKEN = "PUSH_TOKEN_PLACEHOLDER"
REPO = "Abbymayun/stock-analyzer"
API = f"https://api.github.com/repos/{REPO}"
BASE_DIR = "/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer"

def api(method, path, data=None):
    url = f"{API}{path}"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutoClaw"
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  Error {e.code}: {e.read().decode()[:200]}")
        return None

# 获取远程最新SHA
ref = api("GET", "/git/ref/heads/main")
base_sha = ref["object"]["sha"]
print(f"Base: {base_sha}")

# 获取本地变更文件
result = subprocess.run(
    ["git", "diff-tree", "-r", "--no-commit-id", "--name-only", "origin/main", "HEAD"],
    capture_output=True, text=True, cwd=BASE_DIR
)
changed = [f for f in result.stdout.strip().split("\n") if f.strip()]
print(f"Changed: {len(changed)} files")

# 只上传关键文件
target = [f for f in changed if f.startswith("data/") or f in ("app.js","index.html","style.css","server.py") or f.startswith("scripts/")]
print(f"Uploading: {len(target)} files...")

tree_items = []
for fp in target:
    full = os.path.join(BASE_DIR, fp)
    if not os.path.exists(full):
        continue
    size = os.path.getsize(full)
    with open(full, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    blob = api("POST", "/git/blobs", {"content": content, "encoding": "base64"})
    if blob:
        mode = "100755" if fp.endswith(".sh") else "100644"
        tree_items.append({"path": fp, "mode": mode, "type": "blob", "sha": blob["sha"]})
        print(f"  ✓ {fp} ({size//1024}KB)")

print("Creating tree...")
tree = api("POST", "/git/trees", {"base_tree": base_sha, "tree": tree_items})
if not tree:
    print("FAILED: tree")
    exit(1)

msg = f"📊 更新分析数据 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
commit = api("POST", "/git/commits", {"message": msg, "tree": tree["sha"], "parents": [base_sha]})
if not commit:
    print("FAILED: commit")
    exit(1)

result = api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"]})
if result:
    print(f"✅ 推送成功! {commit['sha'][:8]}")
else:
    print("FAILED: push")
