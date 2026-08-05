"""共享图片校验 — 供 display / workspace / analyze 复用。"""

from __future__ import annotations

from pathlib import Path

# 允许的图片扩展名
_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def validate_image_path(image_path: str, allowed: set[str] | None = None) -> Path:
    """校验图片路径和扩展名，通过则返回 resolved Path。

    Args:
        image_path: 图片路径。
        allowed: 允许的扩展名集合（默认使用全部支持格式）。

    Raises:
        PermissionError: 网络路径。
        FileNotFoundError: 文件不存在。
        ValueError: 不支持的扩展名。
    """
    exts = allowed or _ALLOWED_EXTENSIONS
    path = Path(image_path).expanduser().resolve()
    if str(path).startswith(r"\\") or str(path).startswith("//"):
        raise PermissionError(f"禁止访问网络路径: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")
    if path.suffix.lower() not in exts:
        raise ValueError(f"不支持的图片格式: {path.suffix}")
    return path


def validate_image_content(path: Path) -> None:
    """用 Pillow 验证文件是否为有效图片。

    Raises:
        ValueError: 不是有效图片。
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
    except Exception as e:
        raise ValueError(f"无法解析为有效图片: {path}") from e
