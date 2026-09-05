"""Deterministic fixtures in the isolated E2E database; no model calls."""
import base64
import json
from pathlib import Path
import sys

from src.models.content import ContentType, GeneratedContent
from src.storage import ContentStore
from src.utils import config


store = ContentStore(database_url=config.DATABASE_URL)
manifest = Path("/app/data/e2e-fixtures.json")
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=")

if sys.argv[1] == "seed":
    content_id = store.save_content(GeneratedContent(
        content="Disposable browser verification fixture", title="E2E fixture",
        content_type=ContentType.BLOG,
    ))
    path = Path(config.MEDIA_STORAGE_ROOT) / "e2e.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    media = store.save_media_asset(content_id, "image", "upload", "e2e.png", str(path), "image/png")
    for run_id in ("e2e_idle", "e2e_reconnect", "e2e_auth"):
        store.create_run(run_id, "E2E", "blog", "casual", "deepseek", "fixture")
        store.append_run_event(run_id, "step_token", {"index": 1, "delta": "A"})
    memory = Path(config.MEMORY_DIR) / "E2E_PERSISTENCE.txt"
    memory.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text("e2e-volume-marker", encoding="utf-8")
    fixtures = {"content_id": content_id, "media_id": media["id"], "media_size": len(png)}
    manifest.write_text(json.dumps(fixtures), encoding="utf-8")
    print(json.dumps(fixtures))
elif sys.argv[1] == "complete":
    store.append_run_event("e2e_reconnect", "step_token", {"index": 1, "delta": "B"})
    store.transition_run_and_append_event(
        "e2e_reconnect", expected_statuses={"running"}, new_status="completed",
        event_type="run_complete", payload={"final_content": {"content": "AB"}},
    )
elif sys.argv[1] == "verify":
    fixtures = json.loads(manifest.read_text())
    assert store.get_content(fixtures["content_id"])["title"] == "E2E fixture"
    asset = store.get_media_asset(fixtures["media_id"])
    assert Path(asset["file_path"]).read_bytes() == png
    assert (Path(config.MEMORY_DIR) / "E2E_PERSISTENCE.txt").read_text() == "e2e-volume-marker"
    assert store.list_run_events("e2e_idle")[0]["seq"] == 1
    print("Persistence verified after container recreation: content, media bytes, memory file, run events")
else:
    raise SystemExit("Unknown fixture command")
