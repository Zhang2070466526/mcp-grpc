# 工具实现原理

每个 MCP 工具按底层通信方式分为 5 种实现类型：gRPC 远程调用、本地文件读取、subprocess 命令行、COM 对象、内存服务。本文逐一说明每种工具的协议交互、数据结构、校验流程、错误处理和设计决策。

---

## 一、gRPC 远程调用（14 个工具）

所有操作 EDI 工程和仿真器件的工具共享同一套 gRPC 通信模型。核心实现在 `servers/eda/grpc_client.py`（通信层）和 `servers/eda/simulation_components.py`（参数校验层）。

### 1.1 通信协议

EDI 服务通过 `proto/ecserver.proto` 定义了 `ExternalCall` 服务，当前协议版本 v2，16 种事件类型：

```proto
service ExternalCall {
  rpc PerformAction(Request) returns (Response) {}    // 提交任务
  rpc FetchEvent(FetchEventRequest) returns (stream Event) {}  // 流式拉取结果
}
```

核心设计是 **异步任务模型**：`PerformAction` 只负责受理任务（返回 `code=0` 表示已受理），最终结果通过 `FetchEvent` 的流式通道异步推送。

### 1.2 call_grpc() 统一入口

所有 gRPC 工具都调用同一个函数，唯一的区别是 `task_type` 枚举值和 `payload` 字典：

```python
def call_grpc(
    task_type: int,        # ecserver_pb2 枚举值（如 OPEN_PROJECT=1）
    payload: dict,         # 任务参数（project_path, instance_name 等）
    timeout_seconds: int,  # 总超时秒数
    max_timeout_seconds: int = 3600,
    task_id: str | None = None,
    client_uuid: str | None = None,
    on_event: Callable | None = None,  # 异步任务的增量回调
) -> dict:
```

#### 串行锁

EDA 操作必须串行化——同时打开工程又执行仿真会导致状态冲突。`_EDA_LOCK = threading.RLock()` 是有超时的可重入锁：

```python
acquired = _EDA_LOCK.acquire(timeout=timeout_seconds)
if not acquired:
    return _terminal_result(success=False, status="QUEUE_TIMEOUT", ...)
try:
    return _call_grpc_unlocked(...)
finally:
    _EDA_LOCK.release()
```

#### 调用顺序：先订阅后提交

EDI 服务要求 FetchEvent 必须在 PerformAction 之前建立，否则返回 "external handler not ready"。MCP 侧严格遵循：

```
1. stub.FetchEvent(client_uuid) → 建立流式订阅
2. stub.PerformAction(request)  → 提交任务
3. 消费事件流                   → 等待终态
```

第 1 步和第 2 步都受剩余的 `timeout_seconds` 约束。

#### 响应校验

`PerformAction` 返回后，MCP 对回显进行三重校验：

```python
if response.code != 0:
    return REJECTED       # EDI 未受理

if response.client_uuid != client_uuid:
    return PROTOCOL_MISMATCH  # client_uuid 不匹配

if response.task_id != task_id:
    return PROTOCOL_MISMATCH  # task_id 不匹配

if response.event_type not in (EVENT_TYPE_UNSPECIFIED, task_type):
    return PROTOCOL_MISMATCH  # event_type 不匹配
```

#### 消费事件流

三重筛选（`client_uuid + task_id + event_type` 全部匹配才处理）：

```python
for event in event_stream:
    if event.client_uuid != client_uuid:
        continue
    if event.task_id != task_id:
        continue
    if event.event_type != task_type:
        continue

    details, parse_error = _parse_payload_json(event.payload_json)

    # 增量收集 ads_output 日志（不 strip、不覆写）
    chunk = details.get("ads_output", "")
    if chunk:
        ads_output_chunks.append(chunk)  # 原样追加

    # 累积 details（后到的覆盖前面的同名字段）
    for key, value in details.items():
        if key != "ads_output":
            latest_details[key] = value

    # 触发异步回调
    if on_event:
        on_event({"phase": "EVENT", "status": status_name, ...})

    if event.status == RESULT_STATUS_SUCCESS:
        # payload 完整性校验：SUCCESS 的 JSON 必须可解析
        if parse_error:
            return PROTOCOL_MISMATCH
        return SUCCESS  # 终态

    if event.status == RESULT_STATUS_FAILED:
        return FAILED  # 终态

# 流结束但无终态
return STREAM_DISCONNECTED
```

#### 异常处理

| gRPC 错误码 | MCP 返回 |
|---|---|
| `DEADLINE_EXCEEDED` | `status: "TIMEOUT"`，保留已收日志 |
| 流建立后断连 | `status: "STREAM_DISCONNECTED"`，保留已收日志 |
| 流建立前断连 | `status: "GRPC_UNAVAILABLE"`（统一字典，不抛异常） |

#### 返回结构

```python
{
    "success": bool,         # 是否成功
    "completed": bool,       # 是否已到终态
    "status": str,           # 终态标识
    "message": str,          # 描述
    "project_path": str,     # 工程路径
    "result_path": str,      # 结果路径（如 RAW 文件）
    "ads_output": str,       # 增量拼接的完整仿真器日志
    "log_complete": bool,    # 日志是否完整接收
    "details": dict,         # 原始 payload 字段
}
```

### 1.3 仿真器件参数校验

`_prepare_parameters()` 是仿真器件工具共享的校验管线。它执行 11 步校验，任何一步失败都返回带 `error_code` 的结构化错误：

```
1. 类型检查         parameters 必须是 dict（拒绝 None/[]/"" ）
2. 空值检查         create 允许空字典；update 必须非空
3. 控件存在         检查 component_type 在 catalog 中
4. 参数名解析       先查固定参数 → 再匹配动态模式 Freq[{n}]/Order[{n}]
5. 权限检查         create_allowed / update_allowed
6. 值结构检查      每个参数值必须是 {"value": ..., "unit": ...}
7. value 存在       不能为 null、数组或对象
8. 值类型校验       number: 拒绝 NaN/Infinity；integer: 拒绝 1.5
9. 枚举校验         如 CalcS 只能 "yes"/"no"
10. 单位检查        required → 必须有 unit；forbidden → 不能有 unit
                    unit 必须是有效非空字符串且在允许列表中
11. 别名冲突        如 Freq + Freq[1] → 两者都映射到 Freq[1] → 报错
输出: wire_params   如 Freq → Freq[1]（公开名→线名转换）
```

**动态参数模式**：`Freq[{index}]` 和 `Order[{index}]` 通过正则匹配支持 1-32 组。用户可以使用快捷名 `Freq`（→ `Freq[1]`）或显式名 `Freq[2]`。两者同时出现时，第 11 步检测重复。

**权限模型**：每个参数显式声明 `create_allowed` 和 `update_allowed`（无隐式默认值）。`BandwidthForNoise` 为 `create_allowed: false, update_allowed: false`（EDI 内部参数，使用默认值）。

### 1.4 工程管理工具

| 工具 | EventType | payload 字段 | 说明 |
|---|---|---|---|
| `open_edi_project` | OPEN_PROJECT(1) | `project_path` | 已有工程窗口时复用 |
| `close_edi_project` | CLOSE_PROJECT(8) | `project_path`, `need_save` | 可选保存 |

### 1.5 仿真工具

#### 同步仿真

`simulate_project` 直接调用 `call_grpc(SIMULATE_PROJECT, ...)`，阻塞等待仿真完成。期间实时收集 `ads_output`。

#### 异步仿真

异步仿真通过内存任务注册表解耦提交和查询：

```
start_simulation_async()
  ├─ 创建 task 记录（task_id, client_uuid, status=QUEUED）
  ├─ 检查队列上限（最多 8 个，原子检查+插入）
  ├─ submit 到 ThreadPoolExecutor(max_workers=1)
  └─ 立即返回 task_id

后台线程 _run_sim_task():
  ├─ call_grpc(SIMULATE_PROJECT, on_event=_handle_sim_event)
  ├─ on_event 回调更新 _sim_tasks[task_id] 的 status/log_chunks/result_path
  └─ 最终: task["result"] = 完整结果, task["finished_at"] = 时间戳
```

任务生命周期：
```
QUEUED → ACCEPTED → RUNNING → SUCCEEDED / FAILED
                                   ↓
                            2 小时后自动清理（_prune_tasks）
```

**队列上限**：同一 `with _sim_lock` 临界区内完成"统计待处理任务数 → 判断是否超过 8 → 创建新任务"，保证原子性。超限返回 `SIMULATION_QUEUE_FULL`。

**线程安全**：`_sim_lock`（`threading.Lock`）保护 `_sim_tasks` 字典。`_get_task_snapshot()` 在锁内创建浅拷贝，避免并发修改。`_SIM_EXECUTOR(max_workers=1)` 确保同一时间只有一个 gRPC 调用在进行。

**任务快照隔离**：查询状态/结果时，`_get_task_snapshot()` 在锁内创建 `dict(task)` + `list(log_chunks)` 的浅拷贝，然后脱离锁返回。写入方只改原始字典，读取方只看快照。

#### 网络仿真

`simulate_netlist`：
1. MCP 校验 `netlist_path` 存在 → `call_grpc(SIMULATE_NETLIST, {"netlist_path": ...})`
2. EDI 服务：复制网表到临时目录 → 执行 ADS → 复制 `result.raw` 到原网表同级 `history/` → 清理临时目录
3. 返回 `result_path` 和完整 `ads_output`

`simulate_netlist_with_ads`：直接调用 ADS 仿真控制器（`CALL_SIMULATION_CONTROLLER`）。

### 1.6 仿真器件管理（协议 v3）

| 工具 | EventType | 关键实现 |
|---|---|---|
| `create_simulation_component` | CREATE(11) | **v3 不传 parameters**。使用 EDI 工厂默认值创建，创建后根据 `instance_name` 调用 `update_simulation_component` 设参 |
| `update_simulation_component` | UPDATE(15) | **三路类型推断**：显式 component_type > 磁盘查找 > `COMPONENT_TYPE_REQUIRED` 错误。显式类型与实际磁盘类型不一致返回 `COMPONENT_TYPE_MISMATCH` |
| `delete_simulation_component` | DELETE(12) | **不做本地预检查**。直接由 EDI 按 instance_name 执行。通用删除，不限器件类型 |
| `set_component_active_state` | SET_ACTIVE_STATE(14) | 状态规范化 `.strip().upper()`。确定性设置（非切换），重复调用具有幂等性 |
| `generate_schematic_from_netlist` | GENERATE(13) | **双重确认**：`clear_before_import=true` 必须同时 `confirm_clear=true`。`confirm_clear` 不进入 gRPC payload。默认追加到 main 原理图 |
| `replace_port_component` | REPLACE_PORT_COMPONENT(16) | payload: `project_path`, `target_instance_name`, `replacement_component_type`(TermG/P_nToneG), `parameters`。Chat 层需确认 |

**update 类型推断的完整流程**：

```python
explicit_type = component_type.strip() if component_type else ""
component, _ = _find_component_by_instance(project_path, instance_name)
actual_type = component.get("type", "") if component else ""

if actual_type:
    # 磁盘上找到了实例
    if explicit_type and explicit_type != actual_type:
        return COMPONENT_TYPE_MISMATCH  # 显式类型和实际类型冲突
    ct = actual_type  # 使用磁盘上的实际类型

elif explicit_type:
    # 磁盘上没有，但用户提供了类型（如 EDI 中新建但未保存）
    ct = explicit_type  # 信任用户提供的类型

else:
    # 既不在磁盘上，用户也没提供
    return COMPONENT_TYPE_REQUIRED  # 无法确定类型

# 无条件执行完整校验 + wire 转换
wire_params, error = _prepare_parameters(ct, parameters, op="update")
```

### 1.7 导出与模型

| 工具 | EventType | MCP 层校验 |
|---|---|---|
| `export_project_netlist` | VIEW_PROJECT_NETLIST(3) | 仅校验 `project_path` |
| `capture_schematic` | CAPTURE_SCHEMATIC(7) | 额外校验 `img_path` 扩展名（PNG/JPG/BMP/SVG）和路径 resolve |
| `replace_models_from_csv` | MODEL_REPLACE(6) | 额外校验 `csv_path` 存在且后缀 `.csv` |

---

## 二、本地文件读取（6 个工具）

这些工具不经过 gRPC，直接读取磁盘上的 `.epp` 工程文件。核心实现在 `servers/eda/config.py`。

### 2.1 .epp 工程格式

`.epp` 不是单个文件，而是一个目录：

```
ProjectName/
  ProjectName.epp          ← 标记文件（内容固定为 "EDI-PROJECT"）
  project/
    metadata.ep             ← S-expression 格式元数据
  schematics/
    schematics.ep           ← 原理图列表
    main/
      schematic.ep          ← main 原理图（S-expression 格式）
  netlist.log               ← ADS 网表
  history/
    result.raw              ← 仿真结果
```

### 2.2 S-expression 解析器

`parse_sexp(text)` 是递归下降解析器，处理 EDI 使用的 Lisp 风格格式：

```
(block
  (source "EDI")
  (component uuid-001
    (type "ResG")
    (name "R1")
    (component_uuid "model-123")
    (pin 1)
    (pin 2)
    (paramsinfo "{\"R\":{\"Value\":\"50\",\"CurrentUnit\":\"Ohm\"}}")
  )
)
```

解析器状态机：

```
pos=0
├─ 跳过空白
├─ '(' → 递归解析子表达式直到 ')' → 返回列表
├─ '"' → 读取引号字符串（处理 \", \n, \t 转义）→ 返回字符串
└─ 其他 → 读取裸词直到空白或括号 → 返回字符串
```

**关键安全措施**：`ProjectReader.read_schematic(name)` 拒绝 `..` 和路径分隔符：

```python
if ".." in name or "/" in name or "\\" in name:
    return None
```

### 2.3 paramsinfo 解析

原理图里的 `(paramsinfo "...")` 节点包含 JSON 格式的参数信息。存在两种结构：

- **普通参数**：`{"Value": "50", "CurrentUnit": "Ohm", "Tunable": "false"}`
- **Var 变量**：`{"Initial": "29", "Max": "", "Min": "", "Status": "Disable"}`

`parse_paramsinfo(raw)` 将这两种结构统一为小写 key 的字典：

```python
{
    "R": {
        "value": "50",          # 来自 Value 或 Initial
        "unit": "Ohm",          # 来自 CurrentUnit 或 DefaultUnit
        "default_unit": "Ohm",
        "tunable": False,
        "visible": True,
        "initial": "",
        "max": "", "min": "",
        "status": "",
    }
}
```

`parse_components(schematic_text)` 从 S-expression 提取所有 `(component ...)` 节点，并调用 `parse_paramsinfo` 解析参数信息。返回值直接包含已解析的 `paramsinfo` 字典——下游不应再次调用 `parse_paramsinfo`。

### 2.4 参数格式化

`_format_component_parameters(component_type, paramsinfo)` 将 `parse_components` 返回的已解析字典转换为面向用户的格式：

- 直接从 `paramsinfo["key"]["value"]` 读取，**不重复解析**
- 无单位参数不返回 `"unit"` 键（不存在，不是空字符串）
- wire 参数名反向映射为公开名：`Freq[1]` → `Freq`

```python
# 输入: {"Freq[1]": {"value": "1.0", "unit": "GHz"}, "Pts": {"value": "101"}}
# 通过 _from_wire_parameters() 反向映射
# 输出: {"Freq": {"value": "1.0", "unit": "GHz"}, "Pts": {"value": "101"}}
```

**wire→public 反向映射规则**：
1. 查固定参数的 `wire_name` → `public_name` 映射（`Freq[1]` → `Freq`）
2. 如果是动态模式且不在固定映射中（`Freq[2]`），匹配正则生成 `Freq[2]` → `Freq[2]`
3. 无法映射的保持原样

### 2.5 工具列表

| 工具 | 读取内容 | 特点 |
|---|---|---|
| `list_epp_projects` | 文件夹扫描 | `rglob("*.epp")`，最多 1000 个，返回名称/路径/大小 |
| `list_project_components` | `main` 原理图 | `parse_components` → 按 type/name 过滤 → 分页（offset/limit）→ 不含完整参数 |
| `get_component_parameters` | 原理图 | 按 `component_id` 精确匹配 → 返回完整 `paramsinfo`（可选包含隐藏参数） |
| `get_project_summary` | metadata + schematics + netlist + RAW | 聚合：元数据、原理图列表、元件类型分布、仿真器件配置、最新 RAW 文件 |
| `analyze_variables` | 所有原理图 | 识别 Var 元件定义 → 找到引用该变量的参数 → 列出 Sweep 配置 |
| `list_simulation_components` | 所有原理图 | `parse_components` 过滤 SP/HB/XDB → `_format_component_parameters` → 返回公开参数名 |

---

## 三、参数目录与 Schema

参数目录 `simulation_component_catalog.json`（v2.0.0）是 MCP 层对 EDI 参数知识的本地编码。它不替代 EDI 的校验，而是让 **MCP 在本地完成大部分参数校验**，减少无效 gRPC 调用和错误轮次。

### 3.1 设计动机

- **AI 友好**：`get_simulation_component_schema` 返回每个参数的类型、单位、权限——AI 不需要猜测参数名或单位格式
- **校验前置**：90% 的参数错误在 MCP 层就能被拦截（非法参数名、错误单位、类型不匹配）
- **权限控制**：`BandwidthForNoise` 这种内部参数直接标记为不可设置，AI 永远不会尝试传它
- **wire 透明**：AI 使用公开名（`Freq`），MCP 自动转换为 EDI 需要的线名（`Freq[1]`）

### 3.2 核心函数

| 函数 | 输入 | 输出 | 逻辑 |
|---|---|---|---|
| `_load_catalog()` | — | `dict` | `@lru_cache(maxsize=1)` 加载 JSON，失败返回 `{}` |
| `_resolve_parameter_schema(name)` | `"Freq"` | `(schema_dict, "Freq[1]")` | 先查 `parameters` 字典 → 再用正则匹配 `parameter_patterns` → 提取 index → 验证范围 |
| `_prepare_parameters(op, allow_empty)` | 公开参数 dict | `(wire_dict, None)` 或 `(None, error_dict)` | 11 步校验管线（见 §1.3） |
| `_to_wire_parameters()` | `{"Freq": ...}` | `{"Freq[1]": ...}` | 逐参数调 `_resolve_parameter_schema` |
| `_from_wire_parameters()` | `{"Freq[1]": ...}` | `{"Freq": ...}` | 固定映射优先 → 动态正则补全 → 不可映射的保持原样 |
| `_find_component_by_instance(path, name)` | `"C:/test.epp"`, `"HB1"` | `(component_dict, None)` 或 `(None, error_dict)` | 遍历所有原理图，按 `name` 精确匹配。多处返回 `AMBIGUOUS_INSTANCE_NAME` |

### 3.3 动态参数模式

HB 和 XDB 支持多音设置，需要多组 `Freq[n]`/`Order[n]`。目录用 `parameter_patterns` 表达：

```json
{
  "public_pattern": "Freq[{index}]",
  "wire_pattern": "Freq[{index}]",
  "index_min": 1,
  "index_max": 32,
  "value_type": "number",
  "unit_required": true,
  "units": ["Hz", "kHz", "MHz", "GHz"],
  "create_allowed": true,
  "update_allowed": true
}
```

解析器将 `{index}` 替换为 `(\d+)` 生成正则，匹配 `Freq[1]` ~ `Freq[32]`。同时保留固定映射 `Freq → Freq[1]` 作为快捷方式。

---

## 四、subprocess 命令行（3 个工具）

### 4.1 TurboCharts

`turbocharts_app.exe` 是 EDI 套件中的命令行工具，负责将 ADS RAW 仿真结果转换为曲线图和 CSV。MCP 通过 `subprocess.run` 调用它。

**串行化执行器**（`servers/turbocharts/config.py`）：

```python
_TURBOCHARTS_SEMAPHORE = threading.BoundedSemaphore(1)

def run_turbocharts(command, timeout_seconds=120):
    with _TURBOCHARTS_SEMAPHORE:  # 一次只运行一个 turbocharts 进程
        return subprocess.run(
            list(command),
            capture_output=True, text=True,
            timeout=timeout_seconds,
            creationflags=CREATE_NO_WINDOW,  # Windows: 不弹命令行窗口
        )
```

**命令行构造**（`turbocharts_convert`）：

```python
cmd = [TURBOCHARTS_PATH, "--raw", raw_path, "--img", img_path, "--type", chart_type]
if csv_path:   cmd.extend(["--csv", csv_path])
if linename:   cmd.extend(["--linename", linename])
if dependency: cmd.extend(["--dependcy", dependency])  # 注意：程序的参数名就是 --dependcy
if ac_config:  cmd.extend(["--ac", ac_config])
```

关键点：
- `--dependcy` 是 `turbocharts_app.exe` 的真实参数名（少一个 n，非拼写错误）
- MCP 层校验 `img_path` 扩展名（PNG/JPG/BMP/SVG）
- `timeout_seconds` 范围 1-600

### 4.2 RAW 曲线查询

`list_result_curves` 解析 ADS RAW 文件头部，返回可用曲线名。支持两种格式：

**MDS 格式**（EDI 当前使用的格式）：

```
File Format: MDS
Plotname: SP SP1[1] freq=(1 GHz->10 GHz)
No. Variables: 11
Variables:
    0 freq frequency type=real indep=yes
    1 S[1,1] s-param type=complex indep=no
    2 S[2,1] s-param type=complex indep=no
Values:
    0 1e9
    1 0.5-0.1j
```

解析器状态机：
```
逐行读取:
├─ "Plotname:" → 保存前一个 dataset，创建新 dataset
│   └─ 从 plot_name 中提取 freq=(...) → dependencies
├─ "Variables:" → 进入变量读取模式
├─ "Values:" → 退出变量读取模式（停止收集变量）
├─ 变量行（在 Variables: 和 Values: 之间）:
│   └─ 解析: index, name, description, type=real/complex, indep=yes/no
│       ├─ indep=yes → dependencies
│       └─ indep=no → _suggest_curves() 生成推荐曲线名
```

**XML 格式**：

```xml
<Dataset name="SP1">
  <Number name="freq" type="real"/>
  <Complex name="S(1,1)"/>
  <Complex name="S(2,1)"/>
</Dataset>
```

解析器用正则 `<Number|Complex|Real name="...">` 提取，标签名决定类型：`Complex`→complex，`Number`/`Real`→real。

**截断保护**：当前读取前 65536 字节。如果读取量达到上限，返回中包含 `warning` 字段提示结果可能不完整。

**曲线推荐规则**（`_suggest_curves`）：

| 变量类型 | 生成的曲线名 | 约束 |
|---|---|---|
| `S.delay[x,y]` (real) | `real_delayS[x,y]` | **最高优先级**，先于通用 real 判断 |
| real 类型 | `real_{name}` | |
| complex S[n,n] | `DB_S[n,n]`, `real_S[n,n]`, `phase_S[n,n]`, `VSWR_S[n,n]` | 反射参数加 VSWR |
| complex S[n,m] (n≠m) | `DB_S[n,m]`, `real_S[n,m]`, `phase_S[n,m]` | 传输参数不加 VSWR |
| 其他 complex | `DB_{name}`, `real_{name}`, `phase_{name}` | |

### 4.3 仿真结果对比

`compare_simulation_results` 对比 2-8 个 RAW 文件中同一条曲线：

```
1. 逐 RAW 调 turbocharts 导出临时 CSV
2. _read_curve_csv_xy() 读取 x/y 数据
3. 对齐策略:
   - "intersection": 取所有文件共有的 x 数据点
   - "interpolation": 以 reference_index 为基准插值
4. 计算差异指标（每对曲线的 max_abs_diff, mean_abs_diff, rms_diff）
5. Matplotlib 生成对比叠图
6. 可选导出对比 CSV
```

### 4.4 EDI 启动

`launch_edi`：

```
1. TCP connect 检查 gRPC 端口是否已就绪 → 已运行则跳过
2. subprocess.Popen([EDI.exe], cwd=EDI目录)
3. 轮询 TCP connect 等待 gRPC 就绪（默认 30 秒）
```

---

## 五、COM 对象（6 个 ANSYS 工具）

核心实现在 `servers/ansys/config.py`（进程检测/COM 附着/锁文件管理）。

### 5.1 COM 附着

通过 Windows COM 附着到已运行的 AEDT 实例，或启动新实例：

```python
_COM_PROGIDS = ("AnsoftHfss.HfssScriptInterface", "Ansoft.ElectronicsDesktop")

def _attach_aedt():
    for progid in _COM_PROGIDS:
        try:
            app = GetActiveObject(progid)
            return app, app.GetAppDesktop()
        except Exception:
            continue
    raise RuntimeError(f"GetActiveObject failed")
```

每个 COM 调用都在独立的 `pythoncom.CoInitialize()` / `CoUninitialize()` 上下文中执行。

### 5.2 AEDT 检测

```python
def aedt_is_running():
    return len(get_aedt_pids()) > 0

def get_aedt_pids():
    # psutil 遍历进程，匹配 ansysedt.exe
```

`_find_aedt()` 的搜索路径：环境变量 `AEDT_PATH` → Windows 注册表（`SOFTWARE\...\Uninstall` 找 ANSYS 安装位置）→ 默认目录（`C:\Program Files\AnsysEM\` 下按版本号排序取最新）。

### 5.3 锁文件管理

AEDT 打开工程时创建 `.aedt.lock`，内有一行 `DesktopProcessID=<pid>`。MCP 层的清理策略：

```
cleanup_stale_project_lock(project_path):
  ├─ 读取 .aedt.lock → 提取 DesktopProcessID
  ├─ PID 在进程列表中 → lock_active（拒绝删除）
  ├─ PID 不在进程列表中 → stale_lock_removed（安全删除）
  └─ 无法解析 PID → lock_unknown_format（保留）
```

**安全原则**：PID 存活时绝不删除锁文件。只有当进程确实已退出时才清理残留锁。

### 5.4 工具

| 工具 | 实现 |
|---|---|
| `open_hfss_project` | 清理失效锁 → 如 AEDT 已运行则 COM 附着 `OpenProject` / `SetActiveProject`；否则 `subprocess.Popen(ansysedt.exe project)` → 轮询 COM 验证 |
| `close_hfss_project` | COM `CloseProject`（可选 `Save` 前保存）→ 等待 2 秒让 AEDT 自己删锁 → 检查并清理残留锁 |
| `launch_aedt` | 已运行则返回状态；否则 subprocess 启动 → 轮询 COM 就绪 |
| `get_hfss_project_info` | COM 附着 → 读取 `GetProjectList`, `GetActiveProject`, `GetActiveDesign` |
| `start_hfss_analysis_async` | 验证 AEDT 运行 + setup 存在 → task 入 `_HFSS_QUEUE` → worker 线程执行 `design.Analyze(setup)` → 验证结果目录 mtime 变化 |
| `get_hfss_analysis_status` | 读取 `_HFSS_TASKS`，可选 `refresh_from_aedt` 查询 `AreThereSimulationsRunning` |

HFSS 任务队列：串行 worker 线程从 `queue.Queue(maxsize=10)` 取任务执行，单任务互斥（`_any_hfss_running()` 检查）。

---

## 六、图片工具（3 个，1 个条件注册）

### 6.1 show_image

```
1. _validate_image_path(path):
   ├─ expanduser + resolve（阻止 .. 遍历）
   ├─ 拒绝网络路径（\\ 和 //）
   ├─ 检查文件存在
   └─ 检查扩展名（.png/.jpg/.jpeg/.gif/.webp/.bmp）
2. 文件大小判断:
   ├─ ≤10MB → Base64 编码 → 返回 ImageContent + TextContent
   └─ >10MB → 只返回 TextContent（本地路径 + 查看建议）
```

### 6.2 copy_image_to_workspace

条件注册（仅 `OPENCLAW_WORKSPACE` 有效目录时）。复制到 `{workspace}/media/edi/mcp-cache/`：

- 文件名 = `{安全源文件名}_{MD5前8位}{扩展名}`（稳定文件名，同一源文件总是相同目标）
- 上限 40MB
- 超过 24h 的缓存自动清理
- `show_image` 成功时不会自动调用此工具

### 6.3 临时图片 HTTP 服务

`/images/{token}` 路由，10 分钟过期。供 Chat 界面渲染 `show_image` 返回的图片。不依赖 OpenClaw 工作区。

### 6.4 视觉分析（analyze_image）

调用配置的视觉模型分析本地图片内容。核心实现在 `servers/multimodal_vision/vision_analyzer.py`。

**与 show_image 的区别**：
- `show_image` → 把图片返回给 MCP 客户端渲染（不调用模型）
- `analyze_image` → 调用第三方视觉模型，返回结构化文字分析

**配置**（独立于聊天 LLM 配置）：
```ini
VISION_API_KEY=
VISION_BASE_URL=
VISION_MODEL=
VISION_TIMEOUT_SECONDS=45
VISION_MAX_IMAGE_MB=10
```

**调用流程**：
```
1. 配置检查 → 三项全部非空即开启
2. 图片校验 → 路径/扩展名/Pillow 内容验证/大小限制
3. Base64 编码 → data:image/png;base64,...
4. 并发控制 → BoundedSemaphore(2)，超限返回 VISION_BUSY
5. POST /v1/chat/completions（OpenAI 兼容 Vision API）
   └─ system prompt 防止图片提示注入
6. 响应解析 → 提取 analysis/usage，返回结构化结果
```

**安全措施**：
- 未置三项时返回 VISION_NOT_CONFIGURED
- 工具描述明确告知图片会被上传
- system prompt 声明图片中文字不执行
- 日志只记录 HTTP 状态/耗时/模型名/图片大小，不记 Base64/API Key/分析内容
- 返回 `content_is_untrusted: true` 提醒外层 Agent
- 不依赖 OPENCLAW_WORKSPACE
- show_image 成功后不自动调用

**错误码**（10 个）：
`VISION_NOT_CONFIGURED` `IMAGE_NOT_FOUND` `UNSUPPORTED_IMAGE_FORMAT`
`IMAGE_TOO_LARGE` `INVALID_IMAGE` `VISION_TIMEOUT`
`VISION_AUTH_FAILED` `VISION_RATE_LIMITED` `VISION_BUSY`
`VISION_PROVIDER_ERROR` `INVALID_VISION_RESPONSE`

---

## 七、Chat 聊天服务

核心实现在 `servers/chat/service.py`。支持 LLM 多轮工具调用闭环。

### 7.1 会话管理

```python
@dataclass
class ChatSession:
    session_id: str
    messages: list[dict]               # OpenAI 格式消息历史
    current_project_path: str | None   # 当前选定工程
    current_project_name: str | None
    last_folder_path: str | None       # 最近扫描目录
    last_projects: list[dict]          # 最近工程列表
    last_simulation_task_id: str | None
    simulation_task_ids: list[str]     # 历史任务（最近 20 个）
    updated_at: float
```

会话 TTL 2 小时，全局上限 100 个。每 5 分钟清理一次过期会话。

### 7.2 多轮闭环

```
用户消息 → ChatService.chat(session_id, message)
  ├─ system prompt（动态注入当前工程/任务上下文）
  ├─ 最多 5 轮:
  │   ├─ POST {LLM_BASE_URL}/v1/chat/completions
  │   │   └─ tools: CHAT_TOOLS_SCHEMA（28 个工具，配置工作区后 29 个）
  │   ├─ 无 tool_calls → 返回最终回复
  │   └─ 有 tool_calls:
  │       ├─ _validate(tool_name, args, session):
  │       │   ├─ 未知工具 → 拒绝
  │       │   ├─ args 不是 dict → 拒绝
  │       │   ├─ 必填字段空字符串 → 拒绝
  │       │   ├─ project_path → 从 session 上下文自动补齐
  │       │   └─ task_id → 从 session.last_simulation_task_id 自动补齐
  │       ├─ 重复调用保护: fingerprint = f"{tool}:{sorted_json(args)}"
  │       ├─ asyncio.to_thread(执行工具函数)
  │       ├─ _update_context(): 更新 session 的工程/任务状态
  │       └─ 工具结果序列化 → 作为 tool message 交回 LLM
  └─ 超 5 轮 → 返回错误
```

### 7.3 工具 Schema 构建

`_build_tools_schema()` 生成 OpenAI function-calling 格式的工具描述。每个工具的 `required` 和 `optional` 参数与其实际函数签名保持一致。

### 7.4 Web 路由

| 路由 | 功能 |
|---|---|
| `GET /ui` | 返回单页聊天应用（工具面板 + 聊天界面） |
| `GET /health` | TCP 检测 gRPC 端口 + 检查 `turbocharts_app.exe` 存在 → JSON |
| `POST /chat` | `{session_id, message}` → `ChatResponse(reply, activities, media, context)` |
| `GET /tools/list` | MCP 工具名和描述 JSON 列表 |
| `GET /images/{token}` | 临时图片访问（10 分钟过期，inline 渲染） |

### 7.5 安全加固

**会话锁**：同 session 并发请求串行化（`asyncio.Lock`），10 秒超时返回提示。

**输入限制**：
- 单条消息最大 20K 字符
- session_id 最大 128 字符
- 单轮工具调用最多 8 个
- 工具返回结果截断至 100K 字符

**破坏性工具确认门**（`delete_simulation_component`、`replace_models_from_csv`）：
- 模型请求执行破坏性工具时，Chat 层拦截并保存 `PendingAction`
- 向用户展示操作摘要和影响范围
- 用户需明确回复"确认"后才执行
- 一次确认只能执行一次，5 分钟过期
- 确认执行时使用原始保存参数，防止模型在确认前后篡改目标

---

## 八、Resources 与 Prompts

MCP 协议除了 Tool，还定义了 Resource（只读上下文）和 Prompt（可复用工作流模板）。实现在 `servers/mcp_content.py`。

### 8.1 Resources

通过 `@mcp.resource(uri, mime_type=...)` 装饰器注册。客户端通过 `resources/list` 和 `resources/read` 访问。

| URI | MIME | 内容来源 | 关键字段 |
|---|---|---|---|
| `edi://service/overview` | `application/json` | 动态生成 | `server_version`, `protocol_version`, `grpc_target`, `workspace_copy_enabled`, `safety_rules` |
| `edi://reference/simulation-components` | `application/json` | `_load_catalog()` | 与 `get_simulation_component_schema` 同源 |
| `edi://reference/operation-guide` | `text/markdown` | 静态维护 | 创建/删除/网表导入安全性约束 |

`workspace_copy_enabled` 的判断逻辑：

```python
from servers.multimodal_vision import OPENCLAW_WORKSPACE_PATH
workspace_enabled = OPENCLAW_WORKSPACE_PATH is not None
```

直接复用 `workspace_copy.OPENCLAW_WORKSPACE_PATH`，保证 Resource 返回值与实际工具注册状态一致（不依赖环境变量字符串解析）。

### 8.2 Prompts

通过 `@mcp.prompt(name=..., title=..., description=...)` 装饰器注册。返回 `list[Message]`（`role` + `content`）。客户端通过 `prompts/list` 和 `prompts/get` 访问。

**设计原则**：
- Prompt 只返回**消息模板**，不直接执行工具
- 非法参数直接拒绝，不静默回退（`action="bad"` → 返回错误消息，不变成 `create`）
- `update` 缺 `instance_name` 拒绝
- 仿真 Prompt 包含轮询限制（最多查询一次，间隔 ≥10s，单次最多 3 次）
- 核心工作流必须只靠 Tools 也能完成（Resource 是增强，不是依赖）

---

## 九、文档工具（2 个工具）

`open_document` 和 `open_local_document` 实现在 `servers/multimodal_vision/document.py`。

**`open_document`**：为本地 PDF/DOCX 生成临时 HTTP 链接。
- Token 映射 `/documents/{token}`，10 分钟过期
- 链接内保存 `disposition` 参数，PDF inline 预览、DOCX attachment 下载
- 安全：UNC 拒绝、绝对路径校验、nosniff 头

**`open_local_document`**：使用 `os.startfile()` 调用系统默认程序打开。
- 支持 10 种格式（.pdf/.doc/.docx/.xls/.xlsx/.ppt/.pptx/.txt/.csv/.rtf）
- 拒绝可执行文件、相对路径、网络路径
- 工具描述明确"仅用户要求时调用，生成报告后不得自动打开"

---

## 十、报告渲染（1 个工具）

`generate_simulation_report` 生成本地仿真报告（PDF/DOCX）。核心实现在 `servers/report/generator.py`。

**调用流程**：
```
1. 输出路径校验 → 绝对路径/后缀 .pdf .docx/父目录存在/overwrite 覆盖检查
2. model_name 校验 → 非空，最长 200 字符
3. spec_table 校验 → 二维数组/每行列数一致/单元格类型(string int float)
4. charts 校验 → 每项含 path(绝对/PNG/JPG)+title，缺失图片记 warning
5. components 校验 → 四项全字符串
6. schematic 校验 → 绝对路径，缺失记 warning
7. 构建 report payload → POST REPORT_RENDER_URL
8. HTTP 状态映射 → 400(REPORT_VALIDATION_FAILED) 409(OUTPUT_FILE_BUSY) 500(REPORT_RENDER_FAILED)
9. 服务不可用 → REPORT_SERVICE_UNAVAILABLE
10. 验证输出文件存在 → REPORT_OUTPUT_NOT_FOUND
```

**配置**：
```ini
REPORT_RENDER_URL=http://127.0.0.1:17867/api/v1/reports/render
REPORT_RENDER_TIMEOUT_SECONDS=45
```

**设计原则**：
- 只校验数据并调用渲染 API，不自动执行仿真、生成曲线或编造指标
- 默认禁止覆盖（`overwrite=false`），防止意外覆盖已有报告
- 器件厂家和规格不得猜测，无来源时留空
- 服务不可用时工具仍注册，返回 `REPORT_SERVICE_UNAVAILABLE`
- `_rtool` 已扩展支持完整 JSON Schema 属性定义（对象数组、二维数组）

**11 个错误码**：`INVALID_OUTPUT_PATH` `OUTPUT_DIRECTORY_NOT_FOUND`
`OUTPUT_ALREADY_EXISTS` `INVALID_REPORT_PARAMETERS` `INVALID_CHART_PATH`
`REPORT_SERVICE_UNAVAILABLE` `REPORT_RENDER_TIMEOUT` `REPORT_VALIDATION_FAILED`
`OUTPUT_FILE_BUSY` `REPORT_RENDER_FAILED` `INVALID_REPORT_RESPONSE`
`REPORT_OUTPUT_NOT_FOUND`

---

## 十一、跨层设计原则

### 11.1 参数校验分层

AI 的请求经过 5 层校验才能到达 EDI 服务端，每一层拦截不同类别的错误：

```
Chat _validate()           空字符串拒绝、project_path/task_id 自动补齐
  ↓
工具函数入口              路径校验（validate_project_path/validate_file + resolve）
  ↓
_prepare_parameters()      类型/单位/权限/wire 名/别名冲突（MCP 本地）
  ↓
call_grpc()                JSON 序列化、超时控制、锁获取
  ↓
EDI gRPC 服务             最终业务校验和执行
```

### 11.2 错误码体系

| 层级 | 字段 | 来源 | 示例 |
|---|---|---|---|
| MCP 本地校验 | `error_code` | `_param_error()` / `_component_error()` | `INVALID_PARAMETERS`, `COMPONENT_NOT_FOUND`, `DUPLICATE_PARAMETER_ALIAS`, `CLEAR_CONFIRMATION_REQUIRED` |
| gRPC 通信层 | `status` | `_terminal_result()` | `SUCCEEDED`, `FAILED`, `TIMEOUT`, `STREAM_DISCONNECTED`, `GRPC_UNAVAILABLE`, `PROTOCOL_MISMATCH` |

两者的语义不同：`error_code` 表示已知的错误类型（AI 可以据此修正参数重试），`status` 表示通信终态（指示是否需要人工介入）。

完整的 `error_code` 列表（18 个）：

```
COMPONENT_SCHEMA_UNAVAILABLE    UNSUPPORTED_COMPONENT_TYPE
UNSUPPORTED_PARAMETER           CREATE_PARAMETER_NOT_ALLOWED
UPDATE_PARAMETER_NOT_ALLOWED    INVALID_PARAMETERS
INVALID_PARAMETER_VALUE         MISSING_VALUE
INVALID_VALUE                   INVALID_ENUM_VALUE
MISSING_UNIT                    UNSUPPORTED_UNIT
DUPLICATE_PARAMETER_ALIAS       EMPTY_INSTANCE_NAME
COMPONENT_NOT_FOUND             AMBIGUOUS_INSTANCE_NAME
COMPONENT_TYPE_MISMATCH         COMPONENT_TYPE_REQUIRED
INVALID_ACTIVE_STATE            CLEAR_CONFIRMATION_REQUIRED
FILE_NOT_FOUND                  INVALID_STATUS
SIMULATION_QUEUE_FULL           TASK_NOT_FOUND
```

### 11.3 并发控制

| 资源 | 锁类型 | 原因 |
|---|---|---|
| EDA gRPC 操作 | `threading.RLock` 全局锁 | EDI 进程同一时间只能做一件事。可重入锁确保同一个线程可以嵌套调用 |
| 异步仿真任务 | `threading.Lock` | 保护 `_sim_tasks` 字典的读写 |
| TurboCharts 进程 | `BoundedSemaphore(1)` | 一次只能运行一个 turbocharts 实例 |
| ANSYS COM 操作 | `threading.RLock` | 保护 AEDT COM 对象访问 |
| ANSYS 工程路径 | 无锁（低频操作） | `_OPEN_PROJECT_PATHS` 字典，并发冲突概率极低 |
| Chat 会话 | `threading.Lock` | 保护 `_sessions` 字典的读写 |
| 图片 token | `threading.RLock` | 保护 `_IMAGE_TOKENS` 字典（注册、查询、过期清理） |

### 11.4 向后兼容

协议 v2 不兼容 v1。`UPSERT_SIMULATION_COMPONENT` 已被拆分为 `CREATE_SIMULATION_COMPONENT`(11) + `UPDATE_SIMULATION_COMPONENT`(15)，新增 `GENERATE_SCHEMATIC_FROM_NETLIST`(13) 和 `SET_COMPONENT_ACTIVE_STATE`(14)。EDI 服务、MCP 服务、protobuf 生成代码必须成套升级，禁止新旧混用。

### 11.5 非幂等操作保护

以下操作禁止在 `TIMEOUT`/`STREAM_DISCONNECTED` 后自动重试：

- `create_simulation_component`（可能创建重复器件）
- `generate_schematic_from_netlist` 的追加模式（可能重复导入）
- `generate_schematic_from_netlist` 的清空模式（可能再次清空）

`set_component_active_state` 是确定性设置，可以安全重试。

### 11.6 返回字段语义 — outcome_known / task_success

gRPC 层通过 `_terminal_result()` 统一构建返回结构，关键字段：

```
completed      MCP 侧任务是否结束（线程退出、超时、断连都是 completed=True）
outcome_known  是否收到了 EDI 的最终事件（SUCCEEDED 或 FAILED）
task_success   仅 outcome_known=True 时有意义；None = EDI 实际状态未知
failure_source 异常来源："mcp" 表示 MCP 自身异常，不是 EDI 业务失败
```

语义矩阵：

| 状态 | success | outcome_known | task_success |
|---|---|---|---|
| SUCCEEDED | True | True | True |
| FAILED（EDI） | False | True | False |
| REJECTED | False | True | False |
| TIMEOUT | False | False | None |
| STREAM_DISCONNECTED | False | False | None |
| GRPC_UNAVAILABLE | False | False | None |
| PROTOCOL_MISMATCH | False | False | None |
| MCP 异常 | False | False | None（failure_source="mcp"） |

`_run_sim_task()` 不覆盖 gRPC 层已计算的 `task_success`，
只在字段不存在时从 `outcome_known` 和 `status` 推导。

### 11.7 配置统一

所有环境变量收敛到 `servers/settings.py` → `Settings` dataclass（frozen，lru_cache 单例）。
其他模块通过 `get_settings()` 读取，不再直接调用 `os.getenv()`。

启动时 `start_servers.py` 调用 `settings.validate()`，校验：
- EDA_GRPC_SERVER 格式（host:port）
- gRPC 端口范围（1-65535）
- MCP_TRANSPORT 合法性（streamable-http / stdio）
- MCP_PORT 范围

### 11.8 Chat 破坏性工具确认

注册时标记 5 个破坏性工具，参数感知确认：

| 工具 | 确认条件 |
|---|---|
| delete_simulation_component | 无条件确认 |
| replace_models_from_csv | 无条件确认 |
| replace_port_component | 无条件确认 |
| close_edi_project | need_save=true 时确认 |
| generate_simulation_report | overwrite=true 时确认 |
| generate_schematic_from_netlist | clear_before_import=true 时确认（Chat 层补 confirm_clear） |

确认支持简单肯定词（确认/是/yes/ok/好的），无操作 5 分钟过期。

### 11.9 HFSS 任务管理

- TTL 2 小时自动清理（`_prune_hfss_tasks()`）
- 最大 50 个任务（含历史）
- 统一 `outcome_known` / `task_success` 字段
- TASK_NOT_FOUND 返回 `success=False, outcome_known=False, task_success=None`
