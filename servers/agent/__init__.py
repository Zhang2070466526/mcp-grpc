"""Agent 模块 — 实验性功能，不纳入当前正式版本。

当前正式版本为本地 MCP 模式（每台电脑一个 127.0.0.1:8000 服务）。
Agent 模块为未来分布式方案的实验原型：

    - start_servers.py 不导入本模块
    - 不启动 servers.agent.main
    - 不提交 agent_jobs.db

内部结构（实验阶段）：
    main.py                入口
    client.py              公共服务客户端
    registration.py        节点注册
    heartbeat.py           心跳
    executor.py            三池执行器
    operation_registry.py  操作映射
    local_store.py         SQLite
"""

__all__: list[str] = []
