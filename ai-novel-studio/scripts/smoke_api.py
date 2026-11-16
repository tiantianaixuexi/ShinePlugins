"""End-to-end smoke test for the local API.

Starts the real FastAPI sidecar on a free port with a throwaway data directory,
walks the core writing loop (project -> volume -> chapter -> save -> version ->
restore), prints a PASS/FAIL line per step and exits non-zero on the first
failure. Safe to run repeatedly; it never touches the developer's library.

    backend/.venv/Scripts/python.exe scripts/smoke_api.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
TOKEN = "smoke-" + uuid.uuid4().hex
TIMEOUT = 20

_failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _failures
    status = "PASS" if condition else "FAIL"
    if not condition:
        _failures += 1
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"[{status}] {label}{suffix}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    method: str,
    url: str,
    payload: object | None = None,
    *,
    auth: bool = True,
) -> tuple[int, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, body


def main() -> int:
    port = free_port()
    data_dir = Path(tempfile.mkdtemp(prefix="novel-studio-smoke-"))
    env = {
        **os.environ,
        "NOVEL_STUDIO_DATA_DIR": str(data_dir),
        "NOVEL_STUDIO_AUTH_TOKEN": TOKEN,
        "NOVEL_STUDIO_PORT": str(port),
        "NOVEL_STUDIO_LOG_LEVEL": "WARNING",
        "NOVEL_STUDIO_LOG_JSON": "1",
        "PYTHONUTF8": "1",
    }

    process = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"

    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=1):
                    break
            except (urllib.error.URLError, OSError):
                if process.poll() is not None:
                    check("sidecar starts", False, f"exited with {process.returncode}")
                    return 1
                time.sleep(0.25)
        else:
            check("sidecar starts", False, "timeout")
            return 1
        check("sidecar starts", True)

        status, health = request("GET", f"{base}/api/health")
        check("authenticated health", status == 200 and health.get("status") == "ok", str(health))

        status, _ = request("GET", f"{base}/api/health", auth=False)
        check("unauthenticated health is rejected", status == 401, f"got {status}")

        status, created = request(
            "POST",
            f"{base}/api/projects",
            {
                "name": "冒烟测试",
                "novel_type": "科幻",
                "synopsis": "用于验证章节与版本流程",
                "target_word_count": 100000,
                "target_chapter_count": 100,
            },
        )
        check("create project", status == 201, str(created))
        project_id = created["id"]
        check("chinese name round-trips", created["name"] == "冒烟测试", created["name"])

        status, volume = request(
            "POST", f"{base}/api/projects/{project_id}/volumes", {"title": "第一卷"}
        )
        check("create volume", status == 201, str(volume))

        status, chapter = request(
            "POST",
            f"{base}/api/projects/{project_id}/chapters",
            {"title": "第一章", "volume_id": volume["id"], "content": "天地玄黄。"},
        )
        check("create chapter", status == 201, str(chapter))
        chapter_id = chapter["id"]
        # "天地玄黄。" -> four CJK characters; punctuation is not counted.
        check("word count computed", chapter["word_count"] == 4, str(chapter["word_count"]))

        status, saved = request(
            "PUT",
            f"{base}/api/projects/{project_id}/chapters/{chapter_id}",
            {
                "content": "天地玄黄，宇宙洪荒。日月盈昃，辰宿列张。",
                "row_version": chapter["row_version"],
            },
        )
        check("save chapter", status == 200 and saved["word_count"] == 16, str(saved))

        status, conflict = request(
            "PUT",
            f"{base}/api/projects/{project_id}/chapters/{chapter_id}",
            {"content": "并发写入", "row_version": chapter["row_version"]},
        )
        check("stale write is rejected", status == 409, f"got {status}")

        status, versions = request(
            "POST", f"{base}/api/projects/{project_id}/chapters/{chapter_id}/versions"
        )
        check("snapshot created", status == 201 and len(versions) >= 2, str(len(versions)))

        baseline = versions[-1]
        status, restored = request(
            "POST",
            f"{base}/api/projects/{project_id}/chapters/{chapter_id}"
            f"/versions/{baseline['id']}/restore",
        )
        check("restore previous version", status == 200, str(restored))
        check(
            "restore brings back the old text",
            restored.get("content") == "天地玄黄。",
            repr(restored.get("content")),
        )

        # Restoring must not lose the text that was replaced.
        status, after_restore = request(
            "GET", f"{base}/api/projects/{project_id}/chapters/{chapter_id}/versions"
        )
        check(
            "restore archived the replaced text",
            status == 200 and len(after_restore) == len(versions) + 1,
            f"{len(after_restore)} vs {len(versions)}",
        )
        check(
            "archived version holds the longer text",
            bool(after_restore) and after_restore[0]["word_count"] == 16,
            str(after_restore[0]["word_count"]) if after_restore else "no versions",
        )

        status, stats = request("GET", f"{base}/api/projects/{project_id}/stats")
        check(
            "stats reflect content",
            stats["chapters"] == 1 and stats["words"] > 0,
            json.dumps(stats, ensure_ascii=False),
        )

        status, models = request("GET", f"{base}/api/model-configs")
        check("default model template exists", status == 200 and len(models) >= 1, str(status))

        status, operations = request("GET", f"{base}/api/ai/operations")
        check(
            "ai operations listed",
            status == 200 and "polish" in (operations.get("operations") or []),
            str(operations),
        )

        status, prompts = request("GET", f"{base}/api/ai/prompts")
        check(
            "prompt templates seeded",
            status == 200 and isinstance(prompts, list) and len(prompts) >= 7,
            str(prompts)[:120],
        )

        # A fresh install has a template model with no key, so this must fail as
        # a provider error (502) or a clear "no model" message (422) — never an
        # unhandled 500.
        status, failure = request(
            "POST",
            f"{base}/api/ai/polish",
            {
                "project_id": project_id,
                "chapter_id": chapter_id,
                "selection": "天地玄黄。",
                "instruction": "更凝练",
            },
        )
        check(
            "unconfigured provider fails cleanly",
            status in (422, 502) and isinstance(failure, dict) and "error" in failure,
            f"status={status} body={str(failure)[:160]}",
        )

        status, model = request(
            "POST",
            f"{base}/api/model-configs",
            {
                "name": "测试模型",
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:1/v1",
                "model_name": "test-model",
                "api_key": "sk-smoke-secret",
            },
        )
        check("create model config", status == 201, str(model))
        check("api key not leaked", "sk-smoke-secret" not in json.dumps(model))
        check("has_api_key flag set", model.get("has_api_key") is True)

        secrets = data_dir / "secrets.json"
        check(
            "secret stored encrypted",
            secrets.exists() and "sk-smoke-secret" not in secrets.read_text(encoding="utf-8"),
        )

        status, _ = request("DELETE", f"{base}/api/projects/{project_id}?hard=true")
        check("hard delete project", status == 204, f"got {status}")

    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    print()
    if _failures:
        print(f"SMOKE FAILED: {_failures} check(s) failed")
        return 1
    print("SMOKE PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())