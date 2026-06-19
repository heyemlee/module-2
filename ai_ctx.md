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

### 15.3 ✅ Phase B 已完成（裁切排版,2026-06-17）
裁切排版落地,`ruff` + `pytest` 全过(26 passed = 19 + 7 新),HTTP 端到端实跑通过。

| 文件 | 作用 |
|---|---|
| `app/rules_data/board_config.yaml` + `app/boards.py` | 板材/机床参数(rules-as-data, **YAML** 非 json, 与 cabinets.yaml 统一);`BoardConfig` 暴露 `usable_width/length`(扣两端扫边) |
| `app/cutting.py` | 纯函数 nesting:`build_cutting_plan(panels, order_id)` → 按 material+thickness+finish 分组 → 两阶段 guillotine(纵切成 strip / 横切成件, FFD)→ kerf+trim 计入 → 余料记录 → `pattern_id` 标识可堆叠相同 strip;另含 `render_text()` 工人可读裁切单 |
| `app/schemas.py` | 新增 `CutPiece/CutStrip/CutSheet/CuttingPlanGroup/CuttingPlan`;`ProductionEngineeringPackage` 加 `cutting_plan` 字段(additive, 保留旧 `cut_list` 分组) |
| `app/engine.py` | `engineer()` 内调用 `build_cutting_plan` 并挂到包上 |
| `app/routes.py` + `app/service.py` | 新增 `GET /production-packages/{wid}/cutting-plan` → `text/plain` 工人裁切单 |
| `tests/test_cutting.py` | 7 例:全部板件被排一次/strip 与 sheet 不溢出(guillotine 不变量)/余料阈值/相同柜体 pattern 复用/多材料分组/空板件空方案/文本渲染 |

**本对话锁定的 Phase B 决策(覆盖 §17.4):**
1. 裁切方案**给工人看**(text 裁切单 + JSON 结构),不输出机床排版文件。
2. **多订单合并排版**(揉单):`build_cutting_plan` 纯函数吃一个扁平 panel 列表,当前对单订单内全部柜体揉单;跨订单 batch 只需传更多 panel(零成本接缝)。
3. **不旋转零件**(grain 固定:Length 沿 2438.4 长轴 / Width 沿 1219.2 短轴);效率靠同宽零件堆叠,不靠旋转。
4. **板材**:Phase B V1 只用整张 T0(无 T1 预撕条料库存);trim=5/边、saw_kerf=5。
5. **回收料**:记录余料(≥`recovery_min_width` 264.8 标 留用/废料),但**回收料作为库存复用**延后;`EDGE_BANDED_RECOVERY_WIDTHS` **删除不做**(回收料是生料,封边在裁切之后)。
6. **标签**(Module 3 范畴):板件平叠 → 标签贴板件**侧边**,即切即贴;18mm 厚需小标签/窄条码。

### 15.4 ✅ 跨订单 Batch 已完成（揉单, 2026-06-17）
多张订单合并成一份共享裁切方案,`ruff` + `pytest` 全过(33 passed = 26 + 7 新)。

| 文件 | 作用 |
|---|---|
| `app/cutting.py` | 重构:分组下沉到 piece 层(`CutPiece` 加 material/thickness/finish)→ `_pieces_from_panels` / `_plan_from_pieces` 拆出共享 nesting 核心;新增 `build_cutting_plan_multi(sources)` 吃 `[(order_id, panels)]` 合并排;`render_text` 跨订单时每件标 `〔order_id / cabinet_id〕` |
| `app/ids.py` | `batch_id(work_order_ids)` 由排序后 wid 集合哈希(集合无序 → 幂等) |
| `app/store.py` | ORM `ProductionBatch`(batch_id PK / work_order_ids JSON / plan_json);get/save/load |
| `app/service.py` | `create_cutting_batch`(幂等 → 逐 wid 取包,缺失/非 ready 出 blocker owner=integration → `batch_failed`;否则 `build_cutting_plan_multi` 落库 `batch_ready`)+ get/text |
| `app/routes.py` | `POST /cutting-batches` + `GET /cutting-batches/{batch_id}` + `GET .../{batch_id}/cutting-plan`(text) |
| `tests/test_batch.py` | 7 例:合并/合并不劣于单独/集合幂等/未知 wid 失败/空 batch/text 标订单/未知 batch 404 |

实测:2 订单(base×2 + wall×2)单独排 6 张 → 合并排 5 张,利用率 63.5%。
注:跨订单时 panel_id/cabinet_id 会跨包重复(各包自带 P0001/C1-1),靠 piece 上的 `order_id` 标签消歧分拣。

### 15.5 ✅ 回收料库存复用已完成（2026-06-17）
回收余料持久化为库存,后续 batch 优先复用再开新整板。`ruff` + `pytest` 全过(43 passed = 38 + 5 新)。

| 文件 | 作用 |
|---|---|
| `app/cutting.py` | nesting 支持回收料 bin:`OffcutBin`(可用回收料)/`NewOffcut`(新产出)/`PlanResult`(plan + 消耗/产出);`_pack_sheets` 先填回收料(按宽升序, 长度受限)再开新整板,**新整板**剩余宽带 ≥264.8 → 产出回收料(回收料 bin 不再二次入池, 避免碎片链);`build_cutting_plan_with_stock(sources, available)`;`render_text` 标【回收料 OC-xxx】+ 汇总「新整板 N 张 · 回收料 M 块」 |
| `app/schemas.py` | `CutSheet` 加 `from_offcut_id/usable_length`;`CuttingPlanGroup`/`CuttingPlan` 加 `fresh_sheets/offcut_sheets`;新增 `OffcutStockItem`;`CuttingBatchRequest` 加 `use_offcut_stock`(默认 True) |
| `app/store.py` | ORM `OffcutStock`(offcut_id PK / material 索引 / status available\|consumed);`available_offcuts`/`available_offcut_bins`/`deposit_offcuts`/`consume_offcuts` |
| `app/ids.py` 复用 | 回收料 id = `{batch_id}-OC{seq:03d}`(批内稳定) |
| `app/service.py` | `create_cutting_batch` 接 `use_offcut_stock`:取可用回收料 → `build_cutting_plan_with_stock` → 标消耗 + 入库新产出 → 落库;幂等命中**不**二次动库存;新增 `list_offcut_stock` |
| `app/routes.py` | `GET /api/module2/offcut-stock`(可用回收料清单);batch 请求透传 `use_offcut_stock` |
| `tests/test_offcut.py` | 5 例(每例独立材料隔离):复用消耗/新整板余料入库/幂等不二次消耗/`use_offcut_stock=false` 不动库存/复用降低新整板数 |

实测:Batch1(wall 单柜)3 新整板 → 入库 2 块回收料(324.8/639.6 × 2428.4);Batch2 同款复用 1 块 → 新整板降到 2 张(省 1 张)。
**V1 范围**:仅回收**整长宽带**(full-length width band, 直接当部分整板用);条尾短余料只在裁切单标 留用/废料,不入复用池。

### 15.6 ✅ 拆板规则数据化已完成（2026-06-17）
把 §17.3 拆板**公式从代码搬进 YAML**,加柜型 = 改配置不改代码。base/wall/tall 结果**逐字不变**(5 个金样本测试照过)。`ruff` + `pytest` 全过(42 passed, 含 4 新 formula 测试)。

| 文件 | 作用 |
|---|---|
| `app/formula.py` | 安全算术求值器(AST 白名单:数字 / 命名变量 / `+ - * /` / 括号;`**`、函数调用、属性访问、未知变量一律 `FormulaError`),杜绝规则文件执行任意代码 |
| `app/rules_data/cabinets.yaml` | 重构为 `constants`(t/g/eb/...)+ `part_catalog`(7 类部件几何公式, 变量 W/D/H/vr + 常量)+ `cabinets`(每型 = 选哪些部件 + 数量 + vr);底部含 `sink_base` 注释模板 |
| `app/rules.py` | 新模型 `PartGeometry`/`TypePart`/`CabinetRule`(parts 列表)+ `geometry_for`;去掉旧 has_top/stretchers/default_* 标志 |
| `app/engine.py` | `decompose` 改为遍历 `rule.parts` × `part_catalog` 公式(`formula.evaluate`),零柜型特判;数量 `int` 或订单字段名(adjustable_shelves/fixed_shelves, 缺则部件 `default`);厚度/封边厚从 `constants` 取 |
| `tests/test_formula.py` | 4 例:算术等价 Python / 一元+括号 / 未知变量报错 / 拒绝代码执行与 `**` |

**加新柜型的方式**:在 `cabinets.yaml` 的 `cabinets:` 加一型,列出部件+数量+vr;若需新部件形状,先在 `part_catalog:` 加其公式。无需改代码。
**仍缺**:每种新柜型(sink base / drawer base / corner...)的**真实拆板公式**需用户提供(§17.3 那种部件表),不可瞎编。模板已留 `can_auto_decompose: false`,确认前自动 block。

### 15.7 ✅ 真实柜型目录映射已完成（2026-06-17）
对接 `kabi-console` 的 `config/standard-cabinets.json`(1230 柜码 / ~50 系列)。**关键发现**:kabi-console 的裁切尺寸规则(背板嵌入/层板缩进/抽屉/门缝)在 `production-rules.ts` 里**全 gate 住 (null)**——正是 module-2 缺的;它唯一确认的侧板公式 module-2 已有且一致。所以**没有现成新公式可搬**,只搬了「柜型目录 + 系列分类」。`ruff` + `pytest` 全过(50 passed, 含 8 新 type 测试)。

矩形系列复用现有 base/wall/tall 箱体(§17.3 公式不变):
- **base**:FDB / DRB / DB / CDB / TCFDB / TCDRB / SPB / V / VF / VFB(抽屉门只引用不生产, 不加箱体板;vanity 即 d≈21 的 base)
- **wall**:W / WBF / WSL ; **tall**:TP
- **sink_base**(新, = base 去掉底板):FDRSB / DRSB / VSB —— **待用户确认箱体部件, 暂 `can_auto_decompose: false` 自动 block**
- **blocked_families**(转角/烤箱/开放层架/电器):BCB LSCB WBC WAC WDC CSB / SO DO / WOS OSB ESB WES / RFW WM MB

| 文件 | 作用 |
|---|---|
| `app/rules_data/cabinets.yaml` | 加 `code_families`(柜码前缀→carcass)+ `blocked_families`(前缀→拦截原因)+ `sink_base` 类型(disabled) |
| `app/rules.py` | `resolve_carcass(code, fallback_type)`:**最长前缀**跨两表匹配(WBF→wall 但 WBC→blocked),无匹配回落 `type` 字段 |
| `app/engine.py` | 改为按 `resolve_carcass` 选箱体(而非直接信 `type`);blocked 系列出带原因的 blocker;未确认类型(sink_base)出"not yet confirmed" |
| `tests/test_types.py` | 8 例:真实码映射 / 最长前缀 / blocked 带原因 / 回落 type / 抽屉柜按 base 拆 / TP 按 tall / 转角 block / 水槽柜 pending |

### 15.8 ⚠️ 重大发现:kabi 构造系统 ≠ module-2 §17.3（2026-06-17）
按"根据文档来"查 kabi-console 文档(`文档库/03-物料清单与报价/C26061-Salice物料清单`、`标准库/待确认 §D`)后确认:

- **水槽柜真实构造**(C26061 FDRSB 备注):背板**挖洞**(下留3″/左右4–6″/上留8″)+ 前上方加 **6″ 封板**挡水盆 + **踢脚4″** + 无底板。**不是**"base 减底板",远比提案复杂 → `sink_base` 保持 disabled。
- **两套构造系统不一致**:
  | 维度 | module-2 §17.3 | kabi 真实订单 |
  |---|---|---|
  | 踢脚 | 无(侧板=整高H) | 4″,减净高 |
  | 背板 | 整块嵌3mm槽 | 缩进30mm≠2t;水槽柜挖洞 |
  | 板厚 | 统一18 | 15+18 混用 |
- kabi `待确认 §D` 明确:背板嵌入/层板缩进/抽屉/门缝/顶vs拉档/板厚**全部 ⏳ 待确认,"引擎不能臆造"**。
- **结论**:kabi 只能提供「柜型目录 + 系列分类」(已用),**无法提供确认的裁切构造公式**;module-2 现仍基于 §17.3。**需用户拍板:module-2 服务的工厂用 §17.3 还是 kabi 那套(toe-kick/挖洞背板)?** 二者裁切尺寸不同,不能混。

### 15.9b ✅ 可行性护栏已完成（2026-06-17,纯逻辑正确性）
堵住引擎吐出"物理上切不出的方案"的两个洞(纯逻辑,不依赖待确认值):
- `app/engine.py` `_infeasible_reason(specs, usable_width, sheet_length)`:逐 spec 查 ① 任一 length/width/cut_* ≤ 0(柜太小,如 W-2t 为负)② cut_width > 板材净宽(超宽板,原会静默溢出排版)③ cut_length > 板长。命中 → `CABINET_NOT_MANUFACTURABLE`(owner=module2)blocker 并跳过该柜(不进 BOM/裁切),与"不支持柜型"同一处理路径。
- `tests/test_feasibility.py`(4 例):1″ 柜 block 不出负板件 / 50″ 柜背板超宽 block 不溢出 / 正常柜照常 ready 且全部 cut 尺寸 >0 / 单个坏柜只 block 自己、好柜照出。
- 测试 59 passed。

### 15.9 待办(后续)
- **裁切构造系统归一**(§15.8):确认 §17.3 vs kabi 哪套权威;若是 kabi 那套,§17.3 公式需按 toe-kick/挖洞背板/混合板厚重做。
- **代码已知缺口(审《构造规则确认-详细版.html》时发现)**:① `board_config.yaml` 只有**一种整板尺寸**,但 C26224 真实数据有 2440×1220 与 **2740×1220** 两种 → 需支持**每材料不同板材规格**(裁切按材料选板)。② `decompose` 每柜**单一材料**,但背板常是另一种薄板 → 需 part_catalog 支持**每部件材料/厚度**(裁切已按 material+thickness 分组,口子是开的)。③ grain 硬编码"length",未建模"哪些板可旋转"。④ 底板/固定层板**是否入槽(dado)**未建模(现平接)。⑤ 柜型系列映射(DRB/CDB/vanity→base、转角/电器→block)需公司签字确认。
- 水槽柜:需以确认的构造给出 §17.3 式部件表(挖洞背板/6″封板/踢脚)才能启用。
- base 系列分组(DRB/CDB/vanity 当 base)需 sanity-check。
- 裁切 B3(throughput book 单元优化 / 3 阶段 + 真优化器);材料 finish 字符串归一(分组防碎);条尾短余料入复用池;对接 Module 1/3(可选读端点未实现)。

### 15.10 ✅ 真实订单深度测试 + 数字前缀码修复（2026-06-18）
用两份真实工厂物料表 `C26147-K`(54 件) + `C26046-1`(10 件) 全面深度测试,提取 `柜子列表 Cabinets List`
跑 resolve_carcass + 全引擎 E2E。**测试方法记录**见用户记忆 `module2-realorder-test-method`。

**测试结论(按件数):** 直接拆板 17% · 数字前缀需修 10% · 水槽柜待确认 4% · 电器柜拦截 3% · **非箱体平板件 64%**。
矩形箱体拆板**全部正确**(含 12″超浅 / 21″浴室柜 / 93″超高 TP(side cut 2362mm 落在 96″板内) / 抽屉柜按箱体拆)。

**已修(有文档依据,不碰待确认构造):**
1. **数字前缀码识别** `app/rules.py resolve_carcass`:真实码带前导抽屉数(`3DRB`/`1DRSB`),最长前缀从开头锚定
   → 匹配不到 `DRB`/`DRSB`。修复:原码匹配不到任何家族时,剥前导数字重试(`lstrip("0-9")`)。依据=《构造规则确认》§F
   "只产箱体不产抽屉盒",抽屉数与箱体无关。**只救原本无匹配的码,已匹配的零影响**。
2. **输出 type 回显 bug** `app/engine.py:280`:`CabinetRecord.type` 原样回显输入 `cab.type`,真实码解析出
   不同箱体时(3DRB→base)记录仍写输入值 → 误导下游。改为 `type=carcass_type`(报实际拆的箱体)。
   新增 4 测试(test_types.py),**101 passed**,ruff 干净。E2E:全部传 type=base 时真实码仍正确驱动
   (W→wall/TP→tall/3DRB→base/1DRSB→sink_base待确认/RFW·SO→拦截)。

**未修(需公司/工艺确认,引擎不臆造)——应补进《待确认清单.html》:**
- ✅ **非箱体平板件 → 已改为过滤(见 §15.11)**,不再废整单。原"建单板直通裁切路径"的提议**作废**(过度设计):
  按用户拍板,非柜体直接过滤掉,不在 Module 2 生产。详见用户记忆 `non-box-flat-parts-gap`(已更新)。
- 🟡 **裁切按 finish 碎裂**:同一箱体料(White Birch plywood 18mm)被门板色 finish 拆成 3 组(9+6+6 张),
  利用率掉到 58-72%。`cutting.py:570` 分组 key=(material,thickness,**finish**),`engine.py:260` 把 cab.finish
  灌到每块箱体板。箱体板不该按门板色分组。属 §15.9 "材料 finish 归一" 待办,真实数据坐实。详见记忆 `cutting-finish-fragmentation`。
  (注:部分由"工厂表柜体材质列填了门板色码 MO SD6\*6"的数据不一致放大。)
- 🟡 **W/TP 前缀误吞配件**(潜伏):WP(墙板)/WF(墙填充)被"W"判成 wall、TP2596(面板)判成 tall;现靠 depth=0 先 gate 掉。
- 🟡 **幂等健壮性边界**(本次顺带发现):idem-key 与 work_order_id 派生输入不一致时(同 order_id+version 配不同 idem key)
  → PK 冲突 500,而非优雅幂等返回。文档化用法(idem=order_id:version)下不触发,但建议加防御。

### 15.11 ✅ 入口过滤非柜体 + 柜体↔板件对应校验（2026-06-18）
对接 kabi 的"裁切=柔单"语义(所有标准吊/地/高柜揉一起拆板叠切)。用户拍板:**两边都过滤**(kabi 与 Module 2
各自独立过滤),非柜体不在 Module 2 生产;柜体拆完板件要**对应回柜体,数量不对就报错**。保持简单,不动前端。

| 文件 | 改动 |
|---|---|
| `app/intake.py`(新) | `is_cabinet`/`partition_cabinets`:镜像 kabi `isCarcass`——有门/抽/层板任一 >0 即柜体;**无部件且 depth≤0** = 填充条/装饰板/踢脚/线条 → 过滤。depth>0(部件数未知)按柜体留,交给 gate/护栏 兜底(保住现有金样本) |
| `app/schemas.py` | `CabinetInput` 加 `door_qty/drawer_qty`(默认0,对齐工厂表 门数量/抽屉数量,供过滤判定);`ProductionEngineeringPackage` 加 `filtered_non_cabinets`(被过滤项,**报出不静默丢**) |
| `app/service.py` | gate 前先 `partition_cabinets`;全是填充条 → `NO_STANDARD_CABINETS`;否则只把柜体喂 gate+engine,过滤项挂包上 |
| `app/engine.py` | `_verify_correspondence(cabinets,panels,cutting_plan)`:① 每柜必产板件(否则 `CABINET_NO_PANELS`)② 每板件按 quantity 恰好裁一次且挂回有效柜体(否则 `PANEL_COUNT_MISMATCH`/`PANEL_CABINET_UNLINKED`)。在 build_cutting_plan 后调用,不一致即 block |
| `tests/test_intake.py`(新,7例) | 过滤判定/分区保序/混单只产柜体且报过滤项/全填充条 block/对应守恒(裁切件数==板件数) |
| `contracts/*.schema.json` | 重新导出(输入+输出契约变更) |

**108 passed**(101+7),ruff 干净。**真实订单 E2E**:C26147-K 36 行混单 → 过滤 16 非柜体、拆 16 柜体(77 板件)、对应校验✅;
C26046-1 9 行 → 过滤 6、拆 2 柜体(8 板件)、对应✅。**之前整单 gate_failed,现在柜体照拆**,剩余 blocker 只是真该挡的
(RFW/SO 电器、1DRSB 水槽柜待确认)。注:过滤判定用 depth≤0 兜底是因 Module 2 历史输入不带 door/drawer 计数;
kabi 侧用纯 `isCarcass`(其 BOM 有解析后的部件数),两边语义一致、对真实数据结果相同。

### 15.12 ✅ 工厂生产流程图对照 + 裁切按箱体色分组（2026-06-19）
用户给了**权威生产流程图**(ORDER→GN柜号,三线 DOOR/BOX/DRAWER → 封边 → 六面钻 → 组装 → QC → 出货)。
这是之前一堆"待确认"封边政策的权威答案。全面对照 Module 2(只做 **BOX 箱体** 拆板+裁切):

**流程图定死的封边政策(权威):**
| 线 | 材料 | 封边 | 封边条 | 机器 |
|---|---|---|---|---|
| 门板/开放柜面板 | 18mm MDF/PBC | 四边全封·门板色 | ½mm·Hot Air | #3 |
| **箱体 BOX** | **18mm 胶合板** | **侧板前封1边(S)·背板不封** | **1mm·Hot Melt** | #1浅/#2深 |
| 抽屉 | 15mm 胶合板 | 四边全封·箱体色 | 1mm·Hot Melt | #1/#2 |
- **核心规则**:颜色决定一切(板材色→封边条色/机器全自动);**箱体封边=箱体色**,门板色**只在"配面"特殊情况**(冰箱吊柜外露端板 L×2箱体色·S×1门板色)→ **必须工单手工标注,引擎不能自动推导**。
- 这条**证明上一轮"三聚氰胺→全封"的材料覆盖推断是错的**(被用户否、本图坐实):真规则是按三线分,且配面是手工项。

**对照结论:** 侧板前封✅、背板不封✅、箱体 1mm(eb=1)✅、box=18mm✅ —— Module 2 全对上。**唯一实锤 bug**:裁切按门板色 finish 碎裂(与"箱体封边=箱体色"矛盾)。

**已修(#1, 有图做依据):** 箱体板件 `finish=""`(engine.py),按 **箱体料 material+thickness** 分组;门板 finish 移到 `CabinetRecord.finish`(供 Module 3 做门)。`tests/test_engine` 加回归(同箱体料不同门板色→1 组)。**109 passed**,ruff 干净。实测 C26147-K:White Birch plywood 18mm 从 **3 组碎裂(21 张)→ 1 组(19 张,利用率 73.3%)**。契约重导。

**未修(需工厂构造数 / 你拍板 scope,引擎不臆造)——应补进《待确认清单》:**
- **配面封边透传**:已由现有 `attributes`/`CabinetRecord.finish` 透传口子覆盖,引擎不算,工单标注原样带过去。无需改。
- ✅ **L/S 封边标注(已修, 2026-06-19)**:用户拍板"**按板子实际长度判断**"——长的那对边=L、短的=S,与部件名无关(图里侧板标 S 是简化,以板长为准→侧板前沿876mm=**L**)。`schemas.ls_notation(edges,length,width)` + `PanelBOM.edge_banding_ls` computed_field(front/back 沿 length、left/right 沿 width,取较长对为 L)。输出/契约自动带。实测:侧/顶/底前封=`L×1`、活动层板四边=`L×2 + S×2`、背板=``。test_engine 加回归。**110 passed**。
- **"3DRB 中 DD=底板"**:图点名 DD=底板(非门板)、短边可能配色封边;但 C26224 实测 DD 尺寸(376×911.4)不像横底板、更像中竖隔板,**矛盾未解**→ Module 2 现按普通 base 拆,可能漏中竖隔板/某板,**需工厂给该部件公式**才能补。
- **抽屉盒自制**(15mm·45°拼角):图显示抽屉**自制**,但 §17.1 现"只引用不生产"→ **真 scope 缺口,需你拍板**;且 45°拼角构造未给,不能臆造。
- **备库存裁切**(地柜侧板 24"D 批量备货,21/18/12 从 24 裁):裁切优化,后置。
- **图未解决的**:背板嵌入量/层板缩进/精确 cut 扣减 —— 图给封边政策不给毫米扣减,仍靠 §17.3/Salice。

### 15.13 ✅ L/S 封边标注 + Demo UI 收尾（2026-06-19, 自动执行）
**L/S 封边标注**: 用户拍板"按板子实际长度判断"(长边对=L/短边对=S, 与部件名无关; 图里侧板标 S 是简化)。
`schemas.ls_notation(edges,length,width)` + `PanelBOM.edge_banding_ls` computed_field(front/back 沿 length、
left/right 沿 width, 取较长对为 L)。输出/契约自动带。实测: 侧/顶/底前封=`L×1`、活动层板四边=`L×2 + S×2`、背板=``。

**Demo UI 三处收尾**(app/static/demo.html, 保持简单不改后端逻辑):
1. 结果区显示 `filtered_non_cabinets`("已过滤 N 个非柜体…TK9、WP1360、BF0335") —— 落实"不静默丢"。
2. 板件 BOM 的封边列改显 **L/S 标注**(L×1 / L×2+S×2 / 不封)。
3. 加"真实订单(含填充条)"示例(FDB42T/3DRB36T/W3636T/TP247284 + TK9/WP1360/BF0335 填充条)—— 演示里能直接看到过滤生效。

**110 passed**, ruff 干净, 契约重导。**浏览器 QA 通过**(真实订单示例 → 4 柜体、过滤 3 填充条并显示、BOM 出 L/S)。
**双真实订单 E2E**: C26147-K 过滤16/拆16/77板件/对应✅/White Birch 由 3 组合并为 1 组/L/S 全有; C26046-1 过滤6/拆2/对应✅。
**《待确认清单.html》已更新**: 加"2026-06-19 流程图对照"节, 列已解决(封边政策/L/S/箱体色分组/踢脚过滤)+ 仍待确认 3 条
(DD=底板部件公式、抽屉盒自制 scope+45°拼角、备库存裁切)。

**本轮(流程图)全部收口。剩下 3 条都卡在工厂/老板输入, 引擎不臆造:** ① DD=底板公式 ② 抽屉盒 scope ③ 备库存裁切(后置)。

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

### 17.4 待澄清 —— ✅ 已在 2026-06-17 对话中全部解决(见 §15.3)
- ~~输出板件 BOM 单位~~ → 确认 **mm**(制造规格为准)。
- ~~`board_config` 完整字段 / `EDGE_BANDED_RECOVERY_WIDTHS` 全表~~ → 字段见 `board_config.yaml`;封边回收映射**删除不做**(回收料是生料)。
- ~~活动/固定层板数量来源~~ → 订单可传 `CabinetInput.adjustable_shelves/fixed_shelves`,缺省回落标准柜体库默认值。

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

---

## 18. 裁切方案行业标准对标 + 思路更新（2026-06-17 调研）

> 用户问"现在的裁切方案是不是大工厂的标准方案"。查阅 Cut Rite(Homag,行业第一)、OptiCut、
> CutPlan、Wikipedia(cutting-stock / guillotine / nesting)后记录如下。**结论:框架合规、锯得出来,
> 但停在"摆放零件"层,未到"工厂级优化方案"。**

### 18.1 大厂标准做法（记录）
1. **输出 = 「图案(pattern) × 重复次数」,不是一张张板。** 优化器算出一小组**不同裁切图案**,每个图案重复切 N 张;核心是**让不同图案尽量少、每图案重复尽量多**。
2. **按「书 book」堆叠裁切。** 相同图案的板叠成一摞(book height 常 2–8 张)一次锯穿 —— 这正是 §17.2 的"堆叠裁切",是行业 **throughput / speed 模式**(非臆想)。
3. **目标可切换:省料 vs 省时。** Cut Rite 原文 "optimizes for **speed or waste**"。省料=板数最少;省时=图案最少、堆叠最多、锯切次数少。大厂让你选,并真对选定目标优化。
4. **3 阶段 guillotine + head cut(首刀)**,比 2 阶段省料明显;另有应力消除刀(stress-relief)。
5. **真优化器**(列生成 / 元启发),非贪心;配 grain 锁(增废 5–15%)、kerf 累计、余料入库复用、destacking、标签。

来源:homag.com/Cut Rite;wooddesigner.org/OptiCut;cutplan.ai 完整指南;Wikipedia cutting-stock / guillotine-cutting / nesting。

### 18.2 module-2 vs 标准（对标）
| 维度 | 大厂标准 | module-2 现状 | 判断 |
|---|---|---|---|
| 锯切模型 | guillotine | guillotine **2 阶段** | ✅ 对,少一阶段 |
| kerf / 扫边 | 每刀累计 | 已计 | ✅ |
| grain 锁 | 锁、认 5–15% 废 | 锁 | ✅ |
| 余料复用 | 入库填充 | 已做(宽带) | ✅ |
| 合批 | 多单一起算 | 已做 | ✅ |
| **输出形态** | **图案 × 重复 × book** | **逐张独立排版** | ❌ 非标准件 |
| **堆叠 book** | 相同图案叠摞切 | 仅贴 `pattern_id`,不组织成摞 | ❌ |
| **优化目标** | 省料/省时 可选 + 真优化 | 贪心最小板数,不可选、非优化 | ❌ |
| **算法** | 3 阶段 + 列生成/元启发 | FFD 贪心 | ❌ 利用率偏低(混柜 ~58%) |

### 18.3 思路更新 —— 裁切层目标重定（覆盖 §17.2 的实现取向）
**把"裁切"从「摆放零件」升级为「生成可堆叠的重复图案、对选定目标做优化」。** 三个改造方向:

1. **输出结构改为 pattern-based。** 当前产物 = 每张 sheet 的 strip 列表;目标产物 = `CuttingPattern[]`,每个含{布局(strips/pieces 相对位置)、repeat_count(切几张)、book_stack(≤MAX_STACK 一次叠几张)};相同布局合并为同一 pattern。→ 重写 `cutting.py` 的输出层:`_pack_sheets` 产生的 sheet 先**按布局签名归并成 pattern**,再算 repeat 与 book 分组(`pattern_id` 已有,扩成一等公民)。
2. **优化目标显式化、可切换。** 加 `objective: waste | throughput`。waste=现行(板数最少);throughput=**最大化图案重复 / 最小化不同图案数 / 最大化 book 堆叠**(对应 §17.2"堆叠优先")。先让二者都"显式且正确",再谈算法升级。
3. **算法升级(后置,分步)。** 先把 2 阶段 FFD 的**输出**做成 pattern×book(结构正确、利用率不变);再考虑 3 阶段 guillotine + head cut + 更强优化器(列生成/元启发)提利用率。**结构优先于利用率**——先产出工厂能按摞上锯的标准件,再抠利用率。

### 18.4 修订后的裁切路线（替换原 Phase B 取向）
- **B1 ✅ 已完成(2026-06-17,结构)**:输出层重构为 **pattern × repeat × book**。
  | 文件 | 改动 |
  |---|---|
  | `app/schemas.py` | 新增 `PatternStrip`/`CuttingPattern`(pattern_id/repeat_count/books/sheet_nos/layout);`CutSheet` 加 `pattern_id`;`CuttingPlanGroup` 加 `patterns`/`distinct_patterns`;移除 strip 级 `pattern_id` |
  | `app/cutting.py` | `_build_patterns`:按"用量尺寸 + 每条(rip宽+横切长多重集)"签名归并相同布局的整板成图案;`_split_books`(按 `max_stack` 拆 books, 如 5→[4,1]);strip 内**按长度降序**排件(保证一摞各张同位置同长,book 裁切才成立);`render_text` 改为「图案=共用布局 + 切N张 + 堆叠 + 逐张贴标」|
  | `tests/test_cutting.py` | 图案重复/book 求和≤max_stack/每张有 pattern_id;`_split_books` 直测;render 含"图案/堆叠" |
  测试 51 passed。
  **关键观察(暴露 B2 的必要性)**:5 个**完全相同**的墙柜 → FFD 排出 **5 个不同图案**(板数最少 6 张,但堆叠性差)。说明现在的 packer 只最小化板数、**不为重复图案分组**——`distinct_patterns` 现在把这个差距量化出来了。
- **B2 ✅ 已完成(2026-06-17,目标开关)**:加 `objective: waste | throughput`。
  | 文件 | 改动 |
  |---|---|
  | `app/cutting.py` | `_plan_from_pieces` 按 objective 分支;throughput 走 `_throughput_sheets`:按柜实例(order_id+cabinet_id)聚合 → 按 spec 签名(各件 length×width 多重集)分组 → 每 spec 排**一个代表** → `_clone_layout` 把布局复制给每个实例(按尺寸槽位填各自 panel_id);throughput 忽略回收料(异形破坏堆叠) |
  | `app/schemas.py` | `CuttingPlan.objective`;`CuttingBatchRequest.objective: Literal[waste,throughput]` |
  | `app/ids.py` | `batch_id` 纳入 objective + use_offcut_stock(不同选项→不同 batch,幂等不串) |
  | `app/service.py`/`routes.py` | 透传 objective;`_batch_data` 出 objective + distinct_patterns |
  | `tests/test_objective.py` | throughput 图案更少/板数≥/图案按实例重复/两目标都守恒/端点接受 objective |
  测试 55 passed。**实测(5 个相同墙柜)**:waste=6板/5图案/57.3%;throughput=**10板/2图案/34.4%,每图案×5 叠[4,1]**。权衡兑现。
- **B3-1 ✅ 部分完成(2026-06-17):strip→整板的 FFD 换成子集和 DP**。`app/cutting.py` `_max_fill`(0/1 背包子集和,0.1mm 整数单位,父指针回溯)+ 重写 `_pack_sheets`:每张板/回收料用 DP 填到最大宽(`rip+kerf` vs `usable_width+kerf`,精确处理锯缝与整宽单条)。单板最优填充,替掉"首个放得下"的贪心。测试 61 passed(`_max_fill` 直测 `[7,6,6]→{6,6}=12` 证明胜过首次适配)。
  **⚠️ 诚实结论(实测)**:真实混批 24 条 strip,老 FFD=10 张、新 DP=10 张 —— **总板数一样**。DP 把前几张填到余 1mm,但余料挤到末尾,总数不变。原因:**strip→整板这层(1D bin packing)FFD 本就接近最优,瓶颈不在这。真正的结构性浪费在 strip 构建(2 阶段:每条只装一个宽、占满整长)。**
- **B3-2 ✅ 已完成(2026-06-17):2 阶段 → 3 阶段 guillotine**(裁切这条线最大重构,61 测试全过)。
  | 文件 | 改动 |
  |---|---|
  | `app/schemas.py` | 新增 `CutBlock`(length + pieces);`CutStrip.pieces` → `CutStrip.blocks`。结构变三层:strip(纵切宽)→ block(横切同长)→ piece(块内再纵切, 宽度子集和填满 rip) |
  | `app/cutting.py` | 删 `_build_strips`/`_pack_sheets`;新 `_pack_region(W,L,pieces,allow_skip)`:贪心选宽开 strip → 每 strip 用 block 填长 → block 内 `_max_fill`(保留的子集和 DP)按宽填满。`_pack_into_sheets`(回收料先、再新整板);`_to_group`/`_build_patterns`/`render_text`/`_clone_layout` 全改三层;pattern 签名含块内宽多重集(保证 book 各张物理一致) |
  | `tests` | `_all_pieces`/`_placed_ids` 走 blocks;`test_no_strip_or_sheet_overflows` 改 3 阶段不变量(块内同长、宽和 ≤ rip) |
  **实测利用率大涨**:单柜 30.6%→**45.9%**(3→2张);3 base 混批→**55.1%**(5张);base+wall 混批→**68.9%**。背板条现在能再塞侧板/底板/层板(一条 strip 含多种不同长度的块)。
  **注**:B3-1 的 `_pack_sheets`(strip→板的子集和 DP)已被 3 阶段取代;其 `_max_fill` 保留下来做"块内宽度填充"。算法仍是**贪心(选宽/选长)+ DP(块内宽)**,非全局最优(全局最优需列生成),但已把 Gilmore-Gomory 3 阶段的核心收益兑现。
- **B3-3(后置, 选做)**:列生成/分支定价做全局最优;throughput 的"单柜单元"→"N 实例 book 单元"平衡堆叠与利用率。前提仍是 §15.8 构造系统确认。
- B1/B2 是**纯排版结构逻辑,不依赖 §15.8 构造决定**,已独立完成。

---

## 19. 三模块共享契约 + 输入契约完整性（2026-06-17）

> 审 Module 1 输出对接 Module 2 输入后,把 `ApprovedCabinetOrderPackage` 确立为**三模块共享契约**,
> 并补齐"对整条流水线绝对适用"所缺的字段。63 测试全过。

### 19.1 契约导出（机器可读,防漂移）
- `app/service.get_contract()` + `GET /api/module2/contract`:返回输入/输出契约的 JSON Schema(由 Pydantic `model_json_schema()` 生成,**永不与闸门实际校验漂移**)。
- `scripts/export_contracts.py` → 写 `contracts/*.schema.json`(可提交,Module 1/3 引用生成类型/校验)。

### 19.2 输入契约完整性改动(让"一个形状随 stage 成熟"成立)
| 改动 | 原因 |
|---|---|
| `CabinetInput.material/finish` → `str \| null`(默认 null) | Round 1 未选材也能产出同一形状;闸门在 final 才要求非空 |
| `ApprovedCabinetOrderPackage.units: str="inches"` + 闸门校验 | 单位显式声明,传错(mm)→ `UNSUPPORTED_UNITS` 拦截,不靠"约定" |
| `CabinetInput.attributes: dict` + `CabinetRecord.attributes`(透传到输出) | 门/抽屉数·铰链 L/R·安装位·外露面等 **M1 有、M3 要、M2 不算** 的字段:塞 `attributes`,M2 原样带到输出 → 新需求不破契约(面向未来) |
| `quantity` 默认 1 | M1 一柜一条少写一个字段 |

### 19.3 Module 1 → Module 2 对接缺口(待 Module 1 侧补)
- **边界分歧**:M1 的 ai_ctx 认为"Round 2 实测设计=Module 2";M2 的 ai_ctx 认为"Round 2 测量=Module 1"。**"粗估→实测最终订单"这一步现无人认领,需拍板**。
- M1 现产 `Round1Snapshot`(salesEstimateOnly/notForProduction/canEnterProduction:false),by design 进不了 M2 闸门 —— 正确,因为缺"成熟到 final"的步骤。
- M1 侧要补:`toModule2Package()` 导出适配器,把现有字段映射成共享形状(kind→type 小写、actualHeight→height、生成 cabinet_id、material/finish 留 null、approval 留 false、stage=round1),门/抽屉/铰链等塞 `attributes`。

---

## 20. Salice 物料表对账 + §17.3 修正（2026-06-17）

> 用户提供真实工厂表 `C26061-5 List of items-Salice`。`标准柜信息` 页的**面积公式**(data_only=False 读出)
> 是权威构造模型。比对后**修正 §17.3 两处错**并落代码;63 测试全过。

### 20.1 表能答的 / 不能答的
- **能答(已落代码)**:① 拉条深 = **3″**(顶板=`W×3`,原 §17.3 写 4″/101.6 → 改 76.2);② 底/高柜背板高 = **H−4.5″**(背板=门=`W×(H−4.5)`,toe-kick+rail;原写整高 H → 加每型 `tkr`,base/tall=114.3、wall=0);③ 材料分部位(`板材选项`页:箱体 18mm、抽屉 15mm、背板 MDF 1/4″);④ 门/抽屉/层板/铰链数量;⑤ 封边长度公式;⑥ 部分板材规格(Cleaf 2800×2065、9′、8′)。
- **不能答(仍 ⏳,同 kabi 待确认 §D)**:精确 cut 尺寸(表是**名义面积**用原始 W/H/D,不扣板厚);背板宽入槽/层板前缩/dado;**水槽柜真实构造**(面积公式把水槽柜当普通底柜、给了底板,真实无底+挖洞背板只在手写备注里)。

### 20.2 落地改动
- `cabinets.yaml`:`stretcher_depth` 101.6→**76.2**;`back` 公式 `H`→`H-tkr`、`cut H-vr`→`H-tkr-vr`;每型加 `tkr`(base/tall 114.3、wall 0)。
- `rules.py`:`CabinetRule.tkr`;`PartGeometry.thickness`(每部件板厚口子,None→constants.t)。
- `engine.py`:namespace 注入 `tkr`;`_part`/decompose 带 thickness,`engineer` 用 `spec["thickness"]`(背板等可后续按 MDF 1/4″ 设)。
- 验证:B302435 背板 876.3→**762.0**、拉条 101.6→**76.2**、侧板 876.3×609.6(整 H×D)对上 Salice;金样本测试已更新。

### 20.3 仍需工厂补(清单缩短)
精确 cut 扣减量(W−2t 那类)、背板入槽/层板前缩/dado、水槽柜特殊部件表。其余构造已由 Salice 表证实。

---

## 21. 每材料板材规格 + 剩余待补记录（2026-06-17）

### 21.1 已补（机制）
- `board_config.yaml` 加 `stock` 列表(`match` 子串→整张 width×length);`boards.py` `StockSheet` + `BoardConfig.for_material(material)`(model_copy 换 sheet 尺寸);`cutting.py` `_plan_from_pieces` 每组 `gcfg = cfg.for_material(material)`,按材料板规排版;`engine.py` 可行性护栏改用该材料板规(宽板可能能进大板)。65 测试全过。
- 已种确认值:**Cleaf-*-19mm = 2800×2065**;其余无 match 走默认 4×8(1219.2×2438.4)。

### 21.2 ⏳ 仍要工厂填的(记下)
1. **完整材料→整张尺寸表(确认文档 B#5)**:Lioher/面板料「9′」的宽未知;衣柜料「8′」;箱体 plywood 默认 4×8 待确认;其余材料。→ 拿到后往 `board_config.yaml` 的 `stock` 加行即可。
2. **trim/saw_kerf 是否随材料不同**:现全局 5/5;若某些板材不同,`StockSheet` 需加 trim/kerf 字段。

### 21.3 查文档后修正/确认的判断
- **每部件材料 ≠ 缺口**:C26061 订单表真实选材里背板=箱体料(18mm),MDF 1/4″ 只是罕见选项 → 现"每柜单材料"对常规订单正确;厚度口子(`PartGeometry.thickness`)已留,需 MDF 背板时再填。
- **grain 数据已在文档**:订单表每材料标纹路——木纹料(ABC-WG/Syn/Cleaf)竖纹锁定、素色料(SM-/HG-)无纹可旋转。**用它 = 给 3 阶段裁切加旋转**(对无纹材料放开旋转省料),是优化、较大改、后置;现全锁定=保守正确。

### 21.4 Module 2 自身逻辑缺口 —— 至此基本清零
拆板(数据化+Salice 校正)/ 裁切(3 阶段+图案 book+目标开关+回收料+按材料板规)/ 护栏 / 契约 全齐。剩下:① 工厂回填(B 节 7 项 + B#5 板规表)② 边界决定(谁产 final)③ 刻意后置(grain 旋转、列生成、基础设施、Module 1/3 对接)。

---

## 22. 测试体系 + 真实柜码回归网（2026-06-17）

> 拿真实柜码全面跑,而非只靠小金样本。**89 测试全过,跨 22 真实柜码 + 整厨订单未发现 bug。**

### 22.1 新增
- `tests/fixtures/catalog_sample.json`:**22 个真实柜码**(FDB/SPB/CDB/TCFDB/1DRB/V/W/WBF/TP + Cleaf板 + FDRSB/DRSB/BCB/LSCB/SO/DO/WOS/OSB/RFW/WM + 太小/太宽),每条标 ready/blocked + 原因。
- `tests/test_catalog.py`:参数化逐码断言 disposition(ready→守恒+尺寸为正;blocked→blocker code+owner+原因子串)。
- `tests/test_e2e.py::test_full_kitchen_order_end_to_end`:9 柜 2 材料整厨单走完整 API(下单→读包→裁切单→揉单),验证混材料用不同板规(4×8 与 2800×2065 同时出现)。
- `tests/test_stock.py`:per-material 板规;`tests/test_feasibility.py`、`test_formula.py`、`test_types.py`、`test_objective.py` 等。

### 22.2 测试体系现状（89 项)
闸门 / 拆板(Salice 校正) / 公式器(安全) / 柜型解析(最长前缀+回落) / 可行性护栏(负尺寸·超板) / 裁切(3阶段·图案book·目标·守恒·按材料板规) / 回收料库存 / 契约导出 / 端到端 / **真实柜码目录** / 整厨订单。

### 22.3 用法
**catalog fixtures = 回归网**:改 `cabinets.yaml`/`board_config.yaml`(加柜型/改构造/填板规)后跑 `pytest`,立刻知道有没有破坏既有柜型;`.venv/bin/python -m pytest -q`。

### 22.4 暂时闭环结论
Module 2 已暂时闭环:完整服务跑通(8 步 E2E)+ 89 测试 + 跨真实柜码无 bug。下一步在代码外:① 工厂回填(B 节 7 项 + B#5 板规表)② 边界(谁产 final)③ 后置(grain 旋转/列生成/Postgres·auth·部署/Module1·3 对接)。
