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
  UPSERT_SIMULATION_COMPONENT = 11;
  DELETE_SIMULATION_COMPONENT = 12;
}
```

任务类型：

- `OPEN_PROJECT`：打开工程。
- `SIMULATE_PROJECT`：执行仿真。
- `VIEW_PROJECT_NETLIST`：查看工程网表。
- `MODEL_REPLACE`：按 CSV 执行模型替换。
- `CAPTURE_SCHEMATIC`：截图保存原理图图片。
- `CLOSE_PROJECT`：关闭工程，可选择是否保存工程。
- `CALL_SIMULATION_CONTROLLER`：直接调用 ADS 仿真器。
- `SIMULATE_NETLIST`：仿真指定的 `netlist.log`，返回 RAW 结果和仿真器输出日志。
- `UPSERT_SIMULATION_COMPONENT`：在工程唯一原理图中新增或更新 `SParameter`、`HarmonicBalance` 或 `XDB` 器件。
- `DELETE_SIMULATION_COMPONENT`：从工程唯一原理图中删除指定类型的仿真器件。

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



### UPSERT_SIMULATION_COMPONENT

```json
{
  "project_path": "D:/test/project.epp",
  "component_type": "SParameter",
  "parameters": {
    "Start": {
      "value": "1.0",
      "unit": "GHz"
    },
    "Stop": {
      "value": "10.0",
      "unit": "GHz"
    },
    "Step": {
      "value": "1.0",
      "unit": "GHz"
    },
    "Pts": {
      "value": "10"
    },
    "NoiseInputPort": {
      "value": "1"
    },
    "NoiseOutputPort": {
      "value": "2"
    },
    "BandwidthForNoise": {
      "value": "1.0",
      "unit": "GHz"
    },
    "CalcNoise": {
      "value": "no"
    },
    "CalcS": {
      "value": "yes"
    },
    "CalcGroupDelay": {
      "value": "no"
    },
    "EnforcePassivity": {
      "value": "no"
    },
    "GroupDelayAperture": {
      "value": "1e-4"
    },
    "FreqConversion": {
      "value": "no"
    },
    "FreqConversionPort": {
      "value": "1"
    }
  }
}
```

- `component_type` 只支持 `SParameter`、`HarmonicBalance`、`XDB`，区分大小写。
- `parameters` 必须是非空 JSON 对象；键名必须是该器件实际支持的参数名。
- 每个参数必须包含标量字段 `value`，可以包含字符串字段 `unit`，不能包含其他字段。
- `unit` 必须是该参数支持的单位；无单位参数不要填写 `unit`。
- 工程中已有该类型器件时，只覆盖请求中提供的参数；不存在时创建器件、保留默认参数后再覆盖请求参数。
- 对于开关类参数，建议按器件现有格式传字符串 `"yes"` 或 `"no"`。

### UPSERT_SIMULATION_COMPONENT（XDB 示例）

```json
{
  "project_path": "D:/test/project.epp",
  "component_type": "XDB",
  "parameters": {
    "Freq[1]": {
      "value": "1.0",
      "unit": "GHz"
    },
    "Order[1]": {
      "value": "5"
    },
    "GC_XdB": {
      "value": "1"
    },
    "GC_InputPort": {
      "value": "1"
    },
    "GC_OutputPort": {
      "value": "2"
    },
    "GC_InputFreq": {
      "value": "1.0",
      "unit": "GHz"
    },
    "GC_OutputFreq": {
      "value": "1.0",
      "unit": "GHz"
    },
    "GC_InputPowerTol": {
      "value": "1e-3"
    },
    "GC_OutputPowerTol": {
      "value": "1e-3"
    },
    "GC_MaxInputPowerTol": {
      "value": "100"
    },
    "StatusLevel": {
      "value": "2"
    }
  }
}
```

XDB 支持的参数：

| 参数名 | 说明 | 值类型 | 单位 |
|---|---|---|---|
| `Freq[1]` | 基频频率 | number | Hz / kHz / MHz / GHz |
| `Order[1]` | 谐波阶数 | integer | — |
| `GC_XdB` | 增益压缩 | number | — |
| `GC_InputPort` | 输入端口 | integer | — |
| `GC_OutputPort` | 输出端口 | integer | — |
| `GC_InputFreq` | 增益压缩输入频率 | number | Hz / kHz / MHz / GHz |
| `GC_OutputFreq` | 增益压缩输出频率 | number | Hz / kHz / MHz / GHz |
| `GC_InputPowerTol` | 输入功率容差 | number | — |
| `GC_OutputPowerTol` | 输出功率容差 | number | — |
| `GC_MaxInputPowerTol` | 最大输入功率容差 | number | — |
| `StatusLevel` | 状态等级 | integer | — |

### DELETE_SIMULATION_COMPONENT

```json
{
  "project_path": "C:/path/to/project.epp",
  "component_type": "SParameter"
}
```

`component_type` 只支持 `SParameter`、`HarmonicBalance`、`XDB`。服务端删除该类型的唯一器件并保存工程；器件不存在或同类型器件超过一个时，任务最终返回失败。

上述两个任务均使用工程中的唯一原理图。若工程已经在 EDA-PMDS 中打开，服务端复用现有工程窗口；否则先打开工程再执行操作。

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
- `UPSERT_SIMULATION_COMPONENT`：`project_path`、`component_type`、`action`、`instance_name`
- `DELETE_SIMULATION_COMPONENT`：`project_path`、`component_type`、`instance_name`

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

建议先调用 `FetchEvent` 建立流式订阅，再调用 `PerformAction`。下面两个请求使用相同的 `client_uuid`。

### 9.1 新增或更新 SParameter

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-upsert-sp-001",
  "type": "UPSERT_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\",\"parameters\":{\"Start\":{\"value\":\"1\",\"unit\":\"GHz\"},\"Stop\":{\"value\":\"10\",\"unit\":\"GHz\"},\"Step\":{\"value\":\"0.1\",\"unit\":\"GHz\"},\"Pts\":{\"value\":\"101\"}}}"
}
```

如果 Postman 未识别最新枚举，请重新导入 `ecserver.proto`，也可以临时将 `type` 填为数值 `11`。

最终成功事件示例：

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-upsert-sp-001",
  "event_type": "UPSERT_SIMULATION_COMPONENT",
  "status": "RESULT_STATUS_SUCCESS",
  "message": "simulation component created",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\",\"action\":\"created\",\"instance_name\":\"SP1\"}"
}
```

`action` 为 `created` 表示新建器件，为 `updated` 表示更新已有器件。

### 9.2 删除 SParameter

```json
{
  "client_uuid": "postman-test-client-001",
  "task_id": "postman-delete-sp-001",
  "type": "DELETE_SIMULATION_COMPONENT",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\"}"
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
  "message": "simulation component deleted",
  "payload_json": "{\"project_path\":\"C:/test/project.epp\",\"component_type\":\"SParameter\",\"instance_name\":\"SP1\"}"
}
```

如果目标器件不存在，最终事件状态为 `RESULT_STATUS_FAILED`，`message` 会说明对应器件未找到。

## 10. 注意事项

- `client_uuid`、`task_id`、`type` 必须填写。
- `payload_json` 必须是合法 JSON 对象字符串。
- `project_path` 必须是已存在的 `.epp` 文件。
- `UPSERT_SIMULATION_COMPONENT` 的 `parameters` 不能为空。
- `UPSERT_SIMULATION_COMPONENT` 和 `DELETE_SIMULATION_COMPONENT` 的 `component_type` 只接受 `SParameter`、`HarmonicBalance`、`XDB`。
- 仿真器件新增、修改或删除成功后会立即保存工程。
- `MODEL_REPLACE` 必须提供已存在的 `.csv` 文件路径。
- `CAPTURE_SCHEMATIC` 必须提供图片输出路径。
- `CLOSE_PROJECT` 使用 `project_path` 和 `need_save` 关闭工程。
- 同一客户端会话内，提交任务和拉取事件应使用同一个 `client_uuid`。
- `SIMULATE_NETLIST` 的 `netlist_path` 必须是已经存在的文件。
- `SIMULATE_NETLIST` 的 `task_id` 只能包含英文字母、数字、下划线、点和连字符，且不能是 `.` 或 `..`。
- `simulation/<task_id>` 已存在时任务会失败；每次调用应使用新的 `task_id`。
- 独立的 `LOG_EVENT` 暂未支持；仿真器日志通过最终事件的 `ads_output` 返回。
