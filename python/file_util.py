#!/usr/bin/env python3

import os
from pathlib import Path
import pprint
import shutil
import sys
from ruamel.yaml import YAML

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


from debug_tool import print_array

# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).parent.parent.resolve()

PROP_PATH = "/usr/local/shell/config/lang/"
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


def print_array(arr, filename="./tests/data.tmp"):
    """
    将字典或列表的内容写入到指定文件中

    参数:
        arr: 要写入的数组、字典或对象
        filename: 输出文件路径，默认为"./tests/data.tmp"

    如果是字典，使用pprint格式化输出
    如果是列表，写入索引和对应的值
    """
    # 确保目录存在
    fn = path_resolved(filename)
    # 打开文件进行写入
    with open(fn, "w", encoding="utf-8") as fh:
        if isinstance(arr, dict):
            # 如果是字典，使用pprint格式化输出
            pprint.pprint(arr, stream=fh)

        elif hasattr(arr, "__dict__"):
            # 如果是具有__dict__属性的对象（如Namespace）
            pprint.pprint(arr.__dict__, stream=fh)

        else:
            # 如果是列表，写入索引和值
            for value in arr:
                fh.write(f"{value}\n")


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


def read_file(fn):
    """读取文件内容为数组"""
    with open(fn, "r", encoding="utf-8") as f:
        return f.read().splitlines()  # 去掉换行符（兼容windows、macos）


def read_lang_prop(lang_code):
    """读取配置文件为数组"""
    fn = PROP_PATH + lang_code + ".properties"
    with open(fn, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return [line.rstrip("\n") for line in lines]


def write_lang_prop(lang_code, content_list):
    """写入配置文件内容"""
    fn = PROP_PATH + lang_code + ".properties"
    with open(fn, "w", encoding="utf-8") as fh:
        fh.writelines(f"{line}\n" for line in content_list)


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

    # 如果没有指定文件，则搜索默认目录（结果按文件名字母排序）
    else:
        for dir in ["bin", "lib"]:
            dir_path = PARENT_DIR / dir
            if dir_path.exists():
                sh_files.extend(str(path.resolve()) for path in dir_path.glob("**/*.sh") if path.is_file())

    if not sh_files:
        print("错误: 没有找到任何shell脚本文件", file=sys.stderr)
        sys.exit(1)

    return sh_files


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
