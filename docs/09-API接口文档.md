# 09 - API 接口文档

> 状态：与 `app/web/routes.py` 同步 · 最后更新：2026-08-28

## 1. 概述

### 1.1 基础信息

- **Base URL**：`http://<host>:<port>`（默认 `http://127.0.0.1:8000`）
- **协议**：HTTP/1.1，除 WebSocket 外均为普通 JSON 请求/响应
- **内容类型**：`application/json`（上传为 `multipart/form-data`）
- **字符集**：UTF-8

### 1.2 通用响应约定

| 类型 | 说明 |
|------|------|
| 成功 | HTTP 2xx，响应体为 JSON（各接口单独定义） |
| 业务错误 | HTTP 400，`{"detail": "<错误描述>"}` |
| 未找到 | HTTP 404，`{"detail": "..."}` |

> FastAPI 默认校验错误（请求体字段不符）为 HTTP 422，`{"detail": [...]}`。

### 1.3 任务状态枚举

| 值 | 含义 |
|----|------|
| `pending` | 已入队，等待调度（受并发上限限制） |
| `running` | 正在执行 |
| `succeeded` | 成功完成 |
| `failed` | 失败 |

### 1.4 任务 State 结构

所有任务查询与 WebSocket 推送共用 `State` 结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 任务状态枚举（见 1.3） |
| `stage` | string | 当前阶段名（如 "预检" / "处理区域" / "写入"） |
| `progress` | int | 进度百分比 0-100 |
| `message` | string | 当前详情 |
| `outputs` | array | 产物列表（见下） |
| `thumb_path` | string | 缩略图路径（成功后指向库内） |
| `error` | string | 失败时的错误描述 |

**outputs 项结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | string | 产物文件绝对路径（入库后指向库内） |
| `format` | string | 格式：`psd` / `tif` / `png` |
| `width_px` | int | 画布像素宽 |
| `height_px` | int | 画布像素高 |
| `layers` | int | 层数（PSD 为实际层数，平面格式为 1） |
| `library_id` | string | 入库后的文件库 id（未入库无此字段） |

---

## 2. 健康检查

### `GET /health`

容器 HEALTHCHECK 与运维探活用。

**响应**：`200`

```json
{ "status": "ok" }
```

---

## 3. 印前配置查询

### `GET /api/types`

获取印前配置的类型列表。

**响应**：`200`

```json
[
  { "id": "bedsheet", "name": "床单" },
  { "id": "quilt_ab", "name": "被罩AB面" }
]
```

### `GET /api/sizes/{type_id}`

获取某类型下的尺码列表。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `type_id` | string | 类型 id |

**响应**：`200`

```json
[ { "id": "150x200", "name": "150x200cm" } ]
```

**错误**：`404` 类型不存在

### `GET /api/params/{type_id}/{size_id}`

获取某尺码的印前参数 + save_name 模板 + 占位符变量名列表（前端据此渲染变量输入框）。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `type_id` | string | 类型 id |
| `size_id` | string | 尺码 id |

**响应**：`200`

```json
{
  "params": { "width_mm": 1500, "height_mm": 2000, "...": "完整 Params 字段" },
  "save_name_template": "印前_%(type)_%(size)",
  "placeholders": ["type", "size"]
}
```

**错误**：`404` 尺码不存在

> `params` 字段定义见 `02-配置文件规范` §3。`placeholders` 收集自 `save_name` 与所有 `text_marks.items[].text` 的 `%(name)s` 占位符（去重保序）。

---

## 4. 印前配置管理

### `GET /api/config/prepress`

获取印前配置树（类型 → 尺码）。

**响应**：`200`

```json
[
  {
    "id": "bedsheet", "name": "床单",
    "sizes": [ { "id": "150x200", "name": "150x200cm" } ]
  }
]
```

### `GET /api/config/prepress/{type_id}/{size_id}`

获取某尺码配置 JSON 全文（含 `type` / `size` / `name` / `params`）。返回前迁移旧 marks 字段。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `type_id` | string | 类型 id |
| `size_id` | string | 尺码 id |

**响应**：`200`

```json
{
  "type": "bedsheet",
  "size": "150x200",
  "name": "150x200cm",
  "params": { "width_mm": 1500, "...": "" }
}
```

**错误**：`404` 尺码不存在

### `PUT /api/config/prepress/{type_id}/{size_id}`

保存尺码配置（校验后落盘 + 重载，立即对新任务生效）。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `type_id` | string | 类型 id（须与 body.type 一致） |
| `size_id` | string | 尺码 id（须与 body.size 一致） |

**请求体**：

```json
{
  "type": "bedsheet",
  "size": "150x200",
  "name": "150x200cm",
  "params": { "width_mm": 1500, "...": "" }
}
```

**响应**：`200`

```json
{ "saved": "bedsheet/150x200" }
```

**错误**：`400` type/size 不一致或校验失败

### `POST /api/config/prepress`

新建尺码配置（允许新建类型）。

**请求体**：

```json
{
  "type_id": "bedsheet",
  "size_id": "180x200",
  "name": "180x200cm",
  "params": { "width_mm": 1800, "...": "" }
}
```

**响应**：`200`

```json
{ "created": "bedsheet/180x200", "file": "bedsheet_180x200.json" }
```

**错误**：`400` 缺字段 / 尺码已存在 / 校验失败

### `DELETE /api/config/prepress/{type_id}/{size_id}`

删除尺码配置。不允许删空类型（类型至少保留 1 个尺码）。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `type_id` | string | 类型 id |
| `size_id` | string | 尺码 id |

**响应**：`200`

```json
{ "deleted": "bedsheet/180x200" }
```

**错误**：`400` 尺码不存在 / 仅剩此尺码

### `POST /api/config/prepress/rename`

重命名尺码的 type/size id 与显示名（改 id 等于重命名文件 + 改写文件内字段）。

**请求体**：

```json
{
  "old_type": "bedsheet",
  "old_size": "150x200",
  "new_type": "bedsheet",
  "new_size": "160x220",
  "new_name": "160x220cm"
}
```

**响应**：`200`

```json
{ "renamed": "bedsheet/160x220", "file": "bedsheet_160x220.json" }
```

**错误**：`400` 原尺码不存在 / 新 id 含非法字符 / 目标已存在 / 校验失败

> id 禁路径非法字符 `/ \ : * ? " < > |` 及空白。

---

## 5. 排版配置查询

### `GET /api/config/impose`

获取排版配置只读摘要（含 layout，前端据此渲染槽位网格）。

**响应**：`200`

```json
{
  "version": 1,
  "presets": [
    {
      "id": "double_bedsheet",
      "name": "双幅床单拼版",
      "canvas": { "width_mm": 2600, "height_mm": 9000, "dpi": 150, "bitdepth": 8 },
      "layout": { "mode": "grid", "rows": 1, "cols": 2, "default_fit_mode": "stretch" },
      "gutters": { "horizontal_mm": 10, "vertical_mm": 10, "margin_mm": 20 },
      "marks": { "crop_marks": true, "crop_mark_length_mm": 5, "crop_mark_offset_mm": 3, "registration_marks": false },
      "output": { "format": "tif", "compression": "deflate" }
    }
  ]
}
```

> 排版配置字段定义见 `02-配置文件规范` §4。当前排版提交走自由内联配置（见 §8），预设仅作展示。

---

## 6. 存储配置

### `GET /api/config/storage`

获取存储配置只读摘要。

**响应**：`200`

```json
{
  "library": { "path": "data/library", "db_filename": "library.db" },
  "thumbnail": { "format": "webp", "max_size_px": 400, "quality": 80 },
  "tasks": { "max_concurrency": 2 }
}
```

### `PUT /api/config/storage/tasks`

修改任务并发上限。落盘 `storage.json` 并重载，对调度器立即生效（新拉起的任务按新上限排队，运行中任务不受影响）。

**请求体**：

```json
{ "max_concurrency": 1 }
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `max_concurrency` | int | 并行任务上限，≥1 |

**响应**：`200`

```json
{ "max_concurrency": 1 }
```

**错误**：`400` `max_concurrency` 非 ≥1 整数

> 调度机制见 `07-文件存储` §4.3：`submit` 入队（pending），调度线程按上限拉起 worker。

---

## 7. 上传

### `POST /api/upload`

上传图片并入文件库，返回库内路径（供生成读取）。

**请求体**：`multipart/form-data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | file | 图片文件（png/jpg/tif/psd） |

**响应**：`200`

```json
{
  "image_id": "01M134P3WJ6Y",
  "path": "E:/.../data/library/images/01M134P3WJ6Y/original.png",
  "original_name": "apple.png",
  "width": 1440,
  "height": 1000,
  "size_bytes": 123456
}
```

**错误**：`400` 入库失败

---

## 8. 印前生成

### `POST /api/generate`

提交印前生成任务，入队后台执行，返回 `task_id`。任务受并发上限限制，可能处于 `pending`。

**请求体**：

```json
{
  "type_id": "bedsheet",
  "size_id": "150x200",
  "image_path": "E:/.../data/library/images/01M134P3WJ6Y/original.png",
  "save_name": "印前_床单_150x200",
  "vars": { "type": "床单", "size": "150x200" }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type_id` | string | 是 | 类型 id |
| `size_id` | string | 是 | 尺码 id |
| `image_path` | string | 是 | 输入图片路径（上传或文件库返回的 path） |
| `save_name` | string | 否 | 覆盖配置的 save_name（仍解析 `%(name)s` 占位符） |
| `vars` | object | 否 | 占位符变量字典，填充 save_name 与 text_marks |

**响应**：`200`

```json
{ "task_id": "54db1ece..." }
```

**错误**：`400` 缺字段 / 图片不存在 · `404` 尺码不存在

> 生成脚本逻辑见 `04-预检与生成参数` 与 `app/tasks/scripts/prepress.py`。

---

## 9. 排版提交

### `POST /api/impose/submit`

提交排版任务（自由内联配置），入队后台执行，返回 `task_id`。

图件按原始尺寸（仅旋转，不缩放）行优先流式铺排，从画布左上角开始，无间距无边距。任一图件超出画布则失败。

**请求体**：

```json
{
  "canvas": { "width_mm": 2600, "height_mm": 9000, "dpi": 150 },
  "output": { "compression": "deflate" },
  "save_name": "双幅拼版_001",
  "slots": [
    { "image_id": "01M134P3WJ6Y", "rotation": 0 },
    { "image_id": "01M134WMD17Q", "rotation": 90 }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `canvas.width_mm` | float | 是 | 画布宽（mm），>0 |
| `canvas.height_mm` | float | 是 | 画布高（mm），>0 |
| `canvas.dpi` | int | 是 | 分辨率，≥1 |
| `output.compression` | string | 否 | 压缩方式，默认 `deflate` |
| `save_name` | string | 否 | 保存名 |
| `slots` | array | 是 | 槽位列表（按顺序），非空 |
| `slots[].image_id` | string | 是 | 文件库图件 id |
| `slots[].rotation` | int | 否 | 旋转角度，∈ {0, 90, 180, 270}，默认 0 |

**响应**：`200`

```json
{ "task_id": "a80a47d1..." }
```

**错误**：`400` canvas 非法 / slots 为空 / image_id 缺失 / rotation 非法 / 配置非法

> 排版输出普通 TIF（不分层，带透明 alpha），alpha 语义见 `02-配置文件规范` §4.3。

---

## 10. 任务状态与产物

### `GET /api/tasks/{task_id}`

查任务当前 State。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `task_id` | string | 任务 id |

**响应**：`200`（结构见 §1.4）

```json
{
  "task_id": "54db1ece...",
  "status": "succeeded",
  "stage": "写入",
  "progress": 100,
  "message": "生成完成 5 层，1 个文件 uuid=...",
  "outputs": [
    {
      "path": "E:/.../data/library/images/.../original.psd",
      "format": "psd",
      "width_px": 886,
      "height_px": 886,
      "layers": 5,
      "library_id": "01M134XYZ..."
    }
  ],
  "thumb_path": "E:/.../data/library/images/.../thumb.webp",
  "error": ""
}
```

**错误**：`404` 任务不存在

### `GET /api/tasks/{task_id}/download/{fmt}`

下载产物文件（按格式）。

| 路径参数 | 类型 | 说明 |
|----------|------|------|
| `task_id` | string | 任务 id |
| `fmt` | string | 格式：`psd` / `tif` / `png` |

**响应**：`200` 文件流（`FileResponse`，文件名同产物名）

**错误**：`404` 任务不存在 / 产物文件不存在 / 无此格式 · `400` 任务未成功

### `GET /api/tasks/{task_id}/thumb`

下载任务缩略图（webp）。

**响应**：`200` `image/webp` 文件流

**错误**：`404` 任务不存在 / 无缩略图 / 缩略图不存在

---

## 11. 文件库

### `GET /api/library`

文件库列表（按 `created_at` 倒序，支持筛选与分页）。

**查询参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `source` | string | — | 来源筛选：`upload` / `prepress` / `impose` |
| `ref_type` | string | — | 关联类型筛选 |
| `ref_size` | string | — | 关联尺码筛选 |
| `q` | string | — | 按 `original_name` 模糊搜索 |
| `limit` | int | 100 | 每页条数 |
| `offset` | int | 0 | 偏移量 |

**响应**：`200`

```json
{
  "items": [
    {
      "id": "01M134P3WJ6Y",
      "original_name": "apple.png",
      "stored_name": "original.png",
      "format": "png",
      "width_px": 1440,
      "height_px": 1000,
      "dpi": 72,
      "mode": "RGBA",
      "size_bytes": 123456,
      "source": "upload",
      "ref_type": null,
      "ref_size": null,
      "task_id": null,
      "path": "E:/.../data/library/images/01M134P3WJ6Y/original.png"
    }
  ],
  "count": 1,
  "total": 1
}
```

> `path` 为库内原图绝对路径，供印前生成页"从文件库选择"直接用。`total` 为当前筛选条件下的总条数。

### `GET /api/library/{image_id}`

单条记录详情。

**响应**：`200`（结构同上 items 项，无 `path`）

**错误**：`404` 记录不存在

### `GET /api/library/{image_id}/thumb`

缩略图（webp）。

**响应**：`200` `image/webp` 文件流

**错误**：`404` 记录不存在 / 缩略图不存在

### `GET /api/library/{image_id}/download`

下载原图。

**响应**：`200` 文件流（文件名为 `original_name`）

**错误**：`404` 记录不存在 / 文件不存在

### `DELETE /api/library/{image_id}`

删除一条（文件 + 元数据）。

**响应**：`200`

```json
{ "deleted": "01M134P3WJ6Y" }
```

**错误**：`404` 记录不存在

---

## 12. WebSocket

### `WS /ws`

任务进度实时推送。连接后服务端先下发当前全量任务，后续每次 State 变更实时推送。

**连接**：`ws://<host>:<port>/ws`（或 `wss://` HTTPS）

**连接时下发**：当前所有任务的 State（每条一条消息，结构同下）。

**推送消息**（服务端 → 客户端）：

```json
{
  "task_id": "54db1ece...",
  "status": "running",
  "stage": "处理区域",
  "progress": 45,
  "message": "FaceA (1/2)",
  "outputs": [],
  "thumb_path": "",
  "error": ""
}
```

> 消息体 = `{task_id, ...State}`（见 §1.4）。客户端可发心跳文本保持连接，服务端不处理内容仅 `receive_text` 维持。

**前端约定**（`task_badge.js` / `app.js`）：
- 全站任务徽标订阅 WS，按 `status` 计数显示
- 印前生成页任务队列按 `pending → running → succeeded/failed` 排序

---

## 13. 页面路由（HTML）

非 API，返回 Jinja2 渲染的 HTML 页面，列出以备参考：

| 方法 | 路径 | 页面 |
|------|------|------|
| GET | `/` | 印前生成 |
| GET | `/library` | 文件库 |
| GET | `/impose` | 排版拼版 |
| GET | `/config` | 配置入口（重定向到 `/config/prepress`） |
| GET | `/config/prepress` | 印前配置 |
| GET | `/config/impose` | 排版配置（只读） |
| GET | `/config/storage` | 存储配置（部分可改） |

---

## 14. 与其他文档的关系

- `02-配置文件规范`：印前/排版/存储配置字段定义与校验规则
- `04-预检与生成参数`：印前生成各层逻辑
- `05b-排版规范`：排版拼版规则
- `06-任务处理引擎`：任务调度与并发限制
- `07-文件存储`：文件库存储与并发上限机制
