#!/usr/bin/env python3

import glob
import os
from pathlib import Path
import pprint
import shutil
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import MSG_ERROR, MSG_WARNING, _mf, error, exiterr, info, warning

# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).resolve().parent.parent
PROP_PATH = PARENT_DIR / "config" / "lang"


def _path_resolve(path_str):
    """Resolve and normalize a path string to a Path object:
    - Absolute path: resolve and return directly
    - Relative path: resolve relative to PARENT_DIR
    """
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    else:
        return (PARENT_DIR / path).resolve()


def path_resolved(path_str, errMsg=_mf("File does not exist")):
    """Resolve path and verify file existence:
    - Returns resolved Path object if file exists
    - Returns None and prints error if file doesn't exist
    """
    src = _path_resolve(path_str)
    # Check if source file exists
    if not src.is_file():
        print(f"[{MSG_ERROR}] {errMsg}: {src}")
        return None
    return src


def write_array(arr, filename="./tests/data.tmp"):
    """
    Write dictionary or list content to specified file

    Args:
        arr: Array, dictionary or object to write
        filename: Output file path, defaults to "./tests/data.tmp"

    If it's a dictionary, use pprint for formatted output
    If it's a list, write each value on a new line
    """
    # Ensure directory exists
    fn = path_resolved(filename)
    # Open file for writing
    with open(fn, "w", encoding="utf-8") as fh:
        if isinstance(arr, dict):
            # If it's a dictionary, use pprint for formatted output
            pprint.pprint(arr, stream=fh)

        elif hasattr(arr, "__dict__"):
            # If it's an object with __dict__ attribute (like Namespace)
            pprint.pprint(arr.__dict__, stream=fh)

        else:
            # If it's a list, write each value on a new line
            for value in arr:
                fh.write(f"{value}\n")


def copy_file(filepath1, filepath2):
    """复制文件 - 用于测试"""
    try:
        dst = _path_resolve(filepath2)
        src = path_resolved(filepath1, _mf("Source file does not exist"))
        if src is None:  # 检查源文件是否存在
            return None

        # 创建目标目录（如果不存在）
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)  # 复制文件（保留元数据）

        return str(dst)  # 或者直接 return dst

    except Exception as e:
        print(f"[{MSG_ERROR}] {_mf('Copy failed')}: {e}")
        return None


def file_backup_sj(*patterns: str, postfix: str = "bak") -> None:
    """
    Generate backup files with .bak suffix (smart duplicate backup prevention)

    Features:
      1. Support wildcard matching and multi-file backup (e.g., *.conf)
      2. Automatically check if source files exist
      3. Automatically skip existing backup files
      4. Preserve original file permissions

    Args:
      *patterns - Source file paths to backup (supports wildcards)

    Raises:
      Exits program if any file backup fails

    Examples:
      file_backup_sj("/etc/apt/sources.list")          # Backup single file
      file_backup_sj("/etc/nginx/*.conf")              # Backup all matching files
      file_backup_sj("/etc/*.conf", "/etc/*.repo")     # Batch backup multiple file types
    """
    # Parameter validation
    if not patterns:
        exiterr("No files specified for backup")

    backup_count = 0
    skip_count = 0
    error_count = 0

    # Process each pattern (may contain wildcards)
    for pattern in patterns:
        # Use glob to find matching files
        matched_files = glob.glob(pattern)

        if not matched_files:
            warning(r"No files found matching {}", pattern)
            continue

        # Process each matching file
        for src_file in matched_files:
            # Ensure it's a regular file
            if not os.path.isfile(src_file):
                continue

            backup_file = f"{src_file}.{postfix}"

            # Check if backup file already exists
            if os.path.exists(backup_file):
                warning(r"Backup file {} already exists, skipping", backup_file)
                skip_count += 1
                continue

            # Perform backup
            try:
                # Use shutil.copy2 to preserve file attributes and permissions
                shutil.copy2(src_file, backup_file)
                print(f"{_mf('Backup created')}: {src_file} -> {backup_file}")
                backup_count += 1
            except (IOError, OSError, PermissionError) as e:
                print(f"{_mf('Unable to create backup file')} {backup_file}: {e}")
                error_count += 1

    # Output statistics
    if error_count > 0:
        exiterr("Important files cannot be backed up")
    elif (backup_count + skip_count + error_count) > 1:
        info(r"Backup completed: {} succeeded, {} skipped, {} failed", backup_count, skip_count, error_count)


def file_restore_sj(src_file: str, postfix: str = "bak") -> None:
    """
    Restore files from .bak suffix backup files

    Features:
      1. Automatically check if source file exists
      2. Preserve original file permissions

    Args:
      src_file - Source file path to restore

    Raises:
      Exits program if file restoration fails
    """
    # Check if backup file exists
    backup_file = f"{src_file}.{postfix}"
    if not os.path.exists(backup_file):
        exiterr(r"Backup file {} does not exist, restoration failed", backup_file)

    # Perform restoration
    try:
        # Use shutil.copy2 to preserve file attributes and permissions
        shutil.copy2(backup_file, src_file)
        print(f"{_mf('File restored')}: {backup_file} -> {src_file}")
    except (IOError, OSError, PermissionError) as e:
        print(f"{_mf('Unable to create backup file')} {src_file}: {e}")


def read_file(fn):
    """Read file content as array"""
    with open(fn, "r", encoding="utf-8") as f:
        return f.read().splitlines()  # Removes newline characters (compatible with Windows/macOS)


def write_source_file(path, lines):
    """Write configuration file content"""
    file_backup_sj(str(path))  # backup file before writing

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        info(r"source file updated: {}", path)
    except Exception as e:
        print(f"{_mf('Write failed')}: {e}")


def read_lang_prop(lang_code):
    """Read configuration file as array"""
    fn = PROP_PATH / f"{lang_code}.properties"
    with open(fn, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return [line.rstrip("\n") for line in lines]


def write_lang_prop(lang_code, content_list):
    """Write configuration file content"""
    fn = PROP_PATH / f"{lang_code}.properties"
    with open(fn, "w", encoding="utf-8") as fh:
        fh.writelines(f"{line}\n" for line in content_list)


def get_filename(file_args):
    """Get filename from parameters and convert to list format"""
    return file_args.split() if isinstance(file_args, str) else file_args


def get_code_files(dir_args, file_ext, file_args=None):
    """
    Get shell file list

    Args:
        file_args: Can be one of the following forms:
                - None (default search bin/lib directories)
                - Single file path string (e.g., "bin/init.sh")
                - List of file paths (e.g., ["bin/a.sh", "lib/b.sh"])

    Returns:
        list: List of valid shell file paths
    """
    ret_files = []

    # 处理指定的文件
    if file_args:
        files = get_filename(file_args)
        for file in files:
            # 使用Path对象处理路径，保持一致性
            path = PARENT_DIR / file
            if path.is_file():
                ret_files.append(str(path))
            else:
                print(f"{_mf(r'[{}]: Code file does not exist', MSG_WARNING)}: {file}", file=sys.stderr)

    # 如果没有指定文件，则搜索默认目录（结果按文件名字母排序）
    else:
        pattern = f"**/*.{file_ext}"
        for dir in dir_args:
            dir_path = PARENT_DIR / dir
            if dir_path.exists():
                ret_files.extend(str(path.resolve()) for path in dir_path.glob(pattern) if path.is_file())

    if not ret_files:
        print(_mf(r"[{}]: No code files found", MSG_ERROR), file=sys.stderr)
        sys.exit(1)

    return ret_files


def read_env_file(filename, section=None):
    """
    初始化环境变量，从 .env 文件读取数据，返回一个二层字典结构
    {
        "network": {...},
        "infrastructure": {...}
    }

    参数:
        filename (str): .env 文件路径
        section (str): 可选，指定要返回的部分（如 "network" 或 "infrastructure"）

    返回:
        dict: 如果指定了 section，则返回对应的部分；否则返回完整的 env_data
    """
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"{filename} not found!")

    env_data = {}
    current_section = None

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                # 检测标题行 (#=xxx)
                if line.startswith("#="):
                    current_section = line[2:].strip()
                    env_data.setdefault(current_section, {})
                continue

            # 拆分键值对
            if "=" in line:
                key, value = map(str.strip, line.split("=", 1))
                if current_section in env_data:
                    env_data[current_section][key] = value

    if section:  # 指定了 section，返回对应部分
        return env_data.get(section, {})

    return env_data  # 未指定 section，返回完整 env_data
