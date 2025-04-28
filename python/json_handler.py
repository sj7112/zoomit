#!/usr/bin/env python3

import os
import json
import re
import sys

# 全局变量
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONF_DIR = os.path.join(os.path.dirname(BIN_DIR), "config")
TESTS_DIR = os.path.join(os.path.dirname(BIN_DIR), "tests")


# 从 config 加载 json 文件
def json_load_data(name):
    """加载指定的JSON配置文件并返回解析后的内容"""
    json_file = os.path.join(CONF_DIR, f"{name}.json")

    # 检查文件是否存在
    if not os.path.isfile(json_file):
        print(f"配置文件不存在: {json_file}", file=sys.stderr)
        return None

    # 读取文件内容并去除注释
    with open(json_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 去除 // 和 /* */ 注释
    content = re.sub(r"//.*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    # 解析并返回JSON数据
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"无法解析JSON文件: {json_file}", file=sys.stderr)
        return None


# 加载命令元数据
META_Command = json_load_data("cmd_meta")


# 获取JSON对象的所有键并用指定分隔符连接
def json_get_keys(json_data, delimiter=","):
    """返回JSON对象中所有键，以指定分隔符连接"""
    if isinstance(json_data, str):
        try:
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            return ""

    if isinstance(json_data, dict):
        return delimiter.join(json_data.keys())
    return ""


def fetch_options(json_str):
    """解析JSON字符串并返回解析后的对象，如果解析失败则退出程序并报错。"""
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            sys.exit("JSON格式错误")
    else:
        sys.exit("JSON格式错误")


def json_getopt(key, options):
    """
    检查选项中是否存在指定键，并判断其值是否为真。
    如果值不是"0"且不是空字符串，则返回True。
    """
    value = options.get(key, "")
    return value != "0" and value != ""


# 检查是否为合法的JSON格式
def json_check(json_str):
    """检查字符串是否为有效的JSON格式"""
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False


# 解析命令行选项
def parse_options(*args, func_name=None):
    """
    解析函数中的命令行选项（Short options & Long options）
    返回解析后的选项字典和剩余参数列表
    """
    # 从调用栈获取函数名，如果未提供
    if not func_name:
        import inspect

        frame = inspect.currentframe().f_back
        func_name = frame.f_code.co_name

    # 从META_Command中提取选项定义
    options_def = None
    try:
        options_def = META_Command.get(func_name, {}).get("options", [])
        if not options_def:
            print(f"检查 META_Command 未包含 {func_name} 格式", file=sys.stderr)
            return {}, args
    except (AttributeError, KeyError):
        print(f"检查 META_Command 未包含 {func_name} 格式", file=sys.stderr)
        return {}, args

    parsed_options = {}  # 解析后的字典
    short_opts_map = {}  # 短选项名 -> 布尔值（用于检查是否为有效选项）
    long_opts_map = {}  # 长选项名 -> 布尔值（用于检查是否为有效选项）
    long_to_json_key = {}  # 长选项名 -> JSON键名

    # 填充映射表并初始化 parsed_options
    for opt in options_def:
        key = opt["key"]
        long_opt = opt.get("long", "")

        if key.startswith("-") and len(key) == 2:
            # 短选项
            json_key = key[1:]  # 去除前缀"-"
            short_opts_map[json_key] = True

            if long_opt:
                long_key = long_opt[2:]  # 去除前缀"--"
                long_opts_map[long_key] = True
                long_to_json_key[long_key] = json_key
                parsed_options[json_key] = ""  # 默认值为空字符串
            else:
                parsed_options[json_key] = 0  # 默认值为0
        else:
            # 长选项
            json_key = key[2:]  # 去除前缀"--"
            long_opts_map[json_key] = True
            parsed_options[json_key] = ""  # 默认值为空字符串

    # 解析参数
    new_args = []
    i = 0
    while i < len(args):
        arg = args[i]

        # 处理长选项
        if arg.startswith("--"):
            if "=" in arg:
                key, value = arg.split("=", 1)
                key = key[2:]  # 去除前缀"--"
            else:
                key = arg[2:]
                value = "1"  # 默认为1

            json_key = long_to_json_key.get(key, key)

            if json_key in long_opts_map or json_key in parsed_options:
                parsed_options[json_key] = value
            else:
                print(f"警告: 未知选项 {arg}", file=sys.stderr)

        # 处理短选项
        elif arg.startswith("-") and not arg.startswith("--"):
            short_opt = arg[1:]  # 去除前缀"-"

            # 处理每个字符
            for char in short_opt:
                if char in short_opts_map:
                    parsed_options[char] = 1
                else:
                    print(f"警告: 未知选项 -{char}", file=sys.stderr)

        # 非选项参数
        else:
            new_args.append(arg)

        i += 1

    return parsed_options, new_args


# JSON操作函数 - 简化版本
def json_get(data, path=None):
    """获取JSON对象中指定路径的值"""
    if not path:
        return data

    parts = path.split(".")
    current = data

    try:
        for part in parts:
            current = current[part]
        return current
    except (KeyError, TypeError):
        return None


def json_set(data, path, value):
    """设置JSON对象中指定路径的值"""
    if not data:
        data = {}

    parts = path.split(".")
    current = data

    # 导航到最后一层之前的所有路径
    for i in range(len(parts) - 1):
        part = parts[i]
        if part not in current:
            current[part] = {}
        current = current[part]

    # 设置最后一个键的值
    current[parts[-1]] = value
    return data


def json_delete(data, path=None):
    """删除JSON对象中指定路径的键"""
    if not path:
        return {}

    parts = path.split(".")
    current = data

    # 导航到最后一层之前的所有路径
    try:
        for i in range(len(parts) - 1):
            part = parts[i]
            current = current[part]

        # 删除最后一个键
        if parts[-1] in current:
            del current[parts[-1]]
    except (KeyError, TypeError):
        pass  # 路径不存在，不做任何改变

    return data


def json_check_path(data, path):
    """检查JSON对象中是否存在指定路径"""
    parts = path.split(".")
    current = data

    try:
        for part in parts:
            current = current[part]
        return True
    except (KeyError, TypeError):
        return False


# 对外提供的统一接口
def json1(cmd, *args):
    """
    统一的JSON操作接口
    用法:
      my_json = json('new', '{"user":{"name":"John"}}')
      my_json = json('set', my_json, "user.address.city", "New York")
      result = json('get', my_json)
      city = json('get', my_json, "user.address.city")
    """
    if cmd == "new":
        initial = args[0] if args else "{}"
        try:
            return json.loads(initial) if isinstance(initial, str) else initial
        except json.JSONDecodeError:
            print("错误: 无效的初始JSON", file=sys.stderr)
            return {}

    elif cmd == "set":
        data = args[0]
        path = args[1]
        value = args[2] if len(args) > 2 else None
        return json_set(data, path, value)

    elif cmd == "get":
        data = args[0]
        path = args[1] if len(args) > 1 else None
        return json_get(data, path)

    elif cmd == "delete":
        data = args[0]
        path = args[1] if len(args) > 1 else None
        return json_delete(data, path)

    elif cmd == "check":
        data = args[0]
        path = args[1]
        return json_check_path(data, path)


# 如果作为独立脚本运行，可以添加简单的示例测试
if __name__ == "__main__":
    # 示例：创建新的JSON
    sample_json = json.loads('{"user":{"name":"张三"}}')
    print("初始JSON:", sample_json)

    # 示例：设置值
    sample_json = json("set", sample_json, "user.address.city", "北京")
    print("设置后:", sample_json)

    # 示例：获取值
    city = json("get", sample_json, "user.address.city")
    print("获取city:", city)

    # 示例：检查路径
    exists = json_check_path(sample_json, "user.address.city")
    print("路径存在:", exists)

    # 示例：删除值
    sample_json = json("delete", sample_json, "user.address")
    print("删除后:", sample_json)
