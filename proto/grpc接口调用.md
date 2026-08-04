# ExternalCall gRPC 接口调用说明

本文说明外部程序如何调用 EDA-PMDS 的 `ExternalCall` gRPC 服务。协议使用统一的 `payload_json` 字符串传递业务参数，任务提交和任务结果获取是异步的。

## 1. 服务接口

```proto
service ExternalCall {
  rpc PerformAction(Request) returns (Response) {}
  rpc FetchEvent(FetchEventRequest) returns (stream Event) {}
}
```

- `PerformAction`：提交一个外部调用任务。
- `FetchEvent`：按 `client_uuid` 拉取任务状态和最终结果事件。

`PerformAction` 返回成功只表示服务端已受理任务，不表示任务执行完成。最终结果需要通过 `FetchEvent` 获取。

## 2. 通用请求结构

```proto
message Request {
  string client_uuid = 1;
  string task_id = 2;
  EventType type = 3;
  string payload_json = 4;
}
```

通用字段：

- `client_uuid`：客户端唯一标识，不能为空。提交任务和拉取事件时必须保持一致。
- `task_id`：任务唯一标识，不能为空。建议每次请求使用新的 UUID。
- `type`：任务类型。
- `payload_json`：JSON 字符串，按任务类型填写不同字段。

## 3. 任务类型

```proto
enum EventType {
  EVENT_TYPE_UNSPECIFIED = 0;
  OPEN_PROJECT = 1;
  SIMULATE_PROJECT = 2;
  VIEW_PROJECT_NETLIST = 3;
  LOG_EVENT = 4;
  ERROR_EVENT = 5;
  MODEL_REPLACE = 6;
  CAPTURE_SCHEMATIC = 7;
  CLOSE_PROJECT = 8;
  CALL_SIMULATION_CONTROLLER = 9;
  SIMULATE_NETLIST = 10;
  CREATE_SIMULATION_COMPONENT = 11;
  DELETE_SIMULATION_COMPONENT = 12;
  GENERATE_SCHEMATIC_FROM_NETLIST = 13;
  SET_COMPONENT_ACTIVE_STATE = 14;
  UPDATE_SIMULATION_COMPONENT = 15;
}
```

任务类型：

- `OPEN_PROJECT`：打开工程。
- `SIMULATE_PROJECT`：执行工程仿真。
- `VIEW_PROJECT_NETLIST`：查看工程网表。
- `MODEL_REPLACE`：按 CSV 执行模型替换。
- `CAPTURE_SCHEMATIC`：截图保存原理图图片。
- `CLOSE_PROJECT`：关闭工程，可选择是否保存工程。
- `CALL_SIMULATION_CONTROLLER`：直接调用 ADS 仿真器。
- `SIMULATE_NETLIST`：仿真指定的 `netlist.log`，返回 RAW 结果和仿真器输出日志。
- `CREATE_SIMULATION_COMPONENT`：新增一个 `SParameter`、`HarmonicBalance` 或 `XDB` 器件。
- `DELETE_SIMULATION_COMPONENT`：按器件实例名删除原理图上的通用器件。
- `GENERATE_SCHEMATIC_FROM_NETLIST`：将指定网表导入工程的唯一原理图。
- `SET_COMPONENT_ACTIVE_STATE`：按器件实例名确定性设置正常、禁用或短路状态。
- `UPDATE_SIMULATION_COMPONENT`：按器件实例名更新仿真器件参数。
## 4. payload_json 示例

### OPEN_PROJECT

```json
{
  "project_path": "C:/path/to/project.epp"
}
```

### SIMULATE_PROJECT

```json
{
  "project_path": "C:/path/to/project.epp",
  "log_source": "logger_id"
}
```

`log_source` 用于标识调用方日志来源。

### SIMULATE_NETLIST

```json
{
  "netlist_path": "C:/path/to/netlist.log"
}
```

`netlist_path` 必须指向一个已经存在的文件。服务端会将网表复制到独立任务目录后再执行仿真，不会修改传入的原始网表。

### VIEW_PROJECT_NETLIST

```json
{
  "project_path": "C:/path/to/project.epp"
}
```

### MODEL_REPLACE

```json
{
  "project_path": "C:/path/to/project.epp",
  "csv_path": "C:/path/to/replace.csv"
}
```

### CAPTURE_SCHEMATIC

```json
{
  "project_path": "C:/path/to/project.epp",
  "img_path": "C:/path/to/schematic.png"
}
```

### CLOSE_PROJECT

```json
{
  "project_path": "C:/path/to/project.epp",
  "need_save": false
}
```

`need_save` 表示关闭工程前是否保存。

### CALL_SIMULATION_CONTROLLER

```json
{
  "netlist_path": "C:/path/to/netlist.log",
  "ads_path": "C:/Keysight/ADS"
}
```



### CREATE_SIMULATION_COMPONENT

```json
{
  "project_path": "C:/path/to/project.epp",
  "component_type": "SParameter",
  "parameters": {
    "Start": {
      "value": "1",
      "unit": "GHz"
    }
  }
}
```

- `component_type` 只支持 `SParameter`、`HarmonicBalance`、`XDB`，区分大小写。
- `parameters` 可省略、传空对象或只提供部分初始化参数；未提供的参数使用器件默认值。
- 每个参数包含标量字段 `value`，可选字符串字段 `unit`，不能包含其他字段。
- 每次调用都创建新器件，同类型器件可以存在多个。服务端自动分配未占用的实例名，并在最终事件的 `instance_name` 中返回。

### UPDATE_SIMULATION_COMPONENT

```json
{
  "project_path": "C:/path/to/project.epp",
  "instance_name": "SP2",
  "parameters": {
    "Stop": {
      "value": "20",
      "unit": "GHz"
    },
    "Pts": {
      "value": "201"
    }
  }
}
```

- `instance_name` 为原理图上的器件实例名，精确匹配。
- 仅支持更新 `SParameter`、`HarmonicBalance`、`XDB`。
- `parameters` 必须为非空对象；只更新请求中提供的参数，其他参数保持原值。
- 保存失败时恢复修改前参数。

### DELETE_SIMULATION_COMPONENT

```json
{
  "project_path": "C:/path/to/project.epp",
  "instance_name": "R1"
}
```

该任务按 `instance_name` 精确删除任意普通器件，并按原理图正常删除流程处理器件连接线。保存失败时撤销删除。

### SET_COMPONENT_ACTIVE_STATE

```json
{
  "project_path": "C:/path/to/project.epp",
  "instance_name": "R1",
  "state": "SHORTED"
}
```

`state` 只接受以下大写值：

- `NORMAL`：正常。
- `DISABLED`：禁用。
- `SHORTED`：短路。

该任务直接设置目标状态，不执行状态切换；保存失败时恢复原状态。

### GENERATE_SCHEMATIC_FROM_NETLIST

```json
{
  "project_path": "C:/path/to/project.epp",
  "netlist_path": "C:/path/to/netlist.log",
  "clear_before_import": false
}
```

- `netlist_path` 必须是已存在的文件。
- `clear_before_import` 为可选布尔值，默认值为 `false`；为 `true` 时导入前清空 `main` 原理图，为 `false` 时追加。
- 服务端固定向工程中的 `main` 原理图导入器件和连接链路，成功后自动保存工程。最终事件返回 `schematic_path`、`symbols_added`、`nets_added`、`lines_added` 和 `net_points_added`。

上述工程类任务均使用工程中的唯一原理图。工程已打开时复用现有工程窗口，否则先打开工程再执行操作。
## 5. PerformAction 返回值

```proto
message Response {
  int32 code = 1;
  string message = 2;
  string client_uuid = 3;
  string task_id = 4;
  EventType event_type = 5;
}
```

- `code == 0`：任务已受理。
- `code != 0`：任务未受理，错误原因见 `message`。
- `client_uuid`：请求中的客户端标识。
- `task_id`：请求中的任务 ID。
- `event_type`：请求任务类型。

注意：`Response` 不是最终业务结果。业务是否完成、成功或失败，要看后续 `FetchEvent` 返回的事件。

## 6. FetchEvent

请求：

```proto
message FetchEventRequest {
  string client_uuid = 1;
}
```

返回事件：

```proto
message Event {
  string client_uuid = 1;
  string task_id = 2;
  EventType event_type = 3;
  ResultStatus status = 4;
  string message = 5;
  string payload_json = 6;
}
```

状态枚举：

```proto
enum ResultStatus {
  RESULT_STATUS_UNKNOWN = 0;
  RESULT_STATUS_RUNNING = 1;
  RESULT_STATUS_SUCCESS = 2;
  RESULT_STATUS_FAILED = 3;
}
```

常见事件顺序：

1. `PerformAction` 返回 `code == 0`。
2. `FetchEvent` 收到 `RESULT_STATUS_RUNNING`。
3. `FetchEvent` 收到 `RESULT_STATUS_SUCCESS` 或 `RESULT_STATUS_FAILED`。

## 7. 事件 payload_json

事件中的 `payload_json` 也是 JSON 字符串。字段如下：

- `OPEN_PROJECT`：`project_path`
- `SIMULATE_PROJECT`：`project_path`、`result_path`、`ads_output`
- `VIEW_PROJECT_NETLIST`：`project_path`、`netlist_path`
- `MODEL_REPLACE`：`project_path`
- `CAPTURE_SCHEMATIC`：`project_path`、`img_path`
- `CLOSE_PROJECT`：`project_path`、`need_save`
- `LOG_EVENT`：`level`、`source`、`text`
- `CALL_SIMULATION_CONTROLLER`：`netlist_path`、`ads_path`
- `SIMULATE_NETLIST`：`netlist_path`、`result_path`、`ads_output`
- `CREATE_SIMULATION_COMPONENT`：`project_path`、`component_type`、`action`、`instance_name`
- `UPDATE_SIMULATION_COMPONENT`：`project_path`、`instance_name`
- `DELETE_SIMULATION_COMPONENT`：`project_path`、`instance_name`
- `SET_COMPONENT_ACTIVE_STATE`：`project_path`、`instance_name`、`state`
- `GENERATE_SCHEMATIC_FROM_NETLIST`：`project_path`、`netlist_path`、`schematic_path`、`clear_before_import`、`symbols_added`、`nets_added`、`lines_added`、`net_points_added`
## 8. SIMULATE_NETLIST 完整调用示例

建议先调用 `FetchEvent` 建立流式订阅，再调用 `PerformAction` 提交任务。两次调用的 `client_uuid` 必须一致。

### 8.1 PerformAction 请求

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-netlist-001",
  "type": "SIMULATE_NETLIST",
  "payload_json": "{\"netlist_path\":\"C:/test/netlist.log\"}"
}
```

如果 Postman 未识别最新枚举，可以重新导入 `ecserver.proto`，也可以临时将 `type` 填为数值 `10`。

`PerformAction` 受理成功时返回：

```json
{
  "code": 0,
  "message": "task accepted",
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-netlist-001",
  "event_type": "SIMULATE_NETLIST"
}
```

### 8.2 FetchEvent 运行事件

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-netlist-001",
  "event_type": "SIMULATE_NETLIST",
  "status": "RESULT_STATUS_RUNNING",
  "message": "task accepted",
  "payload_json": "{\"netlist_path\":\"C:/test/netlist.log\"}"
}
```

### 8.3 FetchEvent 成功事件

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-netlist-001",
  "event_type": "SIMULATE_NETLIST",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "netlist simulation finished",
  "payload_json": "{\"netlist_path\":\"C:/test/netlist.log\",\"result_path\":\"C:/test/history/result.raw\",\"ads_output\":\"ADS simulator output...\"}"
}
```

`payload_json` 解析后的业务对象为：

```json
{
  "netlist_path": "C:/test/netlist.log",
  "result_path": "C:/test/history/result.raw",
  "ads_output": "ADS simulator output..."
}
```

字段说明：

- `netlist_path`：客户端传入的原始网表绝对路径。
- `result_path`：复制完成后的 RAW 文件绝对路径，固定放在原网表同级的 `history/result.raw`。
- `ads_output`：本次 ADS 仿真进程的标准输出和标准错误输出。日志只在最终成功或失败事件中统一返回。

### 8.4 服务端文件处理流程

假设程序目录为 `C:/Program Files/EDI`，请求中的 `task_id` 为 `postman-netlist-001`：

1. 创建临时目录 `C:/Program Files/EDI/simulation/postman-netlist-001/`。
2. 将传入的网表复制为该目录下的 `netlist.log`。
3. 在临时目录执行 ADS 仿真并生成 `result.raw`。
4. 将结果复制到原网表目录的 `history/result.raw`，存在旧文件时覆盖。
5. 将复制后的 `history/result.raw` 绝对路径写入最终事件的 `result_path`。
6. 删除临时目录 `simulation/postman-netlist-001/`。

如果仿真、RAW 复制或临时目录清理失败，最终状态为 `RESULT_STATUS_FAILED`。失败事件仍包含已经收集到的 `ads_output`；未成功归档 RAW 时，`result_path` 为空字符串。

## 9. 仿真器件管理完整调用示例

建议先调用 `FetchEvent` 建立流式订阅，再调用 `PerformAction`。以下请求使用相同的 `client_uuid`。

### 9.1 新增 SParameter

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-create-sp-001",
  "type": "CREATE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\",\"parameters\":{\"Start\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"Stop\":{\"value\":\"10.0\",\"unit\":\"GHz\"},\"Step\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"Pts\":{\"value\":\"10\"},\"NoiseInputPort\":{\"value\":\"1\"},\"NoiseOutputPort\":{\"value\":\"2\"},\"BandwidthForNoise\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"CalcNoise\":{\"value\":\"no\"},\"CalcS\":{\"value\":\"yes\"},\"CalcGroupDelay\":{\"value\":\"no\"},\"EnforcePassivity\":{\"value\":\"no\"},\"GroupDelayAperture\":{\"value\":\"1e-4\"},\"FreqConversion\":{\"value\":\"no\"},\"FreqConversionPort\":{\"value\":\"1\"}}}"
}
```
该请求包含 SParameter 当前全部可设置属性。注意：`BandwidthForNoise` 为 EDI 内部参数，MCP 层禁止手动设置（create_allowed=false, update_allowed=false），EDI 使用默认值。界面中显示的 `Bandwidth` 对应接口字段 `BandwidthForNoise`，不能传 `Bandwidth`。


如果 Postman 未识别最新枚举，请重新导入 `ecserver.proto`，也可以临时将 `type` 填为数值 `11`。

最终成功事件示例：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-create-sp-001",
  "event_type": "CREATE_SIMULATION_COMPONENT",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "simulation component created",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\",\"action\":\"created\",\"instance_name\":\"SP1\"}"
}
```

`CREATE_SIMULATION_COMPONENT` 每次都创建新器件，`action` 固定为 `created`；实际分配名称见 `instance_name`。

### 9.2 新增 HarmonicBalance

下面的请求包含 HarmonicBalance 默认初始化时的全部属性：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-create-hb-001",
  "type": "CREATE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"HarmonicBalance\",\"parameters\":{\"Freq[1]\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"Order[1]\":{\"value\":\"5\"}}}"
}
```

需要多音设置时，可以继续增加成对的 `Freq[2]`、`Order[2]`、`Freq[3]`、`Order[3]` 等动态参数。

### 9.3 新增 XDB

下面的请求包含 XDB 当前全部可设置属性：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-create-xdb-001",
  "type": "CREATE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"XDB\",\"parameters\":{\"Freq[1]\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"Order[1]\":{\"value\":\"5\"},\"GC_XdB\":{\"value\":\"1\"},\"GC_InputPort\":{\"value\":\"1\"},\"GC_OutputPort\":{\"value\":\"2\"},\"GC_InputFreq\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"GC_OutputFreq\":{\"value\":\"1.0\",\"unit\":\"GHz\"},\"GC_InputPowerTol\":{\"value\":\"1e-3\"},\"GC_OutputPowerTol\":{\"value\":\"1e-3\"},\"GC_MaxInputPowerTol\":{\"value\":\"100\"},\"StatusLevel\":{\"value\":\"2\"}}}"
}
```

### 9.4 删除指定名称的器件

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-delete-sp-001",
  "type": "DELETE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"instance_name\":\"SP1\"}"
}
```

如果 Postman 未识别最新枚举，可以将 `type` 临时填为数值 `12`。

最终成功事件示例：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-delete-sp-001",
  "event_type": "DELETE_SIMULATION_COMPONENT",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "component deleted",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"instance_name\":\"SP1\"}"
}
```

该任务不限于三种仿真器件，可以按名称删除普通原理图器件及其连接线。

### 9.5 按器件名更新参数

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-update-sp-001",
  "type": "UPDATE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"instance_name\":\"SP2\",\"parameters\":{\"Stop\":{\"value\":\"20\",\"unit\":\"GHz\"},\"Pts\":{\"value\":\"201\"}}}"
}
```

最终成功事件示例：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-update-sp-001",
  "event_type": "UPDATE_SIMULATION_COMPONENT",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "simulation component updated",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"instance_name\":\"SP2\"}"
}
```

### 9.6 设置器件正常、禁用或短路状态

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-state-r1-001",
  "type": "SET_COMPONENT_ACTIVE_STATE",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"instance_name\":\"R1\",\"state\":\"SHORTED\"}"
}
```

最终成功事件中的 `payload_json` 返回 `project_path`、`instance_name` 和已经设置的 `state`。
## 10. 网表生成链路完整调用示例

建议先调用 `FetchEvent` 建立流式订阅，再调用 `PerformAction` 提交任务。两次调用的 `client_uuid` 必须一致。

### 10.1 PerformAction 请求

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-generate-schematic-001",
  "type": "GENERATE_SCHEMATIC_FROM_NETLIST",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"netlist_path\":\"C:/test/netlist.log\",\"clear_before_import\":true}"
}
```

`clear_before_import` 可省略，默认值为 `false`：为 `true` 时导入前清空 `main` 原理图；为 `false` 时追加到现有原理图。

如果 Postman 未识别最新枚举，请重新导入 `ecserver.proto`，也可以临时将 `type` 填为数值 `13`。

### 10.2 FetchEvent 运行事件

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-generate-schematic-001",
  "event_type": "GENERATE_SCHEMATIC_FROM_NETLIST",
  "status": "RESULT_STATUS_RUNNING",
  "message": "task accepted",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"netlist_path\":\"C:/test/netlist.log\",\"clear_before_import\":true}"
}
```

### 10.3 FetchEvent 成功事件

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-generate-schematic-001",
  "event_type": "GENERATE_SCHEMATIC_FROM_NETLIST",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "schematic import finished",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"netlist_path\":\"C:/test/netlist.log\",\"schematic_path\":\"C:/test/schematics/main/schematic.ep\",\"clear_before_import\":true,\"symbols_added\":10,\"nets_added\":8,\"lines_added\":12,\"net_points_added\":4}"
}
```

字段说明：

- `schematic_path`：生成并保存后的 `main/schematic.ep` 文件绝对路径。
- `symbols_added`：本次新增的器件数量。
- `nets_added`：本次新增的网段数量。
- `lines_added`：本次新增的连接线数量。
- `net_points_added`：本次新增的网络连接点数量。

服务端固定操作工程中的 `main` 原理图，调用程序目录下的 `schematic_drawing_tool_edi/schematic_drawing_tool.exe` 解析网表，成功后自动保存工程。如果工程、`main` 原理图、网表文件、绘图工具或配置文件不可用，最终事件状态为 `RESULT_STATUS_FAILED`，原因通过 `message` 返回。
## 11. 注意事项

- `client_uuid`、`task_id`、`type` 必须填写。
- `payload_json` 必须是合法 JSON 对象字符串。
- 涉及工程的任务中，`project_path` 必须指向已存在的 `.epp` 文件。
- `CREATE_SIMULATION_COMPONENT` 的 `component_type` 只接受 `SParameter`、`HarmonicBalance`、`XDB`；`parameters` 可省略或只提供部分参数。
- `UPDATE_SIMULATION_COMPONENT` 必须提供器件 `instance_name` 和非空 `parameters`，目标必须是上述三种仿真器件之一。
- `DELETE_SIMULATION_COMPONENT` 和 `SET_COMPONENT_ACTIVE_STATE` 使用 `instance_name` 精确定位器件。
- 器件创建、参数更新、删除或状态设置成功后会立即保存工程；保存失败时回滚本次操作。
- `GENERATE_SCHEMATIC_FROM_NETLIST` 必须提供已存在的工程文件和网表文件，固定操作 `main` 原理图。
- `clear_before_import=true` 会在导入前清空 `main` 原理图，调用方应确认原内容允许删除。
- `MODEL_REPLACE` 必须提供已存在的 `.csv` 文件路径。
- `CAPTURE_SCHEMATIC` 必须提供图片输出路径。
- `CLOSE_PROJECT` 使用 `project_path` 和 `need_save` 关闭工程。
- 同一客户端会话内，提交任务和拉取事件应使用同一个 `client_uuid`。
- `SIMULATE_NETLIST` 的 `netlist_path` 必须是已存在的文件。
- `SIMULATE_NETLIST` 的 `task_id` 只能包含英文字母、数字、下划线、点和连字符，且不能是 `.` 或 `..`。
- `simulation/<task_id>` 已存在时任务会失败；每次调用应使用新的 `task_id`。
- 独立的 `LOG_EVENT` 暂未支持；仿真器日志通过最终事件的 `ads_output` 返回。