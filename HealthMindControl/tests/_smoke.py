"""可选真库冒烟：启动应用并访问核心端点（需要 .env 中真实可达的 PG/Kafka）。"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient  # noqa: E402
import healthmind_control.app as hmc  # noqa: E402

client = TestClient(hmc.app)
with client:
    paths = ("/", "/ui/dashboard", "/ui/tasks", "/ui/fixtures", "/ui/rows", "/ui/kafka", "/ui/releases",
             "/ui/repair", "/ui/audit", "/ui/about", "/api/summary", "/api/backlogs",
             "/api/rows/meta", "/api/fixtures/tables", "/api/releases", "/api/kafka/groups", "/api/audit/actions",
             "/api/repair/plan?query=meal")
    for path in paths:
        r = client.get(path)
        print(path, r.status_code, len(r.text))
    print("smoke done")
