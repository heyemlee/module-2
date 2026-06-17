# AI Context — Module 2 (生产工程 / 拆板 / 裁切方案)

> Current working memory for building **Module 2 from zero** as a standalone part of the
> factory AI Agent FDE project. Source plan: `factory-ai-agent-fde-plan.html`.
> Updated decision: three people build three major modules. This file focuses on Module 2.

---

## 1. Three-Module Boundary

The FDE work is split across three people / three major modules:

| Module | Core question | Main output |
|---|---|---|
| Module 1 | 客户最终要做哪些柜体？ | 审核通过的柜体级订单 |
| Module 2 | 柜体怎么拆成板件并裁切？ | 板件 BOM、封边数据、裁切方案、生产工单基础数据 |
| Module 3 | 生产数据怎么在车间执行？ | QR 标签、扫码页面、五金安装、组装、包装、出货记录 |

**Important boundary:** Module 2 does **not** own QR code label design, printing, scan pages,
hardware rules, hardware hole rules, assembly steps, packaging, or shipping execution. Those are
Module 3 and later.

---

## 2. Orchestrator And Agent Shape

Recommended architecture:

- Use one **Master Orchestrator Agent** to control the overall project state.
- Treat the three modules as capabilities/services called by the Orchestrator.
- Do not let the three modules freely call each other or privately mutate production state.

Recommended module shape:

| Module | Shape | Reason |
|---|---|---|
| Module 1 | Sales & Design Agent | Customer requirements, measurement review, and design drafting are fuzzy enough to benefit from agentic behavior. |
| Module 2 | Production Engineering Engine | Panel dimensions, edge banding, material rules, and cutting data must be deterministic and auditable. |
| Module 3 | Shopfloor Execution Agent | Shop-floor state is deterministic, while hardware knowledge, SOPs, and exception handling can use AI assistance. |

The Orchestrator owns:

- project status
- module handoff
- gate checks
- blocker assignment
- event log
- audit trail

Module 2 should expose deterministic APIs and return blockers instead of guessing.

---

## 3. Module 2 Mission

Module 2 is the **production engineering module**. It accepts an approved cabinet-level order
from Module 1 and converts it into panel-level production data.

Module 2 owns:

1. Production gate validation.
2. Standard cabinet library.
3. Cabinet-to-panel decomposition rules.
4. Material rules needed for panels.
5. Edge banding rules.
6. Panel BOM generation.
7. Cut list and cutting-plan data.
8. Base production work order data.
9. Cabinet IDs and panel IDs.
10. Blockers for orders that cannot be automatically decomposed.

Module 2 does **not** decide the customer's design. It does not review layout aesthetics. It does
not run shop-floor execution. It turns a confirmed cabinet list into manufacturable panel data.

---

## 4. Input From Module 1

Module 1 sends Module 2 an **Approved Cabinet Order Package**.

Required input:

- `order_id`
- customer / project information
- approved detailed layout reference
- final cabinet list
- cabinet code
- cabinet type
- cabinet width / depth / height
- cabinet quantity
- material / finish selection
- customer confirmation status
- sales confirmation status
- designer approval status
- closed confirmation-item history
- explicit marker that this is **not** Round 1 / preliminary / sales-estimate-only data

Gate rules:

- Round 1 cabinet lists must never enter production.
- `customer_confirmed`, `sales_confirmed`, and `designer_approved` must all be true.
- Open `Confirmation Required` items block Module 2.
- Missing cabinet dimensions, quantity, material, or finish block Module 2.
- Non-standard cabinet codes block Module 2 unless a matching rule exists in the standard
  cabinet library or a manual override has been approved.

Module 1 is responsible for deciding **which cabinets** the customer ordered. Module 2 is
responsible for deciding **how those cabinets become panels**.

---

## 5. Module 2 Internal Data

Module 2 maintains its own production-engineering reference data.

### 5a. Standard Cabinet Library

Defines standard cabinet codes and cabinet structure.

Examples:

- `W301236` = wall cabinet, 30"W x 12"D x 36"H
- `B302435` = base cabinet, 30"W x 24"D x 34.5"H, code height 35

Library fields should include:

- cabinet code
- cabinet type: base / wall / tall / drawer base / sink base / other
- width / depth / height
- door count
- drawer count
- default panel structure
- allowed variations
- whether the cabinet can be automatically decomposed

The standard cabinet library belongs to Module 2.

### 5b. Cabinet Decomposition Rules

Defines how each cabinet type becomes panels.

Typical panel outputs:

- left side panel
- right side panel
- bottom panel
- top panel or stretcher
- back panel
- shelf panel
- door panel reference, if needed for panel production
- drawer box panels only if drawer-box production is in Module 2 scope

Each rule must calculate panel dimensions from cabinet dimensions and material thickness.

### 5c. Material Rules

Defines panel material and thickness.

Examples:

- cabinet box material
- back panel material
- shelf material
- door / finish panel material if included in Module 2 production
- sheet size, e.g. 4x8
- thickness
- grain direction requirement

### 5d. Edge Banding Rules

Defines which panel edges receive banding.

Examples:

- exposed front edge
- shelf front edge
- finished side exposed edges
- hidden wall-side edges
- banding material / color / thickness

Edge banding rules belong to Module 2 because they are required before cutting and panel
production.

---

## 6. Output To Module 3

Module 2 outputs a **Production Engineering Package**.

Required output:

- production work order base data
- cabinet-level production records
- panel-level production records
- cabinet ID
- panel ID
- panel BOM
- cut list
- cutting-plan data
- material list
- edge banding list
- manufacturing notes
- blockers / exceptions

Panel BOM fields:

- panel ID
- source cabinet ID
- panel name
- length
- width
- thickness
- quantity
- material
- finish
- grain direction
- edge banding requirement
- production note

Cutting-plan fields:

- material group
- thickness group
- finish group
- source sheet size
- required panel list
- basic cutting sequence or layout reference
- offcut / remainder record, if available

V1 can start with a reliable cut list and grouped cutting data. Full nesting optimization can be
added later.

---

## 7. API Boundary For Standalone Development

Module 2 should expose APIs so Module 1 and Module 3 do not need to know its internal
decomposition or cutting logic.

Recommended integration model:

- Module 1 calls Module 2 with an approved cabinet-level order.
- Module 2 validates the production gate and generates a production engineering package.
- Module 3 reads the production engineering package by `work_order_id` and handles QR labels,
  hardware, scanning, assembly, packaging, and shipping.

### 7a. Module 1 Creates A Production Engineering Package

Endpoint:

```http
POST /api/module2/production-packages
```

Request body: `ApprovedCabinetOrderPackage`.

Minimum request shape:

```json
{
  "order_id": "ORD-2026-001",
  "project": {
    "customer_name": "Customer Name",
    "address": "Project address"
  },
  "approval": {
    "customer_confirmed": true,
    "sales_confirmed": true,
    "designer_approved": true
  },
  "source": {
    "stage": "final",
    "layout_version": "layout-v3",
    "cabinet_list_version": "cabinet-v5"
  },
  "cabinets": [
    {
      "cabinet_id": "C001",
      "cabinet_code": "B302435",
      "type": "base",
      "width": 30,
      "depth": 24,
      "height": 34.5,
      "quantity": 2,
      "material": "plywood-3/4",
      "finish": "white-shaker"
    }
  ],
  "confirmation_required_items": []
}
```

Successful response:

```json
{
  "ok": true,
  "status": "production_package_created",
  "work_order_id": "WO-2026-001",
  "package_url": "/api/module2/production-packages/WO-2026-001"
}
```

Gate failure response:

```json
{
  "ok": false,
  "status": "gate_failed",
  "blockers": [
    {
      "code": "UNAPPROVED_ORDER",
      "owner": "module1",
      "message": "designer_approved must be true"
    }
  ]
}
```

### 7b. Module 3 Reads Module 2 Output

Core endpoint:

```http
GET /api/module2/production-packages/{work_order_id}
```

Returns the full `ProductionEngineeringPackage`.

Optional read endpoints for V1 or later:

```http
GET /api/module2/production-packages/{work_order_id}/panels
GET /api/module2/production-packages/{work_order_id}/cut-list
GET /api/module2/production-packages/{work_order_id}/edge-banding
```

Minimum response shape for Module 3:

```json
{
  "work_order_id": "WO-2026-001",
  "source_order_id": "ORD-2026-001",
  "status": "engineering_ready",
  "cabinets": [
    {
      "cabinet_id": "C001-1",
      "cabinet_code": "B302435",
      "panels": ["P001", "P002", "P003"]
    }
  ],
  "panels": [
    {
      "panel_id": "P001",
      "cabinet_id": "C001-1",
      "name": "left_side",
      "length": 34.5,
      "width": 24,
      "thickness": 0.75,
      "material": "plywood",
      "finish": "white-shaker",
      "edge_banding": ["front"]
    }
  ],
  "cut_list": [
    {
      "material": "plywood",
      "thickness": 0.75,
      "sheet_size": "48x96",
      "panels": ["P001", "P002", "P003"]
    }
  ],
  "edge_banding_list": [
    {
      "panel_id": "P001",
      "edges": ["front"],
      "banding": "white"
    }
  ]
}
```

### 7c. API Ownership Rule

Module 2 owns the API contract for:

- receiving approved cabinet-level orders from Module 1
- validating production readiness
- creating production engineering packages
- exposing panel BOM, cut list, and edge banding data to Module 3

Module 2 does not push QR labels or shop-floor tasks directly. Module 3 should pull the finished
engineering package by `work_order_id`.

---

## 8. Orchestrator Control Contract

The Master Orchestrator Agent controls Module 2 through API calls, state transitions, idempotency,
and blocker handling. It should not directly edit Module 2's internal standard cabinet library,
decomposition rules, material rules, edge banding rules, or cutting algorithm.

### 8a. Control Model

The Orchestrator controls Module 2 by:

1. Sending only approved Module 1 output to Module 2.
2. Calling Module 2 APIs with a stable `order_id` and idempotency key.
3. Reading Module 2's status and result.
4. Moving the project state only when Module 2 returns `engineering_ready`.
5. Assigning blockers to `module1`, `module2`, `module3`, or `integration`.
6. Recording every request, response, blocker, retry, and handoff in the event log.

Module 2 controls its own production engineering logic. The Orchestrator controls when that logic
runs and whether its result can move downstream.

### 8b. Recommended State Machine

Recommended Module 2 states inside the Orchestrator:

| State | Meaning |
|---|---|
| `module2_not_started` | Module 1 has not handed off a final cabinet order yet. |
| `module2_requested` | Orchestrator has requested Module 2 package creation. |
| `module2_gate_failed` | Module 2 rejected the input before production engineering. |
| `module2_engineering_running` | Module 2 accepted the request and is generating panel/cutting data. |
| `module2_engineering_blocked` | Module 2 cannot finish because a rule, parameter, or upstream field is missing. |
| `module2_engineering_ready` | Module 2 generated a valid Production Engineering Package. |
| `module3_ready` | Orchestrator has approved Module 2 output for Module 3 consumption. |

Only the Orchestrator should update the project-level state. Module 2 should return statuses and
blockers, not mutate the shared project state directly.

### 8c. Commands From Orchestrator To Module 2

Minimum commands:

```http
POST /api/module2/production-packages
GET /api/module2/production-packages/{work_order_id}
```

Recommended later commands:

```http
GET /api/module2/production-packages/{work_order_id}/status
POST /api/module2/production-packages/{work_order_id}/retry
POST /api/module2/production-packages/{work_order_id}/cancel
```

V1 can skip `retry` and `cancel` if package creation is fast and synchronous.

### 8d. Idempotency

The Orchestrator should include an idempotency key when creating a Module 2 package.

Recommended header:

```http
Idempotency-Key: module2:{order_id}:{cabinet_list_version}
```

Rule:

- Same `order_id` + same `cabinet_list_version` should return the same existing `work_order_id`.
- New `cabinet_list_version` should create a new production engineering package version.
- Module 2 should not silently overwrite a previous ready package.

### 8e. Required Module 2 Response Fields For Orchestrator

Every Module 2 response should include:

- `ok`
- `status`
- `order_id`
- `work_order_id`, when created
- `contract_version`
- `input_fingerprint`
- `created_at` or `updated_at`
- `blockers`, when blocked or failed

Example ready response:

```json
{
  "ok": true,
  "status": "engineering_ready",
  "order_id": "ORD-2026-001",
  "work_order_id": "WO-2026-001",
  "contract_version": "module2.v1",
  "input_fingerprint": "cabinet-list-v5:abc123",
  "package_url": "/api/module2/production-packages/WO-2026-001",
  "blockers": []
}
```

Example blocked response:

```json
{
  "ok": false,
  "status": "engineering_blocked",
  "order_id": "ORD-2026-001",
  "contract_version": "module2.v1",
  "input_fingerprint": "cabinet-list-v5:abc123",
  "blockers": [
    {
      "code": "UNSUPPORTED_CABINET_CODE",
      "owner": "module2",
      "field": "cabinets[2].cabinet_code",
      "message": "No decomposition rule exists for cabinet code SB362435"
    }
  ]
}
```

### 8f. What Orchestrator Must Not Do

The Orchestrator must not:

- edit Module 2 decomposition rules directly
- override panel dimensions
- override edge banding decisions
- force a blocked package into Module 3
- treat AI suggestions as production-ready panel data
- let Module 1 or Module 3 mutate Module 2's generated package

If a package is wrong, the Orchestrator should request a new Module 2 run with a new input version
or assign a blocker to the correct owner.

---

## 9. Explicitly Out Of Scope For Module 2

Module 2 does not own:

- QR code label design
- QR code / barcode print template
- scan page UI
- shop-floor status tracking
- hardware rules
- hinge rules
- slide rules
- shelf-pin rules
- pull-out / basket rules
- hardware SKU selection
- hardware hole placement
- assembly steps
- special hardware installation guide
- packaging photos
- shipping scan
- delivery confirmation

Module 2 may generate stable `cabinet_id` and `panel_id` values. Turning those IDs into QR code
labels, printed tags, and scan workflows belongs to Module 3.

---

## 10. Hardware Boundary

Hardware rules belong to Module 3.

However, some hardware can affect panel dimensions or cabinet structure. Examples:

- pull-out baskets requiring special clearance
- drawer slides changing drawer-box width
- special hinges changing door or side-panel preparation
- built-in appliances changing internal cabinet structure

V1 rule:

- If hardware affects panel dimensions and the structural parameters are already confirmed,
  Module 2 may use those parameters as plain input.
- If those parameters are missing, Module 2 must reject or block automatic decomposition.
- Module 2 should not infer hardware rules by itself.

So the clean rule is:

> Hardware rules are Module 3. Hardware-derived structural parameters must be resolved before
> Module 2 can generate final panel data.

---

## 11. Suggested V1 Build Order For Module 2

1. Define the `ApprovedCabinetOrderPackage` input contract.
2. Define the `ProductionEngineeringPackage` output contract.
3. Define the standalone API contract.
4. Build the production gate.
5. Build a minimal standard cabinet library.
6. Support a small set of cabinet types first:
   - base cabinet
   - wall cabinet
   - tall cabinet
7. Implement material and thickness rules.
8. Implement edge banding rules.
9. Generate panel BOM.
10. Generate grouped cut list.
11. Generate basic production work order data with cabinet IDs and panel IDs.
12. Add blocker output for unsupported cabinets, missing dimensions, missing material, or
    hardware-dependent structures.

Recommended V1 stance:

- Prioritize correctness over optimization.
- Start with deterministic rules for a small set of standard cabinets.
- Produce clear blockers instead of guessing.
- Keep QR labels and shop-floor UI out of this module.

---

## 12. Open Decisions

Need to confirm before implementation:

- Standard cabinet library source: Excel, JSON, database table, or admin UI.
- Unit convention: inches internally, unless the factory chooses another standard.
- Which cabinet types are in V1.
- Whether door panels are produced by this module or only referenced.
- Whether drawer boxes are decomposed by Module 2 or handled later with assembly/hardware.
- Cutting plan depth:
  - cut list only
  - basic sheet grouping
  - simple layout
  - optimized nesting
- Exact material names, thicknesses, and sheet sizes.
- Edge banding rule table format.
- API auth / tenancy model, if each module is deployed as a separate service.
- Whether Module 2 stores generated packages or only returns them to a shared orchestrator.

---

## 13. Current Confirmed Decisions

- Three people will build three major modules.
- A Master Orchestrator Agent should control project state, gates, blocker assignment, and module handoff.
- Module 2 should be a deterministic Production Engineering Engine, not a free-form autonomous agent.
- Orchestrator controls Module 2 through API commands, statuses, idempotency, and blockers.
- Module 2 is no longer intake-only.
- Module 2 should expose API boundaries for Module 1 input and Module 3 output.
- Module 2 owns standard cabinet library.
- Module 2 owns edge banding rules.
- Module 2 owns cabinet decomposition into panels.
- Module 2 owns panel BOM and cutting-plan data.
- Module 2 does **not** own QR code label design.
- Module 2 does **not** own hardware rules.
- Hardware rules, QR labels, scan pages, assembly, packaging, and shipping belong to Module 3.
- 后端部署：**Railway**（托管 FastAPI 服务）。详见 §16。

---

## 14. Module 2 V1 MVP Design (Architecture)

> 初始设计，目标是**最小可跑通 (MVP)**：先把「收订单 → 过闸门 → 拆板 → 出 BOM/封边/裁切 →
> 落库 → 按 work_order_id 读回」跑通。复杂度后延，只保留零成本扩展接缝。

### 14.1 已确认实现决策
- 技术栈：**Python + FastAPI + Pydantic v2**。
- 部署：**独立 HTTP 服务** (standalone)。
- 包持久化：**数据库**；MVP 用 **SQLite**（零运维，后续换 Postgres 只改连接串）。
- 规则存储：**YAML 文件 + Pydantic 校验**（规则即数据，改规则不改代码；后续可迁 DB / admin UI）。

### 14.2 MVP 目录结构（扁平、够用）

```
module2/
  app/
    main.py            # FastAPI app + 两个路由 (POST / GET)
    config.py          # DB 路径、units=inches、contract_version
    schemas.py         # Pydantic: ApprovedCabinetOrderPackage / ProductionEngineeringPackage / Blocker
    gate.py            # validate_gate(order) -> list[Blocker]  (§5 闸门规则)
    rules.py           # 读 YAML 规则 + 查表 (标准柜体 / 拆解 / 材料 / 封边)
    engine.py          # 纯函数: 拆板 + 材料 + 封边 + 裁切分组
    ids.py             # cabinet_id / panel_id / work_order_id 生成
    store.py           # SQLite 持久化 + 幂等
    rules_data/
      cabinets.yaml    # base/wall/tall 标准柜体, 内含拆解/材料/封边 (先放最小集)
  tests/
    test_gate.py
    test_engine.py     # 金样本: 柜体 -> 期望板件 BOM
    test_idempotency.py
  requirements.txt
```

### 14.3 V1 只做两个 API
- `POST /api/module2/production-packages`（创建，读 `Idempotency-Key` 头）。
- `GET /api/module2/production-packages/{work_order_id}`（Module 3 拉完整包）。
- 响应统一含：`ok / status / order_id / work_order_id / contract_version / input_fingerprint / blockers`。

### 14.4 主流程
1. **闸门** `gate.validate_gate`：stage!=final / 三项 approval / 未关闭确认项 / 缺尺寸·数量·材料·finish /
   不支持柜体码 → 返回 `gate_failed` + blockers。
2. **幂等** `store`：key=`module2:{order_id}:{cabinet_list_version}`，命中返回既有 `work_order_id`，不重算。
3. **逐柜体 × quantity** 展开，分配 `cabinet_id`；`rules.py` 查标准柜体+拆解规则，缺则
   `blocker(owner=module2)` → `engineering_blocked`。
4. **`engine.py`**（纯函数）：按柜体尺寸+厚度算各板件尺寸 → 解析材料/厚度 → 解析封边 →
   按 `material+thickness+finish+sheet_size` 分组成 cut list。
5. 组装 `ProductionEngineeringPackage`，落库，返回 `engineering_ready`。

### 14.5 V1 范围（先小）
- 柜体类型：`base` / `wall` / `tall`，其余 blocker。
- 单位：inches。门板：仅引用不生产。抽屉盒：延后。
- 裁切：分组 cut list，**不做 nesting**。

### 14.6 为后续扩展预留的「零成本接缝」（现在不建，只是别堵死）
- **业务逻辑与路由分离**：`gate.py` / `engine.py` 纯函数、不依赖 FastAPI → 以后可直接被
  Tool Calling / 编排器当工具调用，无需重写。
- **规则即数据 (YAML)**：以后可迁 DB / admin UI。
- **Pydantic 模型 = 契约**：以后用 `model_json_schema()` 生成 Anthropic tool 定义几乎免费。
- **engine 纯确定性、不含 AI**：以后 AI / RAG 只在外层做「建议/检索」（不支持柜体码的建议、
  制造备注等），结果只进 `blocker.suggestions[]` 或带标记的 note，**永不**写生产字段（呼应 §8f）。

### 14.7 明确后延（不在 MVP）
六边形分层 / Ports & Adapters、AI/RAG 层、能力注册表、Postgres、DB 规则与 admin UI、
`/panels` `/cut-list` `/edge-banding` `/status` `/retry` `/cancel`、nesting 优化。

### 14.8 落地顺序
1. `schemas.py` → 2. `gate.py` → 3. `rules_data/cabinets.yaml` + `rules.py` →
4. `engine.py` → 5. `store.py` (SQLite+幂等) → 6. `main.py` 接通两路由 → 7. tests + 跑通端到端。

### 14.9 验证方式
- `tests/test_engine.py`：`B302435` 等已知柜体 → 断言期望板件 BOM（尺寸/数量/材料/封边）。
- `tests/test_gate.py`：每条闸门规则一条失败用例，断言 blocker 的 `code/owner`。
- `tests/test_idempotency.py`：同 key 二次创建返回同一 `work_order_id`。
- **端到端**：起服务 → `POST` approved 订单 → 期望 `engineering_ready` → `GET {work_order_id}` 断言内容；
  再 `POST` 未审核订单 → 期望 `gate_failed`。

---

## 15. Implementation Status

> 记录实际落地进度，区分「已建基础设施」与「待建业务」。

### 15.1 已完成：项目脚手架（仅基础设施，无业务）
项目根目录 = `/Users/abcabinet/Desktop/module-2`（`ai_ctx.md` 与 `module-2-api-contract.md` 在根目录）。已创建并通过语法校验：

| 文件 | 作用 |
|---|---|
| `pyproject.toml` | 依赖(fastapi/uvicorn/pydantic/pydantic-settings/sqlalchemy/pyyaml) + dev(pytest/httpx/ruff) + ruff/pytest 配置 |
| `Dockerfile` / `docker-compose.yml` | 镜像 + 本地编排(含 `--reload`,预留 Postgres 块) |
| `.env.example` / `.gitignore` / `.dockerignore` | 环境模板与忽略规则 |
| `app/config.py` | 环境变量读取(pydantic-settings,单例 `settings`) |
| `app/db.py` | DB 连接(SQLAlchemy 2.0)、`Base`、`init_db()`、`get_db()` |
| `app/responses.py` | 统一响应 `ApiResponse`(ok/status/contract_version/data/blockers) + `success()`/`failure()` + `Blocker` |
| `app/errors.py` | 统一错误处理 `AppError` + 校验/兜底异常 → 统一响应 |
| `app/main.py` | FastAPI 入口,接通以上;仅 `/` 与 `/health` meta 路由 |
| `app/rules_data/` `tests/test_health.py` | 规则目录占位 + 冒烟测试 |

启动:`uvicorn app.main:app --reload`;验证:`curl /health`、`/docs`、`pytest`。

注:脚手架在 §14.2 的扁平结构上**多加了** `config.py / db.py / errors.py / responses.py` 作为基础封装层
(原 §14.2 只列业务文件)。业务文件 `schemas.py / gate.py / rules.py / engine.py / ids.py / store.py` 尚未创建。

### 15.2 ✅ Phase A 已完成（确定性核心,2026-06-15）
全部业务文件已建并通过 `ruff` + `pytest`（19 passed),uvicorn 实跑端到端通过:

| 文件 | 作用 |
|---|---|
| `app/schemas.py` | 输入 `ApprovedCabinetOrderPackage`(inch)+ 输出 `ProductionEngineeringPackage`(mm)+ 枚举;`PanelBOM` 含 `cut_length/cut_width` |
| `app/gate.py` | `validate_gate(order)->list[Blocker]` 纯函数(§5 闸门:stage/approval×3/未关闭确认项/空柜表/缺字段/尺寸·数量非正) |
| `app/rules_data/cabinets.yaml` + `app/rules.py` | 标准柜体库(base/wall/tall + code 前缀→type + 默认层板数),Pydantic 加载 |
| `app/ids.py` | `work_order_id`(由 idem key 哈希,天然幂等)/ `cabinet_instance_id` / `panel_id`(P0001)/ `input_fingerprint` |
| `app/engine.py` | 纯确定性拆板(§17.3 七类板件公式, mm)+ 按 quantity 展开实例 + 不支持柜型→`engineering_blocked` blocker + Phase A 分组 cut list |
| `app/store.py` | ORM `ProductionPackage`(work_order_id PK / idem key unique / package_json)+ get/save;已接入 `init_db` |
| `app/service.py` | 编排 gate→幂等→engine→store,产出统一 `ApiResponse` |
| `app/routes.py` + `app/main.py` | `POST /api/module2/production-packages`(读 `Idempotency-Key` 头)+ `GET .../{work_order_id}` |
| `tests/` | `test_gate`(每条闸门一例)/ `test_engine`(B302435 等金样本断言 mm 尺寸/封边)/ `test_e2e`(POST→GET / gate_failed / 幂等 / 404);`conftest.py` 用临时 SQLite |

注:本地已建 `.venv` 并装 deps(原脚手架未装,仅语法校验过)。运行:`.venv/bin/python -m pytest -q`。

### 15.3 待办：Phase B（裁切排版,需 board_config.json）
T0/T1/T2 板材系统 + 扫边/锯缝 + `stack_efficiency` 堆叠 nesting + cut-plan 输出(替换当前 Phase A 分组 cut list)。
另:§17.4 待澄清项(输出 BOM 单位 mm vs inch 待用户确认 / board_config 全字段 / 层板数量来源)。

---

## 17. Confirmed Build Decisions (2026-06-15, round 2)

> 用户在「下一步开发」讨论中拍板,**覆盖/细化** §12 Open Decisions 与 §14.5 MVP 范围。

### 17.1 门板 / 抽屉盒
- **都只引用不生产**(确认 §14.5)。schemas 不含门板/抽屉盒板件字段,engine 不算其尺寸。

### 17.2 裁切方案 —— 重大范围扩张
- **不再是** §14.5 的「简单分组 cut list, 不做 nesting」。
- 改为完整裁切排版规格:**内部单位 mm**(输入仍 inches, `INCHES_TO_MM=25.4`),
  7 类板件确定性公式,T0/T1/T2 板材系统,扫边/锯缝,`stack_efficiency` 堆叠裁切算法。
- 流程:所有进来的订单合并 → 按柜体总体计算 → 拆柜体 → 列板件 → 排版裁切。

### 17.3 裁切与拆板规则规格(权威, 来自用户)
**全局常量:** 输入 inch / 内部 mm / 精度 0.1mm(`r1()`); `t=18`(板厚)、`g=3`(背板通槽/侧)、
活动层板前缩 `20`、拉条深 `101.6`(4″)、封边厚 `eb=1`、wall 竖向缩 `vr=2`(其余柜型 0)。

**三柜型:** wall(顶+底,无拉条) / base(仅底,2 拉条,无顶) / tall(顶+底,无拉条)。

**拆板公式**(W/D/H 为外部 mm):
| 部件 | 数量 | 成品 Length | 成品 Width | cut_length × cut_width | 封边 |
|---|---|---|---|---|---|
| 侧板 Side | 2 | H | D | (H-vr) × (D-eb) | 前沿 |
| 顶板 Top(wall/tall) | 1 | W-2t | D-t | (W-2t) × (D-t-eb) | 前沿 |
| 底板 Bottom(全部) | 1 | W-2t | D-t | (W-2t) × (D-t-eb) | 前沿 |
| 背板 Back(全部) | 1 | H | W-2t+2g | (H-vr) × (W-2t+2g) | 无 |
| 拉条 Stretcher(base) | 2 | W-2t | 101.6 | (W-2t) × 101.6 | 无 |
| 活动层板 Adj Shelf | n | W-2t | D-t-20 | (W-2t-2eb) × (D-t-20-2eb) | 四边 |
| 固定层板 Fixed Shelf | n | W-2t | D-t | (W-2t) × (D-t-eb) | 前沿 |
- 结构:侧板包最外层;顶/底夹两侧间(W-2t);背板嵌两侧 3mm 槽(W-2t+2g);顶/底深 D-t。
- 轴:Length/Height 沿 2438.4mm 长轴, Width 沿 1219.2mm 短轴。
- 成品尺寸→BOM/对账;cut 尺寸(扣封边)→实际裁切。Qty 展开为独立柜体, `part_id` 形如 `P0001`。

**板材系统:** T0 整张 1219.2×2438.4;T1 条料(标准宽 窄264.8/宽569.6);T2 最终零件。
裁切参数(`board_config.json`):trim=5mm/边、saw_kerf=5mm;
回收阈值 wide569.6/narrow264.8/rail_min200;常见回收宽 264.8/285.8/303.8/569.6/590.6/608.6/762/838.2;
封边后回收宽映射(`EDGE_BANDED_RECOVERY_WIDTHS`)如 304.8→303.8、609.6→608.6。
**扫边:** 所有 H=2438.4 库存板首刀扫 5mm(高向单边一次);常规两端各 5mm→可用长 2428.4;
零件高 > `HEIGHT_TRIM_THRESHOLD`(2428.4,如 96″ 板)则该 strip 独占且跳短边扫边(usable=2438.4,`skip_trim`);
宽向不扫;已回收料不再扫。

**裁切方案 stack_efficiency:** 优先可重复堆叠裁切而非纯利用率;标准化/旋转零件构建可重复 strip 图案,
最大堆叠 4(`MAX_STACK`);分阶段:先从 T0 撕标准宽 strip,再把标准 strip 与匹配 T1 库存并入堆叠池长向裁切;
T0 模式忽略 T1,标准宽 strip 优先服务当前订单;拉条优先从整长回收料切;输出机器友好 stack 元数据。

### 17.4 待澄清(开工裁切层前确认)
- **输出板件 BOM 单位**:契约示例为 inches, 但新规则成品尺寸为 mm —— 暂定 **mm**(以制造规格为准),需用户确认。
- `board_config.json` 完整字段(回收逻辑细节、`EDGE_BANDED_RECOVERY_WIDTHS` 全表)。
- 活动/固定层板数量来源(标准柜体库 or 订单输入)。

### 17.5 修订后落地顺序(分两阶段)
- **Phase A(确定性核心, 全部已明确)**: schemas → gate → constants/rules(柜型+常量+公式) →
  engine(拆板,纯函数, mm) → 金样本测试(B302435 等 → 期望板件尺寸/封边) → store(SQLite+幂等) → 两路由 → 端到端。
- **Phase B(裁切排版, 待 board_config.json)**: T0/T1/T2 + 扫边 + stack_efficiency nesting + cut-plan 输出。

---

## 16. Deployment（后端方案：Railway）

> 决策（2026-06-15）：**后端 = Railway**。理由：Module 2 是常驻 Python FastAPI 服务、需跑自定义确定性
> 业务逻辑,必须有「计算托管」。Supabase / Insforge 是 BaaS(主要是托管 DB/Auth),跑不了常驻 FastAPI
> (Supabase 函数仅 Deno/TS),故只能当 DB 而非 app 宿主。

- **App 宿主 → Railway**：直接部署现成 `Dockerfile`;健康检查用已有的 `GET /health`。
- **数据库**：
  - MVP 阶段 SQLite 即可(本地/单实例)。
  - 上 Railway 后切 **Railway 托管 Postgres**(同平台最省心),仅改 `.env` 的 `DATABASE_URL`
    为 `postgresql+psycopg://...`,并给 `pyproject.toml` 加 `psycopg[binary]` 依赖;`app/db.py` 无需改。
  - 若整个三模块要共享一套带 Auth 的库,可改用 Supabase Postgres,同样只换 `DATABASE_URL`。
- **环境变量**：在 Railway 配置 `DATABASE_URL`、`ENVIRONMENT=production`、`DEBUG=false`、`CORS_ORIGINS`
  (对应 `app/config.py` 的 `Settings`)。
- 注意:`data/`(SQLite 文件)已 gitignore;Railway 上若仍用 SQLite,容器重启数据会丢,生产务必用 Postgres。
