"""
MD5处理模块 - 用于知识库系统的文件去重
功能：生成MD5、检查是否已处理、保存处理记录
"""

import os
import hashlib
import logging
import servers.knowledge.config as config

logger = logging.getLogger(__name__)


def get_string_md5(input_str: str, encoding: str = 'utf-8') -> str:
    """
    将传入的字符串转换为MD5十六进制字符串

    Args:
        input_str: 待转换的字符串
        encoding: 编码方式，默认utf-8

    Returns:
        str: 32位MD5十六进制字符串

    Examples:
        >>> get_string_md5("hello")
        '5d41402abc4b2a76b9719d911017c592'
    """
    # 字符串 → 字节数组
    str_bytes = input_str.encode(encoding=encoding)

    # 计算MD5
    md5_obj = hashlib.md5()
    md5_obj.update(str_bytes)
    md5_hex = md5_obj.hexdigest()

    return md5_hex


def get_file_md5(file_path: str, chunk_size: int = 8192) -> str:
    """
    计算文件的MD5值（适用于大文件，逐块读取）

    Args:
        file_path: 文件路径
        chunk_size: 每次读取的字节数，默认8KB

    Returns:
        str: 32位MD5十六进制字符串

    Raises:
        FileNotFoundError: 文件不存在时抛出

    Examples:
        >>> get_file_md5("./data/document.pdf")
        'a1b2c3d4e5f6...'
    """
    # 校验文件存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 初始化 MD5 对象
    md5_obj = hashlib.md5()
    # 以二进制模式逐块读取，避免大文件一次性读入内存
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)   # 每次读 chunk_size 字节
            if not chunk:
                break                    # 读到文件末尾
            md5_obj.update(chunk)        # 增量更新 MD5

    return md5_obj.hexdigest()


def check_md5(md5_str: str) -> bool:
    """
    检查传入的MD5字符串是否已经被处理过了

    Args:
        md5_str: 待检查的MD5字符串

    Returns:
        bool: True=已处理过，False=未处理过

    Examples:
        >>> if check_md5("5d41402abc4b2a76b9719d911017c592"):
        ...     print("已处理过")
        ... else:
        ...     print("未处理过")
    """
    # 确保记录文件存在
    if not os.path.exists(config.md5_path):
        # 创建空文件
        with open(config.md5_path, 'w', encoding='utf-8') as f:
            pass
        return False

    # 逐行读取并匹配
    with open(config.md5_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line == md5_str:
                return True

    return False


def save_md5(md5_str: str) -> bool:
    """
    将传入的MD5字符串记录到文件内保存

    Args:
        md5_str: 待保存的MD5字符串

    Returns:
        bool: True=保存成功，False=保存失败

    Examples:
        True
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(config.md5_path), exist_ok=True)

        # 追加写入
        with open(config.md5_path, 'a', encoding='utf-8') as f:
            f.write(md5_str + '\n')
        return True
    except Exception as e:
        logger.error("保存MD5失败: %s", e)
        return False


def check_and_save_md5(content: str) -> bool:
    """
    检查内容是否已处理，如果未处理则自动保存（组合函数）

    Args:
        content: 待检查的文本内容

    Returns:
        bool: True=已存在（跳过），False=是新内容（已保存）

    Examples:
        >>> if check_and_save_md5("这是新内容"):
        ...     print("内容已存在，跳过处理")
        ... else:
        ...     print("新内容，开始处理")
    """
    # 先计算内容 MD5
    md5_value = get_string_md5(content)

    # 已存在则跳过（返回 True 表示「已处理」）
    if check_md5(md5_value):
        return True

    # 新内容：保存 MD5 记录，返回 False 表示「是新内容」
    save_md5(md5_value)
    return False


