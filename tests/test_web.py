"""Web 层测试：FastAPI TestClient。

用 test_small 配置（100×100mm）避免大图耗时。
"""
from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app._vendor import load_vips
from app.main import create_app
from app.tasks.scripts._state import State
from app.web import tasks as task_mgr


@pytest.fixture(scope="module")
def app():
    load_vips()
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_image_bytes():
    """造一张 PNG 字节流用于上传。"""
    img = Image.new("RGB", (600, 600), (200, 180, 255))
    ImageDraw.Draw(img).rectangle([100, 100, 500, 500], fill=(255, 120, 100))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------


def test_create_app():
    """create_app 返回 FastAPI 实例。"""
    app = create_app()
    assert app.title == "印前文件服务器"


def test_api_types(client):
    """GET /api/types 返回类型列表。"""
    r = client.get("/api/types")
    assert r.status_code == 200
    types = r.json()
    ids = [t["id"] for t in types]
    assert "test" in ids


def test_api_sizes(client):
    """GET /api/sizes/test 返回尺码列表。"""
    r = client.get("/api/sizes/test")
    assert r.status_code == 200
    sizes = r.json()
    assert any(s["id"] in ("152x202", "small") for s in sizes)


def test_api_params(client):
    """GET /api/params/test/152x202 返回 params + placeholders。"""
    r = client.get("/api/params/test/152x202")
    assert r.status_code == 200
    data = r.json()
    assert "params" in data
    assert "placeholders" in data
    assert any(z["name"] == "FaceA" for z in data["params"]["zones"])
    # test_152x202 配置 save_name="%(name)s_%(size)s"，text 含 %(name)s %(size)s
    assert "name" in data["placeholders"]
    assert "size" in data["placeholders"]


def test_api_params_no_placeholders(client):
    """无占位符配置返回空 placeholders 列表。"""
    # test_small 无 save_name、text="demo" 无占位符
    r = client.get("/api/params/test/small")
    assert r.status_code == 200
    data = r.json()
    assert data["placeholders"] == []


def test_api_upload(client, sample_image_bytes):
    """POST /api/upload 存图到临时目录，返回 path。"""
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "image_id" in data and "path" in data
    assert Path(data["path"]).exists()


def test_state_on_update_callback():
    """State.update 触发 on_update 回调。"""
    calls = []
    state = State(on_update=lambda s: calls.append((s.status.value, s.progress)))
    state.update("预检", 10, "开始")
    state.update("画布", 20, "ok")
    state.succeed(outputs=[], message="done")
    assert len(calls) == 3
    assert calls[0] == ("running", 10)
    assert calls[2] == ("succeeded", 100)


def test_tasks_submit(client, sample_image_bytes):
    """tasks.submit 起线程跑 run，最终 succeeded。"""
    # 先上传图
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    image_path = r.json()["path"]

    # 用 test_small 配置（100×100mm 快）
    config_path = "configs/prepress/test_small.json"
    output_root = "data/outputs/test_web"

    task_id = task_mgr.submit(image_path, config_path, output_root)
    assert task_id

    # 轮询到终态
    for _ in range(60):
        state = task_mgr.get(task_id)
        if state.status.value in ("succeeded", "failed"):
            break
        time.sleep(0.5)
    assert state.status.value == "succeeded", f"任务失败: {state.error}"
    assert state.progress == 100
    assert len(state.outputs) >= 1


def test_generate_endpoint(client, sample_image_bytes):
    """POST /api/generate 返回 task_id，轮询 /api/tasks/{id} 到 succeeded。"""
    # 上传
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    image_path = r.json()["path"]

    # 提交生成（用 small 100×100mm 快）
    r = client.post("/api/generate", json={
        "type_id": "test",
        "size_id": "small",
        "image_path": image_path,
    })
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    # 轮询
    for _ in range(60):
        r = client.get(f"/api/tasks/{task_id}")
        if r.status_code == 200:
            data = r.json()
            if data["status"] in ("succeeded", "failed"):
                break
        time.sleep(0.5)
    assert data["status"] == "succeeded", f"生成失败: {data.get('error')}"


def test_ws_progress(client, sample_image_bytes):
    """WS 连接收到任务进度推送。"""
    # 先建立 WS 连接（TestClient 的 websocket_connect）
    with client.websocket_connect("/ws") as ws:
        # 触发一个任务
        r = client.post(
            "/api/upload",
            files={"file": ("sample.png", sample_image_bytes, "image/png")},
        )
        image_path = r.json()["path"]
        task_id = task_mgr.submit(
            image_path, "configs/prepress/test_small.json", "data/outputs/test_ws"
        )
        # 收消息直到看到该 task_id 的 succeeded
        seen = False
        for _ in range(60):
            msg = ws.receive_json()
            if msg.get("task_id") == task_id and msg.get("status") == "succeeded":
                seen = True
                break
        assert seen, "未收到 succeeded 推送"


# ---- 文件库集成 ----


def test_upload_ingests_into_library(client, sample_image_bytes):
    """上传图入文件库，返回库内路径与尺寸。"""
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "image_id" in data and "path" in data
    assert Path(data["path"]).exists()
    assert data["width"] == 600 and data["height"] == 600

    # 库列表能看到
    lr = client.get("/api/library?source=upload")
    assert lr.status_code == 200
    items = lr.json()["items"]
    assert any(i["id"] == data["image_id"] for i in items)

    # 缩略图可取
    tr = client.get(f"/api/library/{data['image_id']}/thumb")
    assert tr.status_code == 200


def test_generate_ingests_outputs_into_library(client, sample_image_bytes):
    """生成成功后产物入文件库，关联 type/size。"""
    # 上传
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    image_path = r.json()["path"]

    # 生成
    r = client.post("/api/generate", json={
        "type_id": "test",
        "size_id": "small",
        "image_path": image_path,
    })
    task_id = r.json()["task_id"]

    # 轮询到终态
    for _ in range(60):
        r = client.get(f"/api/tasks/{task_id}")
        data = r.json()
        if data["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.5)
    assert data["status"] == "succeeded", f"生成失败: {data.get('error')}"

    # 产物有 library_id
    assert any(o.get("library_id") for o in data["outputs"])

    # 库中能按 prepress 来源筛出该产物
    lr = client.get("/api/library?source=prepress")
    items = lr.json()["items"]
    lib_ids = {o.get("library_id") for o in data["outputs"]}
    assert any(i["id"] in lib_ids for i in items)
    # 关联信息正确
    matched = next(i for i in items if i["id"] in lib_ids)
    assert matched["ref_type"] == "test" and matched["ref_size"] == "small"


def test_library_delete(client, sample_image_bytes):
    """删除库记录：文件与列表均消失。"""
    r = client.post(
        "/api/upload",
        files={"file": ("sample.png", sample_image_bytes, "image/png")},
    )
    image_id = r.json()["image_id"]
    dr = client.delete(f"/api/library/{image_id}")
    assert dr.status_code == 200
    assert client.get(f"/api/library/{image_id}").status_code == 404
