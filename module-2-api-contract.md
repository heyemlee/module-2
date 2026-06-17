# Module 2 API Contract

> Audience: Module 1 developer, Module 2 developer, Module 3 developer, and integration owner.
> Purpose: define how Module 1 sends approved cabinet-level orders to Module 2, and how Module 3
> reads Module 2's production engineering output.

---

## 1. Module 2 Purpose

Module 2 receives an approved cabinet-level order from Module 1 and turns it into panel-level
production engineering data.

In one sentence:

> Module 1 decides which cabinets the customer ordered. Module 2 decides how those cabinets become
> panels and cutting data. Module 3 decides how the production data is executed in the shop floor.

Module 2 owns:

- production gate validation
- standard cabinet library
- cabinet decomposition rules
- material rules needed for panel production
- edge banding rules
- panel BOM
- cut list
- cutting-plan data
- production work order base data
- cabinet IDs and panel IDs

Module 2 does not own:

- QR code label design
- QR / barcode print templates
- scan page UI
- hardware rules
- hinge / slide / shelf-pin / pull-out rules
- hardware hole placement
- assembly steps
- packaging photos
- shipping scan
- delivery confirmation

---

## 2. Ownership Boundary

| Area | Owner |
|---|---|
| Customer requirement | Module 1 |
| Round 1 showroom flow | Module 1 |
| Round 2 site measurement | Module 1 |
| Detailed layout | Module 1 |
| Final cabinet list | Module 1 |
| Customer / sales / designer approval | Module 1 |
| Standard cabinet library | Module 2 |
| Cabinet-to-panel decomposition | Module 2 |
| Material and thickness rules | Module 2 |
| Edge banding rules | Module 2 |
| Panel BOM | Module 2 |
| Cut list / cutting plan | Module 2 |
| QR label design | Module 3 |
| Scan pages | Module 3 |
| Hardware rules | Module 3 |
| Assembly workflow | Module 3 |
| Packaging / shipping workflow | Module 3 |

Hardware note:

If hardware affects panel dimensions, Module 2 needs the final structural parameters before it can
generate production data. Module 2 should not infer hardware rules by itself. Missing
hardware-derived structural parameters must become blockers.

---

## 3. API Summary

Module 1 creates a production engineering package:

```http
POST /api/module2/production-packages
```

Module 3 reads a production engineering package:

```http
GET /api/module2/production-packages/{work_order_id}
```

Optional read endpoints:

```http
GET /api/module2/production-packages/{work_order_id}/panels
GET /api/module2/production-packages/{work_order_id}/cut-list
GET /api/module2/production-packages/{work_order_id}/edge-banding
```

Recommended flow:

1. Module 1 sends an approved cabinet-level order to Module 2.
2. Orchestrator calls Module 2 with an idempotency key.
3. Module 2 validates the production gate.
4. Module 2 generates panel BOM, edge banding data, and cut list.
5. Module 2 returns `work_order_id`, status, and blockers if any.
6. Orchestrator moves the project state only when Module 2 returns `engineering_ready`.
7. Module 3 reads the package by `work_order_id`.
8. Module 3 creates QR labels, scan pages, hardware workflow, assembly, packaging, and shipping.

---

## 4. Input From Module 1

Endpoint:

```http
POST /api/module2/production-packages
```

Request body type:

```ts
ApprovedCabinetOrderPackage
```

Minimum request example:

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

Required top-level fields:

| Field | Required | Owner | Notes |
|---|---:|---|---|
| `order_id` | yes | Module 1 | Source customer/order ID. |
| `project` | yes | Module 1 | Basic customer/project info. |
| `approval` | yes | Module 1 | Customer, sales, and designer approval status. |
| `source` | yes | Module 1 | Must prove this is final, not Round 1. |
| `cabinets` | yes | Module 1 | Final cabinet-level order lines. |
| `confirmation_required_items` | yes | Module 1 | Must be empty or fully closed. |

Required cabinet fields:

| Field | Required | Notes |
|---|---:|---|
| `cabinet_id` | yes | Stable ID from Module 1, or generated before sending. |
| `cabinet_code` | yes | Example: `B302435`, `W301236`. |
| `type` | yes | Example: `base`, `wall`, `tall`. |
| `width` | yes | Prefer inches in V1 unless the team agrees otherwise. |
| `depth` | yes | Prefer inches in V1. |
| `height` | yes | Prefer inches in V1. |
| `quantity` | yes | Positive integer. |
| `material` | yes | Material selected or approved for production. |
| `finish` | yes | Finish selected or approved for production. |

---

## 5. Production Gate Rules

Module 2 must reject the request if any gate rule fails.

Gate failures:

- `source.stage` is not `final`
- order is Round 1 / preliminary / sales-estimate-only / not-for-production
- `approval.customer_confirmed` is not true
- `approval.sales_confirmed` is not true
- `approval.designer_approved` is not true
- open confirmation-required items exist
- cabinet list is empty
- cabinet code is missing
- cabinet dimensions are missing or invalid
- quantity is missing or invalid
- material or finish is missing
- cabinet code is unsupported by Module 2 standard cabinet library
- hardware-dependent structure is missing confirmed structural parameters

Gate failure response:

```json
{
  "ok": false,
  "status": "gate_failed",
  "blockers": [
    {
      "code": "UNAPPROVED_ORDER",
      "owner": "module1",
      "field": "approval.designer_approved",
      "message": "designer_approved must be true"
    }
  ]
}
```

Blocker owner values:

| Owner | Meaning |
|---|---|
| `module1` | Module 1 must fix source order, layout, approval, or cabinet data. |
| `module2` | Module 2 lacks a rule, material definition, or standard cabinet mapping. |
| `module3` | Hardware-related structural parameters are needed before Module 2 can finish. |
| `integration` | Shared contract or orchestration issue. |

---

## 6. Success Response To Module 1

If Module 2 successfully creates the package:

```json
{
  "ok": true,
  "status": "production_package_created",
  "work_order_id": "WO-2026-001",
  "package_url": "/api/module2/production-packages/WO-2026-001"
}
```

Required response fields:

| Field | Meaning |
|---|---|
| `ok` | `true` when package creation succeeds. |
| `status` | `engineering_ready` or `production_package_created`, depending on implementation naming. |
| `work_order_id` | Stable ID used by Module 3 to read Module 2 output. |
| `package_url` | Read URL for the generated production engineering package. |
| `contract_version` | API contract version, e.g. `module2.v1`. |
| `input_fingerprint` | Fingerprint of the cabinet list / input version used to generate the package. |

---

## 7. Output For Module 3

Endpoint:

```http
GET /api/module2/production-packages/{work_order_id}
```

Response body type:

```ts
ProductionEngineeringPackage
```

Minimum response example:

```json
{
  "work_order_id": "WO-2026-001",
  "source_order_id": "ORD-2026-001",
  "status": "engineering_ready",
  "cabinets": [
    {
      "cabinet_id": "C001-1",
      "source_cabinet_id": "C001",
      "cabinet_code": "B302435",
      "type": "base",
      "width": 30,
      "depth": 24,
      "height": 34.5,
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
      "quantity": 1,
      "material": "plywood",
      "finish": "white-shaker",
      "grain_direction": "vertical",
      "edge_banding": ["front"],
      "production_note": ""
    }
  ],
  "cut_list": [
    {
      "group_id": "CUT-GROUP-001",
      "material": "plywood",
      "thickness": 0.75,
      "finish": "white-shaker",
      "sheet_size": "48x96",
      "panels": ["P001", "P002", "P003"]
    }
  ],
  "edge_banding_list": [
    {
      "panel_id": "P001",
      "edges": ["front"],
      "banding": "white",
      "thickness": 1
    }
  ],
  "blockers": []
}
```

Module 3 can rely on:

- `work_order_id`
- `cabinet_id`
- `panel_id`
- cabinet-to-panel relationship
- panel dimensions
- material
- finish
- thickness
- cut list grouping
- edge banding list
- production notes

Module 3 must not expect Module 2 to provide:

- QR label image
- QR label layout
- QR print template
- scan page route
- hardware SKU list
- hinge / slide / pull-out rules
- hardware hole positions
- assembly steps
- packaging checklist
- shipping status

---

## 8. Data Status Values

Recommended package status values:

| Status | Meaning |
|---|---|
| `gate_failed` | Module 2 rejected the input. |
| `engineering_ready` | Module 2 generated usable panel-level production data. |
| `engineering_blocked` | Module 2 accepted the order but cannot finish due to missing rule or parameter. |

Recommended package creation status values:

| Status | Meaning |
|---|---|
| `production_package_created` | Package generated successfully. |
| `gate_failed` | Package not generated due to source input problems. |

---

## 9. Orchestrator Control Contract

The Master Orchestrator Agent controls Module 2 through API calls, state transitions, idempotency,
and blocker handling. It must not directly edit Module 2's internal standard cabinet library,
decomposition rules, material rules, edge banding rules, or cutting algorithm.

Module 2 controls its own production engineering logic. Orchestrator controls when Module 2 runs
and whether the result can move downstream.

### 9a. Recommended Orchestrator State Machine

| State | Meaning |
|---|---|
| `module2_not_started` | Module 1 has not handed off a final cabinet order yet. |
| `module2_requested` | Orchestrator has requested Module 2 package creation. |
| `module2_gate_failed` | Module 2 rejected the input before production engineering. |
| `module2_engineering_running` | Module 2 accepted the request and is generating panel/cutting data. |
| `module2_engineering_blocked` | Module 2 cannot finish because a rule, parameter, or upstream field is missing. |
| `module2_engineering_ready` | Module 2 generated a valid Production Engineering Package. |
| `module3_ready` | Orchestrator has approved Module 2 output for Module 3 consumption. |

Only the Orchestrator should update project-level state. Module 2 returns statuses and blockers.

### 9b. Idempotency

The Orchestrator should include an idempotency key when creating a Module 2 package.

Recommended header:

```http
Idempotency-Key: module2:{order_id}:{cabinet_list_version}
```

Rules:

- Same `order_id` + same `cabinet_list_version` should return the same existing `work_order_id`.
- New `cabinet_list_version` should create a new production engineering package version.
- Module 2 should not silently overwrite a previous ready package.

### 9c. Required Module 2 Response Fields For Orchestrator

Every Module 2 create/status response should include:

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

### 9d. What Orchestrator Must Not Do

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

## 10. Versioning

Every API request and response should include a contract version once implementation starts.

Recommended field:

```json
{
  "contract_version": "module2.v1"
}
```

Versioning rule:

- Add fields in a backward-compatible way when possible.
- Do not rename or remove fields without creating a new contract version.
- Module 1 and Module 3 should validate against the same contract version.

---

## 11. Open Questions

These decisions should be resolved before full implementation:

- Will Module 2 be deployed as a separate service or as routes inside the same app?
- What auth or shared secret is required between modules?
- Are dimensions always inches?
- What is the first source for the standard cabinet library: Excel, JSON, database, or admin UI?
- Which cabinet types are required in V1?
- Are door panels produced by Module 2 or only referenced?
- Are drawer boxes decomposed by Module 2 or handled later?
- Is V1 cut planning only a cut list, or does it include basic sheet layout?
- Where are generated packages stored?
- Who owns retries and idempotency if Module 1 sends the same order twice?
- Which exact Module 2 status names should the Orchestrator standardize on?

---

## 12. V1 Recommendation

For V1, keep the contract narrow and reliable:

- Implement only `POST /api/module2/production-packages`.
- Implement only `GET /api/module2/production-packages/{work_order_id}`.
- Support `Idempotency-Key` for package creation.
- Support a small set of standard cabinet types first: base, wall, tall.
- Return blockers instead of guessing.
- Keep QR labels and hardware rules out of Module 2.
- Make Module 3 pull completed engineering packages by `work_order_id`.
