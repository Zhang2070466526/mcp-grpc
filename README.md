# EDA MCP 服务

将 EDA-PMDS/EDI 的 gRPC 接口和本地命令行工具封装为 MCP 服务，
支持 **stdio** 和 **Streamable HTTP** 两种传输方式，
使 AI 客户端能通过自然语言操作 EDA 工程。

---

## 快速开始

### 安装

```powershell
uv sync
```

### 配置

所有配置集中在 `.env`：

```ini
EDA_GRPC_SERVER=127.0.0.1:50055       # gRPC 服务地址
EDI_PATH=C:\Program Files (x86)\EDI\EDI.exe
TURBOCHARTS_PATH=C:\Program Files (x86)\EDI\turbocharts_app.exe
MCP_TRANSPORT=streamable-http         # stdio | streamable-http
MCP_HOST=127.0.0.1                    # 0.0.0.0 为局域网可访问
MCP_PORT=8000
```

### 前置条件

- EDA gRPC 服务可用：`netstat -ano | findstr 50055`
- `.epp` 工程文件存在
- turbocharts 功能需要 `turbocharts_app.exe`

### 启动

```powershell
cd D:\GitLabCode\mcp-grpc

# Streamable HTTP 模式（OpenClaw / Web 客户端，默认）
uv run python start_servers.py

# stdio 模式（桌面客户端）
uv run python start_servers.py --transport stdio

# 自定义端口
uv run python start_servers.py --port 9000
```

---

## 客户端对接

### Claude Code

`.mcp.json` 已配置，`/mcp` 重载即生效。

### OpenClaw / Web 客户端

| 字段 | 值 |
|---|---|
| 名称 | `eda` |
| 传输方式 | Streamable HTTP |
| URL | `http://127.0.0.1:8000/mcp` |

### 其他 MCP 客户端

```json
{
  "mcpServers": {
    "eda": {
      "command": "uv",
      "args": [
        "--directory", "D:/GitLabCode/mcp-grpc",
        "run", "python", "start_servers.py",
        "--transport", "stdio"
      ],
      "env": { "EDA_GRPC_SERVER": "127.0.0.1:50055" }
    }
  }
}
```

### 对外提供服务（局域网共享）

1. `.env` 中设置 `MCP_HOST=0.0.0.0`
2. 启动服务：`uv run python start_servers.py`
3. 防火墙放行 `MCP_PORT`（默认 8000）
4. 查看本机 IP：`ipconfig | findstr IPv4`
5. 其他人配置 `http://<你的IP>:8000/mcp`

---

## 工具参考

| 工具 | 功能 | 必填参数 | 可选参数 |
|---|---|---|---|---|
| `list_epp_projects` | 扫描文件夹，列出所有 .epp 工程 | `folder_path` | 无 |
| `open_eda_project` | 打开 .epp 工程 | `project_path` | `timeout_seconds`（>0，默认 60） |
| `view_project_netlist` | 查看/导出工程网表 | `project_path` | `timeout_seconds`（>0，默认 60） |
| `simulate_project` | 执行工程仿真 | `project_path` | `log_source`、`timeout_seconds`（默认 120，无上限） |
| `capture_schematic` | 截取工程原理图为图片 | `project_path`、`img_path` | `timeout_seconds`（默认 60） |
| `model_replace` | 按 CSV 批量替换模型 | `project_path`、`csv_path` | `timeout_seconds`（默认 60） |
| `close_project` | 关闭工程 | `project_path` | `need_save`（默认 false）、`timeout_seconds` |
| `call_simulation_controller` | 调用 ADS 仿真控制器 | `netlist_path` | `ads_path`、`timeout_seconds`（默认 120，无上限） |
| `launch_edi` | 启动 EDI 客户端，等待 gRPC 就绪 | 无 | `edi_path`、`wait_for_grpc`、`wait_timeout` |
| `turbocharts_convert` | ADS RAW → 曲线图 + CSV | `raw_path`、`img_path`、`chart_type` | `csv_path`、`linename`、`dependency`、`ac_config` |

使用示例：

```
帮我看看 C:\Users\JGL\EDI-Workspace 下面有哪些 .epp 工程
帮我启动 EDI
帮我打开 EDA 工程 C:\Users\JGL\EDI-Workspace\EDI_TEST\EDI_TEST.epp
帮我查看这个工程的网表
帮我对这个工程执行仿真
帮我把 result_tr.raw 转成 S 参数增益曲线图，输出 gain.png，曲线 DB_S[2,1]，依赖轴 freq
```

### turbocharts_convert 参数详解

**chart_type**：`SP`（S参数）、`HB`（谐波平衡）、`XDB`

**linename** — 曲线名，格式 `单位_曲线名[端口]`，多条用 `&` 分隔：

| 曲线 | 说明 | 曲线 | 说明 |
|---|---|---|---|
| `DB_S[2,1]` | S参数输出增益 | `DB_S[1,2]` | S参数反向增益 |
| `real_nf(1)` | 噪声系数 | `VSWR_S[1,1]` | 输入驻波 |
| `real_delayS[2,1]` | 群时延 | `APS_S[2,1]` | 衰减器附加相移 |
| `MAS_S[2,1]` | 移相器衰减态 | `MV_S[2,1]` | 移相器幅度波动 |
| `PSS_S[2,1]` | 移相器移相态 | | |

**ac_config** — 精度配置，格式 `ac_type#bit#data#nv_type#nv_value`：

| 字段 | 说明 | 示例值 |
|---|---|---|
| `ac_type` | 精度类型 | `phase`（相位）/ `att`（衰减） |
| `bit` | 精度位数 | `3` |
| `data` | 曲线名称 | `S[2,1]` |
| `nv_type` | 取值方式 | `fv`（固定间隔）/ `cl`（完整列表） |
| `nv_value` | 取值 | `0.1`（fv）/ `0.1,0.2,0.3`（cl） |

示例：`"phase#3#S[2,1]#fv#0.1"`

---

## 项目结构

```
├── proto/                         # protobuf 协议文件
│   ├── ecserver.proto
│   ├── ecserver_pb2.py
│   └── ecserver_pb2_grpc.py
├── servers/                       # MCP 服务模块
│   ├── registry_server.py         # 工具注册中心（加工具只改这个）
│   ├── eda/
│   │   ├── config.py              # 公用函数与配置
│   │   ├── grpc_client.py         # gRPC 通信层
│   │   ├── project_service.py     # 工程管理（3 个工具）
│   │   ├── simulation_service.py  # 仿真（2 个工具）
│   │   ├── analysis_service.py    # 分析（2 个工具）
│   │   ├── model_service.py       # 模型替换（1 个工具）
│   │   └── edi_launcher.py        # 启动工具（1 个工具）
│   └── turbocharts/
│       └── server.py              # RawConverter 工具（1 个）
├── start_servers.py               # 一键启动入口
├── .mcp.json                      # Claude Code 配置
├── .env                           # 环境变量（唯一配置来源）
└── pyproject.toml                 # uv 项目配置
```

---

## 常见问题

### 端口被占用

```powershell
# 查看端口占用
netstat -ano | findstr 8000

# 关闭占用端口的进程（替换 PID 为实际值）
taskkill -f -pid <PID>
```

### 检查 gRPC 服务是否运行

```powershell
netstat -ano | findstr 50055
# 有 LISTENING 输出 = 运行中，无输出 = 未启动
```

### 检查 EDI 是否在运行

```powershell
tasklist | findstr EDI.exe
```

### 启动失败

- 确认 `.env` 配置正确：`EDA_GRPC_SERVER`、`EDI_PATH`、`TURBOCHARTS_PATH`
- 确认虚拟环境已安装：`uv sync`
- 确认 EDA gRPC 服务已启动

---

## 注意事项

- `project_path` 必须是存在的 `.epp` 文件
- `timeout_seconds` 必须 > 0，无上限
- stdio 模式下不要向 stdout 输出调试信息
- `.env` 配置在服务启动时自动加载

---

## 开发

### 添加新工具

1. EDA gRPC 方向：在 `servers/eda/server.py` 中按模板添加 `@mcp.tool()` 函数，调用 `call_grpc()`
2. 新方向：在 `servers/` 下新建子包，创建 `server.py`
3. 在 `servers/registry_server.py` 中 import 并注册

### 重新生成 proto

```powershell
python -m grpc_tools.protoc -I proto --python_out=proto --grpc_python_out=proto proto/ecserver.proto
# 编辑 proto/ecserver_pb2_grpc.py 第 5 行：
# import ecserver_pb2 → from proto import ecserver_pb2
```

### 相关文档

- [交接文档](./HANDOVER.md) — 架构、技术栈、通信流程、已知问题
- [接口汇总](./EDI系统接口与外部调用汇总.md) — EDI 全量接口文档
