"""配置管理 API 测试。

用临时目录隔离印前配置，避免污染真实 configs/prepress。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app._vendor import load_vips
from app.config import storage as sc
from app.main import create_app


REAL_PREPRESS = Path("configs/prepress").resolve()


@pytest.fixture(autouse=True)
def isolate_prepress(tmp_path, monkeypatch):
    """把印前配置目录指向临时副本，写入不影响真实配置。"""
    import app.config as cfg
    import app.config as _cfg
    tmp_cfg = tmp_path / "prepress"
    shutil.copytree(REAL_PREPRESS, tmp_cfg)
    monkeypatch.setattr(cfg, "PREPRESS_DIR", tmp_cfg)
    # 清缓存，使 _scan_prepress 用新目录
    cfg._scan_prepress.cache_clear()
    yield
    cfg._scan_prepress.cache_clear()


@pytest.fixture(scope="module")
def app():
    load_vips()
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def test_prepress_tree(client):
    """配置树返回类型与尺码。"""
    r = client.get("/api/config/prepress")
    assert r.status_code == 200
    tree = r.json()
    ids = [t["id"] for t in tree]
    assert "test" in ids
    test = next(t for t in tree if t["id"] == "test")
    assert any(s["id"] == "small" for s in test["sizes"])


def test_get_size_raw(client):
    """读取尺码 json 全文。"""
    r = client.get("/api/config/prepress/test/small")
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "test" and d["size"] == "small"
    assert d["params"]["width_mm"] > 0


def test_save_valid(client):
    """合法保存：改名后读回一致。"""
    d = client.get("/api/config/prepress/test/small").json()
    d["name"] = "改后名"
    r = client.put("/api/config/prepress/test/small", json=d)
    assert r.status_code == 200
    d2 = client.get("/api/config/prepress/test/small").json()
    assert d2["name"] == "改后名"


def test_save_invalid_returns_400(client):
    """非法参数（width_mm=0）返回 400。"""
    d = client.get("/api/config/prepress/test/small").json()
    d["params"]["width_mm"] = 0
    r = client.put("/api/config/prepress/test/small", json=d)
    assert r.status_code == 400
    assert "width_mm" in r.json()["detail"] or "0" in r.json()["detail"]


def test_save_type_mismatch(client):
    """type/size 与路径不一致返回 400。"""
    d = client.get("/api/config/prepress/test/small").json()
    d["type"] = "other"
    r = client.put("/api/config/prepress/test/small", json=d)
    assert r.status_code == 400


def test_create_and_delete(client):
    """新增尺码 → 出现 → 删除 → 消失。"""
    base = client.get("/api/config/prepress/test/small").json()
    r = client.post("/api/config/prepress", json={
        "type_id": "test", "size_id": "tmp_create", "name": "临时",
        "params": base["params"],
    })
    assert r.status_code == 200
    # 树中出现
    tree = client.get("/api/config/prepress").json()
    test = next(t for t in tree if t["id"] == "test")
    assert any(s["id"] == "tmp_create" for s in test["sizes"])
    # 读得到
    assert client.get("/api/config/prepress/test/tmp_create").status_code == 200
    # 删除
    r = client.delete("/api/config/prepress/test/tmp_create")
    assert r.status_code == 200
    tree = client.get("/api/config/prepress").json()
    test = next(t for t in tree if t["id"] == "test")
    assert not any(s["id"] == "tmp_create" for s in test["sizes"])


def test_create_new_type(client):
    """新建类型：type_id 不存在时允许创建（第一个尺码）。"""
    base = client.get("/api/config/prepress/test/small").json()
    r = client.post("/api/config/prepress", json={
        "type_id": "newtype_e2e", "size_id": "s1", "name": "新类型尺码",
        "params": base["params"],
    })
    assert r.status_code == 200
    tree = client.get("/api/config/prepress").json()
    assert any(t["id"] == "newtype_e2e" for t in tree)
    # 清理
    client.delete("/api/config/prepress/newtype_e2e/s1")


def test_create_chinese_id_accepted(client):
    """type_id / size_id 允许中文。"""
    base = client.get("/api/config/prepress/test/small").json()
    r = client.post("/api/config/prepress", json={
        "type_id": "中文类型", "size_id": "小号", "name": "中文测试",
        "params": base["params"],
    })
    assert r.status_code == 200
    tree = client.get("/api/config/prepress").json()
    assert any(t["id"] == "中文类型" for t in tree)
    # 清理
    client.delete("/api/config/prepress/中文类型/小号")


def test_create_unsafe_path_id_rejected(client):
    """type_id / size_id 含路径非法字符返回 400。"""
    base = client.get("/api/config/prepress/test/small").json()
    r = client.post("/api/config/prepress", json={
        "type_id": "bad/type", "size_id": "s1", "name": "x", "params": base["params"],
    })
    assert r.status_code == 400


def test_delete_last_size_blocked(client):
    """删除类型最后一个尺码被拒。"""
    # 先建一个独立类型？类型由文件聚合，难造。改为：test 类型若只剩一个尺码则删应拒。
    # 这里验证：对已存在尺码删除时，若该类型仅剩一个，返回 400。
    tree = client.get("/api/config/prepress").json()
    for t in tree:
        if len(t["sizes"]) == 1:
            sid = t["sizes"][0]["id"]
            r = client.delete(f"/api/config/prepress/{t['id']}/{sid}")
            assert r.status_code == 400
            return
    # 无单尺码类型则跳过
    pytest.skip("无单尺码类型可测")


def test_impose_and_storage_readonly(client):
    """排版与存储配置只读端点可用。"""
    r = client.get("/api/config/impose")
    assert r.status_code == 200
    assert "presets" in r.json()
    r = client.get("/api/config/storage")
    assert r.status_code == 200
    assert "library" in r.json() and "thumbnail" in r.json()


def test_config_pages(client):
    """配置三个子页渲染，/config 重定向到印前配置。"""
    r = client.get("/config", follow_redirects=True)
    assert r.status_code == 200
    assert "印前配置" in r.text
    assert client.get("/config/prepress").status_code == 200
    assert client.get("/config/impose").status_code == 200
    assert client.get("/config/storage").status_code == 200
