# 部署指南 — 打包产物使用 & 智能体对接

> 面向最终用户：如何部署打包好的 `edi-mcp.zip`，以及配置 AI 客户端接入 MCP 服务。
> PyPI：<https://pypi.org/project/edi-mcp/>

---

## 目录结构

解压 `edi-mcp.zip` 到任意目录（以 `C:\EDI` 为例）：

```
C:\EDI\
  EDI.exe                    ← EDI 客户端（自动检测）
  turbocharts_app.exe        ← TurboCharts 图表工具（可选）
  edi-mcp\
    edi_mcp_server.exe       ← MCP 服务主程序（双击运行，无黑框）
    _internal\               ← 依赖库（不要手动修改）
    .env                     ← 配置文件
    start_server.bat         ← 备用手动启动脚本
```

> EDI 和 turbocharts 放在 `edi-mcp/` 同级目录即可，服务自动检测。
> 检测顺序：`EDI.exe` → `EDA-PMDS.exe` → `CAIS.exe`

---

## 配置 .env（可以忽略）

编辑 `edi-mcp\.env`：

```ini
EDA_GRPC_SERVER=127.0.0.1:50055     # gRPC 地址（通常不改）
EDI_PATH=                            # 留空自动检测
TURBOCHARTS_PATH=                    # 留空自动检测
MCP_TRANSPORT=sse                    # sse（Web）或 stdio（本地）
MCP_PORT=50026                       # 监听端口
MCP_HOST=127.0.0.1                   # 监听地址
OPENCLAW_WORKSPACE=C:\Users\JGL\.openclaw\workspace  # copy_image_to_workspace 需要
LLM_API_KEY=sk-xxx                   # 可选：聊天 AI 功能
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

> 留空的字段走自动检测(除OPENCLAW_WORKSPACE)，一般只需确认 `EDA_GRPC_SERVER` 正确。

---

## 启动 & 验证

| 方式 | 操作 |
|---|---|
| 双击运行 | 双击 `edi_mcp_server.exe`（无黑框，后台运行） |
| 命令行 | `cd C:\EDI\edi-mcp && .\edi_mcp_server.exe` |

验证服务状态：

```
http://127.0.0.1:50026/health
```

正常返回：

```json
{"status":"ok","mcp_ready":true,"eda_grpc_ready":true}
```

检查日志：

```
%TEMP%\edi\data\log\edi_mcp_YYYYMM.log
```

---

## 智能体配置

### Claude Code（stdio）

```json
{
  "mcpServers": {
    "eda": {
      "command": "C:/EDI/edi-mcp/edi_mcp_server.exe",
      "args": ["--transport", "stdio"],
      "env": { "EDA_GRPC_SERVER": "127.0.0.1:50055" }
    }
  }
}
```

### OpenClaw（SSE）

配置文件路径：`%USERPROFILE%\.openclaw\workspace\config\mcporter.json`（如 `C:\Users\JGL\.openclaw\workspace\config`）

```json
{
  "mcpServers": {
    "eda-mcp-sse-50026": {
      "baseUrl": "http://127.0.0.1:50026/sse"
    }
  }
}
```

### 其他 SSE 客户端

| 配置项 | 值 |
|---|---|
| 传输方式 | SSE / Streamable HTTP |
| URL | `http://127.0.0.1:50026/sse` |

---

## 验证客户端连接

在聊天界面或 MCP 客户端中直接说：

```
当前你检测到了那些mcp服务，这个mcp服务有那些工具
```

客户端会列出已连接的 MCP 服务，如果出现 `eda-mcp-sse-50026` 就代表连接成功。

---


## OpenClaw 图片显示

`show_image` 始终可用，返回 MCP ImageContent。`copy_image_to_workspace` 仅在 `OPENCLAW_WORKSPACE` 有效时注册，复制到 `media/edi/`，显示由 OpenClaw Agent 消息工具负责。

> 不需要修改 `openclaw.json`，不需要 TOOLS.md，不需要 `[embed]`。

---

## 常见问题

**双击 exe 没反应？**

这是正常现象（无黑框后台运行）。访问 `http://127.0.0.1:50026/health` 确认。如果打不开，命令行运行看错误日志。

**端口被占用？**

```powershell
netstat -ano | findstr 50026
taskkill -f -pid <PID>
```

**gRPC 未就绪？**

确认 EDI 已启动且 50055 在监听：

```powershell
netstat -ano | findstr 50055
```

**图片显示"不在聊天中显示"？**

检查 `.env` 中 `OPENCLAW_WORKSPACE` 是否已配置为有效的 OpenClaw 工作区路径（如 `C:\Users\JGL\.openclaw\workspace`）。打包生成的 `.env` 默认为空，需要手动填写。

**图片显示白屏或 Outside allowed folders？**

不要使用 `[embed]` 或直接发送本地路径。让 Agent 调用 `show_image`，工具会自动复制到工作区并返回 `MEDIA:` 路径。

**如何停止服务？**

```powershell
taskkill -f -im edi_mcp_server.exe
```
