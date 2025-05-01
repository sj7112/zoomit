#!/usr/bin/env python3

from pathlib import Path
import shutil
import sys
from ruamel.yaml import YAML

# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).parent.parent.resolve()

YML_PATH = "/usr/local/shell/config/lang/_lang.yml"


def _path_resolve(path_str):
    """根据是否为绝对路径，返回一个标准化后的 Path 对象：
    - 绝对路径：直接返回
    - 相对路径：以当前脚本目录为基准拼接
    """
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    else:
        return (PARENT_DIR / path).resolve()


def path_resolved(path_str, errMsg="文件不存在"):
    """根据是否为绝对路径，返回一个标准化后的 Path 对象：
    - 绝对路径：直接返回
    - 相对路径：以当前脚本目录为基准拼接
    """
    src = _path_resolve(path_str)
    # 检查源文件是否存在
    if not src.is_file():
        print(f"❌ {errMsg}: {src}")
        return None
    return src


def copy_file(filepath1, filepath2):
    """复制文件 - 用于测试"""
    try:
        dst = _path_resolve(filepath2)
        src = path_resolved(filepath1, "源文件不存在")
        if src is None:  # 检查源文件是否存在
            return None

        # 创建目标目录（如果不存在）
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)  # 复制文件（保留元数据）

        return str(dst)  # 或者直接 return dst

    except Exception as e:
        print(f"❌ 复制失败: {e}")
        return None


def read_config(fn):
    """读取配置文件为数组"""
    with open(fn, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return [line.rstrip("\n") for line in lines]


def read_lang_yml():
    """读取yml语言文件为字典"""
    yaml = YAML()  # 处理yaml文件
    with open(YML_PATH, "r") as f:
        data = yaml.load(f)  # 读yaml

    return data, yaml


def write_lang_yml(data, yaml):
    """读取yml语言文件为字典"""
    with open(YML_PATH, "w") as f:
        yaml.dump(data, f)


def write_config(fn, content_list):
    """写入配置文件内容"""
    with open(fn, "w", encoding="utf-8") as fh:
        fh.writelines(f"{line}\n" for line in content_list)


def get_filename(file_args):
    """从参数中获取文件名，转为列表形式"""
    return file_args.split() if isinstance(file_args, str) else file_args


def get_shell_files(file_args=None):
    """
    获取shell文件列表

    Args:
        file_args: 可以是以下形式之一：
                  - None（默认搜索bin/lib目录）
                  - 单个文件路径字符串（如"bin/init.sh"）
                  - 文件路径列表（如["bin/a.sh", "lib/b.sh"]）

    Returns:
        list: 有效的shell文件路径列表
    """
    sh_files = []

    # 处理指定的文件
    if file_args:
        files = get_filename(file_args)
        for file in files:
            # 使用Path对象处理路径，保持一致性
            path = PARENT_DIR / file
            if path.is_file():
                sh_files.append(str(path))
            else:
                print(f"警告: 文件不存在: {file}", file=sys.stderr)

    # 如果没有指定文件，则搜索默认目录
    else:
        for dir in ["bin", "lib"]:
            dir_path = PARENT_DIR / dir
            if dir_path.exists():
                sh_files.extend(str(path.resolve()) for path in dir_path.glob("**/*.sh") if path.is_file())

    if not sh_files:
        print("错误: 没有找到任何shell脚本文件", file=sys.stderr)
        sys.exit(1)

    return sh_files
