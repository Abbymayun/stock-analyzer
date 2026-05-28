#!/usr/bin/env python3
"""将本地最新数据推送到 GitHub Pages（不依赖 git commit）"""
import json, os, base64, urllib.request, urllib.error
from datetime import datetime

TOKEN = os.environ.get("PUSH_TOKEN", "PUSH_TOKEN_PLACEHOLDER")
REPO = "Abbymayun/stock-analyzer"
API = f"https://api.github.com/repos/{REPO}"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

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
        print(f"  API Error {e.code}: {e.read().decode()[:200]}")
        return None

def push_data():
    """上传 data/ 目录下所有 JSON 文件到 GitHub"""
    # 获取远程最新 commit SHA
    ref = api("GET", "/git/ref/heads/main")
    if not ref:
        print("无法获取远程分支信息")
        return False
    base_sha = ref["object"]["sha"]

    # 收集要上传的文件
    files = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(DATA_DIR, fname)
        size = os.path.getsize(fpath)
        if size > 5 * 1024 * 1024:  # 跳过 >5MB
            continue
        files.append((f"data/{fname}", fpath, size))

    print(f"上传 {len(files)} 个数据文件...")

    tree_items = []
    for rel_path, abs_path, size in files:
        with open(abs_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        blob = api("POST", "/git/blobs", {"content": content, "encoding": "base64"})
        if blob:
            tree_items.append({"path": rel_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            print(f"  ✓ {rel_path} ({size//1024}KB)")
        else:
            print(f"  ✗ {rel_path} 上传失败")

    if not tree_items:
        print("没有文件需要上传")
        return False

    # 获取 data 目录的 tree SHA
    parent_tree = api("GET", f"/git/trees/{base_sha}")
    data_tree_sha = None
    for item in parent_tree.get("tree", []):
        if item["path"] == "data" and item["type"] == "tree":
            data_tree_sha = item["sha"]
            break

    if data_tree_sha:
        # 在现有 data tree 基础上更新
        data_tree = api("POST", f"/git/trees", {"base_tree": data_tree_sha, "tree": tree_items})
    else:
        data_tree = api("POST", f"/git/trees", {"tree": tree_items})

    if not data_tree:
        print("创建 data tree 失败")
        return False

    # 用新的 data tree 替换原来的
    root_tree = api("POST", "/git/trees", {
        "base_tree": base_sha,
        "tree": [{"path": "data", "mode": "040000", "type": "tree", "sha": data_tree["sha"]}]
    })
    if not root_tree:
        print("创建 root tree 失败")
        return False

    msg = f"📊 自动更新分析数据 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = api("POST", "/git/commits", {
        "message": msg,
        "tree": root_tree["sha"],
        "parents": [base_sha]
    })
    if not commit:
        print("创建 commit 失败")
        return False

    result = api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"]})
    if result:
        print(f"✅ 推送成功! {commit['sha'][:8]}")
        return True
    else:
        print("推送失败")
        return False

if __name__ == "__main__":
    import sys
    ok = push_data()
    sys.exit(0 if ok else 1)
