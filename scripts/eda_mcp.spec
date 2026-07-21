# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — EDA MCP 本地服务打包
# 目录模式，对 NumPy/Matplotlib/gRPC 兼容性最好

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).parent

a = Analysis(
    [str(root / 'start_servers.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / 'proto'), 'proto'),
        (str(root / 'scripts' / 'chat_client.html'), 'scripts'),
    ],
    hiddenimports=[
        'servers', 'servers.eda', 'servers.turbocharts',
        'servers.eda.config', 'servers.eda.grpc_client',
        'servers.eda.project_manage', 'servers.eda.simulation',
        'servers.eda.design_export', 'servers.eda.model_replace',
        'servers.eda.project_inspection', 'servers.eda.edi_launcher',
        'servers.registry_server', 'servers.turbocharts.server',
        'servers.turbocharts.runner',
        'proto', 'proto.ecserver_pb2', 'proto.ecserver_pb2_grpc',
        'grpc', 'grpc._cython',
        'matplotlib', 'matplotlib.backends.backend_agg',
        'numpy', 'numpy.core._methods',
        'dotenv',
        'starlette', 'uvicorn', 'uvicorn.loops', 'uvicorn.protocols',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'IPython', 'jupyter', 'notebook',
        'matplotlib.tests', 'numpy.tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='eda-mcp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EDA MCP',
)
