#!/usr/bin/env python3
"""通过GitHub API推送本地commit到远程仓库"""
import json, os, sys, subprocess, hashlib, base64
import urllib.request, urllib.error

TOKEN = "PUSH_TOKEN_PLACEHOLDER"
REPO = "Abbymayun/stock-analyzer"
API = f"https://api.github.com/repos/{REPO}"

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
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  API Error {e.code}: {e.read().decode()[:200]}")
        return None

# 获取远程main的SHA
ref = api("GET", "/git/ref/heads/main")
base_sha = ref["object"]["sha"]
print(f"远程main SHA: {base_sha}")

# 获取本地要推送的commit的diff
# 本地 origin/main..HEAD 之间有2个commit
result = subprocess.run(
    ["git", "diff-tree", "-r", "--no-commit-id", "--name-status", "origin/main", "HEAD"],
    capture_output=True, text=True, cwd="/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer"
)

# 也获取commit信息
log_result = subprocess.run(
    ["git", "log", "--format=%H%n%s%n%b%n---END---", "origin/main..HEAD"],
    capture_output=True, text=True, cwd="/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer"
)

commits_text = log_result.stdout.strip().split("---END---")
commits = []
for c in commits_text:
    c = c.strip()
    if not c:
        continue
    lines = c.split('\n')
    sha = lines[0]
    msg = '\n'.join(lines[1:]).strip()
    commits.append({"sha": sha, "message": msg})

print(f"待推送 {len(commits)} 个commit:")
for c in commits:
    print(f"  {c['sha'][:8]} {c['message']}")

# 获取所有变更文件
diff_result = subprocess.run(
    ["git", "diff-tree", "-r", "--no-commit-id", "origin/main", "HEAD"],
    capture_output=True, text=True, cwd="/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer"
)

files = []
for line in diff_result.stdout.strip().split('\n'):
    if not line.strip():
        continue
    parts = line.split('\t')
    if len(parts) >= 2:
        status = parts[0].split()[0]  # A, M, D
        filepath = parts[1]
        files.append((status, filepath))

print(f"\n共 {len(files)} 个文件变更")

# 限制：跳过过大的文件 (>5MB)
MAX_SIZE = 5 * 1024 * 1024
BASE_DIR = "/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer"

# 由于要一次性创建tree并推送，我们采用简化策略：
# 用git bundle打包，或者直接用GitHub API的git blobs
# 但最简单的方式：git format-patch + git am 通过API

# 实际上最简单：用git format-patch生成patch，然后用GitHub API创建commit
# 但GitHub API不支持直接push多个commit

# 最直接的方式：把所有变更打包成一个commit
print("\n创建单个commit包含所有变更...")

# 创建blobs
blobs = {}
tree_items = []
skip_count = 0

for status, filepath in files:
    full_path = os.path.join(BASE_DIR, filepath)
    
    if status == 'D':
        tree_items.append({"path": filepath, "mode": "100644", "type": "blob", "sha": None})
        continue
    
    if not os.path.exists(full_path):
        print(f"  跳过(不存在): {filepath}")
        continue
    
    size = os.path.getsize(full_path)
    if size > MAX_SIZE:
        print(f"  跳过(过大{size//1024}KB): {filepath}")
        skip_count += 1
        continue
    
    with open(full_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode()
    
    print(f"  上传blob: {filepath} ({size//1024}KB)")
    blob = api("POST", "/git/blobs", {"content": content, "encoding": "base64"})
    if blob:
        blobs[filepath] = blob["sha"]
        # 检查是否是可执行文件
        mode = "100755" if filepath.endswith('.sh') or filepath.startswith('scripts/') else "100644"
        tree_items.append({"path": filepath, "mode": mode, "type": "blob", "sha": blob["sha"]})

if skip_count > 0:
    print(f"\n跳过了 {skip_count} 个过大文件")

print(f"\n创建tree ({len(tree_items)} 项)...")
tree = api("POST", "/git/trees", {"base_tree": base_sha, "tree": tree_items})
if not tree:
    print("创建tree失败!")
    sys.exit(1)

print(f"Tree SHA: {tree['sha']}")

# 创建commit
commit_msg = f"📊 更新分析数据 {len(tree_items)}个文件\n\n包含: {', '.join(c['message'] for c in commits)}"
commit = api("POST", "/git/commits", {
    "message": commit_msg,
    "tree": tree["sha"],
    "parents": [base_sha]
})
if not commit:
    print("创建commit失败!")
    sys.exit(1)

print(f"Commit SHA: {commit['sha']}")

# 更新ref
result = api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"]})
if result:
    print(f"\n✅ 推送成功!")
    print(f"https://github.com/{REPO}/commit/{commit['sha']}")
else:
    print("更新ref失败!")
