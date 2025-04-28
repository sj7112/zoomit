#!/usr/bin/env python3

from datetime import datetime
import json
import locale
import sys
import os
import argparse
import re
import textwrap

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ast_parser import parse_shell_files
from file_util import (
    copy_file,
    read_config,
    path_resolved,
    read_configs,
    write_file,
    write_files,
)

# 读取环境变量并设置为全局变量，默认值为0
DELETE_MODE = int(os.getenv("DELETE_MODE", 1))  # 0=保留；1=注释；2=删除

SEPARATOR = "@@"
HASH = "hash"
MSGS = "msgs"


def _not_found():
    """输出提示信息 + 时间戳"""
    now = datetime.now()
    timestamp = now.strftime("%-d/%-m/%y %H:%M:%S")  # 对于 Linux/macOS
    # timestamp = now.strftime("%#d/%#m/%y %H:%M:%S")  # 如果是 Windows，使用这行
    return f"# not found {timestamp}"


def load_entries_from_file(filepath):
    """从 JSON 文件加载数据并返回"""
    with open(path_resolved(filepath), "r", encoding="utf-8") as file:
        return json.load(file)  # 使用 json.load() 解析文件内容


def get_locale_code():
    """获取系统语言代码"""
    try:
        return locale.getdefaultlocale()[0]
    except:
        return "en_US"


# =============================================================================
# 识别文件区块并返回序号i
# =============================================================================
def process_file_head(lines, new_lines):
    i = 0
    while i < len(lines):
        line = lines[i]
        match line.strip():
            case "":
                i += 1  # 空行，跳过
            case l if re.match(r"#\s*[^\s]+\.sh$", l):
                return i  # 文件标记行，停止处理
            case _:
                new_lines.append(line)  # 普通行，添加
                i += 1
    return i  # 文件结束


# =============================================================================
# 识别文件区块并返回相关信息
# =============================================================================
def identify_file_section(lines, i, new_lines):
    filename = re.match(r"^#\s*([^\s]+\.sh)$", lines[i]).group(1)
    new_lines.append("")  # 顶部增加一个空行
    new_lines.append(f"# {filename}")

    return i + 1, filename


# =============================================================================
# 跳过不需要处理的文件区块
# =============================================================================
def skip_file_section(lines, i, new_lines):
    while i < len(lines) and not re.match(r"^#\s*[^\s]+\.sh$", lines[i]):
        new_lines.append(lines[i])
        i += 1
    return i


# =============================================================================
# 处理单个文件区块的内容
# =============================================================================
def process_file_section(filename, lines, i, new_lines, lang_data):
    current_section = {}
    for funcname, func_data in lang_data[filename].items():
        current_section[func_data["hash"]] = funcname

    existing_keys = {}
    global DELETE_MODE

    while i < len(lines) and not re.match(r"^#\s*[^\s]+\.sh$", lines[i]):
        line = lines[i]
        i += 1

        # 跳过空行，保持格式整洁
        if not line.strip():
            continue

        # 处理键值行（hash code = value # 注释）
        match = re.match(r"^\s*(\d+)\s*=\s*(.+?)(\s*#.*)?\s*$", line)
        if match:
            key, value, comment = int(match.group(1)), match.group(2), match.group(3) or ""
            if key in existing_keys:
                continue  # 跳过重复的异常记录
            existing_keys[key] = True

            if key in current_section:
                # 存在于新配置中
                new_value = current_section.pop(key, None)  # 获取新值，并从数组中移除
                if comment and comment.lstrip().startswith("# not found "):
                    comment = ""  # 清空自动注释(仅保留自定义注释)
                new_lines.append(f"{key}={new_value}{comment}")
            else:
                # 不存在于新配置中
                match DELETE_MODE:
                    case 0:
                        new_lines.append(f"{key}={value} {_not_found()}")  # 保留整行，尾部添加注释
                    case 1:
                        new_lines.append(f"# {key}={value} {_not_found()}")  # 整行注释，尾部添加注释
                    case 2:
                        pass  # 直接跳过 = 删除
        else:
            if re.match(r"^\s*#", line):
                new_lines.append(line)  # 注释行直接添加

    # 添加剩余新条目
    for key in current_section:
        new_lines.append(f"{key}={current_section[key]}")

    return i


# =============================================================================
# 添加未出现的文件块
# =============================================================================
def add_missing_files(new_lines, processed_file, lang_data):
    # 跳过processed_file
    for filename, file_data in (item for item in lang_data.items() if not processed_file.get(item[0], False)):
        new_lines.append("")  # 增加空行
        new_lines.append(f"# {filename}")  # 增加顶部行
        for func_name, func_data in file_data.items():
            new_lines.append(f"{func_data[HASH]}={func_name}")  # 添加键值对(key=value)


# =============================================================================
# 添加未出现的语言消息块
# =============================================================================
def add_missing_msgs(new_lines, processed_file, lang_data):
    # 跳过processed_file
    for filename, file_data in (item for item in lang_data.items() if not processed_file.get(item[0], False)):
        new_lines.append("")  # 增加空行
        new_lines.append(f"# {filename}")  # 增加顶部行
        for func_name, func_data in file_data.items():
            if MSGS in func_data:
                new_lines.append(f"# {func_data[HASH]}={func_name}")
                for key, msg in func_data[MSGS].items():
                    new_lines.append(f"{key}={msg}")


# =============================================================================
# 主函数：处理语言文件(元数据)
# =============================================================================
def update_meta_properties(meta_file, lang_data):
    counts = [0, 0, 0]
    new_lines = []
    processed_file = {}

    # hash表：文件-函数
    lines = read_config(meta_file)

    # 子程序1：处理头部注释
    i = process_file_head(lines, new_lines)
    while i < len(lines):
        # 子程序2：识别文件标记并返回相关信息
        i, filename = identify_file_section(lines, i, new_lines)

        if not filename in lang_data:
            # 子程序3：跳过不需要处理的文件区块
            i = skip_file_section(lines, i, new_lines)
            counts[0] += 1
        else:
            # 子程序4：处理文件区块内容
            i = process_file_section(filename, lines, i, new_lines, lang_data)
            processed_file[filename] = True  # 设置文件已处理标志
            counts[1] += 1

    # 子程序5：添加未出现的文件块
    add_missing_files(new_lines, processed_file, lang_data)
    counts[2] = len(lang_data)

    # 写文件
    write_file(meta_file, new_lines)

    return counts


# =============================================================================
# 主函数：处理语言文件(指定语言)
# =============================================================================
def update_lang_properties(lang_file, lang_data):
    counts = [0, 0, 0]
    new_lines = []
    processed_file = {}

    # hash表：文件-函数
    lines = read_config(lang_file)

    # 子程序1：处理头部注释
    i = process_file_head(lines, new_lines)
    while i < len(lines):
        # 子程序2：识别文件标记并返回相关信息
        i, filename = identify_file_section(lines, i, new_lines)

        if not filename in lang_data:
            # 子程序3：跳过不需要处理的文件区块
            i = skip_file_section(lines, i, new_lines)
            counts[0] += 1
        else:
            # 子程序4：处理文件区块内容
            i = process_file_section(filename, lines, i, new_lines, lang_data)
            processed_file[filename] = True  # 设置文件已处理标志
            counts[1] += 1

    # 子程序5：添加未出现的文件块
    add_missing_msgs(new_lines, processed_file, lang_data)
    counts[2] = len(lang_data)

    # 写文件
    write_file(lang_file, new_lines)

    return counts


# =============================================================================
# 参数解析（标准入口参数处理）
# =============================================================================
# def parse_args():
#     parser = argparse.ArgumentParser(
#         description="语言属性文件更新工具",
#         formatter_class=argparse.RawTextHelpFormatter,  # 使用RawTextHelpFormatter保留格式
#     )
#     parser.add_argument("--lang", type=str, required=False, help="语言包")
#     parser.add_argument("--file", type=str, required=False, help="待处理文件路径")
#     parser.add_argument(
#         "--delete",
#         type=int,
#         default=0,
#         choices=[0, 1, 2],
#         help=("删除模式: 0=保留 1=注释 2=删除\n" "默认=0"),
#     )
#     parser.add_argument("--debug", action="store_true", help="调试模式")

#     return vars(parser.parse_args())


def parse_args():
    """参数解析（标准入口参数处理）"""
    parser = argparse.ArgumentParser(
        description="语言属性文件更新工具",
        formatter_class=argparse.RawTextHelpFormatter,  # 保持帮助文本格式
    )
    # 选项参数（Option Arguments）
    parser.add_argument("--lang", type=str, required=False, help="语言包")
    parser.add_argument("--file", type=str, required=False, help="待处理文件路径")
    parser.add_argument(
        "--delete",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help=("删除模式: 0=保留 1=注释 2=删除\n" "默认=0"),
    )
    parser.add_argument("--debug", action="store_true", help="调试模式")
    # 普通参数（Positional Arguments）
    parser.add_argument("params", nargs="*", help="输入文件路径列表（多个路径通过空格分隔）")

    # 解析预处理后的参数
    return vars(parser.parse_args())

    # 分离位置参数和选项参数
    # position_args = args_dict.pop("params", [])
    # options = args_dict  # 剩余的都是选项参数
    # return options, *position_args  # 第一个元素是options，后面是普通变量的拆分


# =============================================================================
# 执行逻辑（从STDIN读取数据，调用主函数）
#
# shell调用方法：通过环境变量传参
# DELETE_MODE=1 python lang_util.py
# =============================================================================
def run_exec(opts):
    path = "config/lang/_lang.properties"  # 文件和函数
    lang_files = [
        "/usr/local/shell/config/lang/zh.properties",
        "/usr/local/shell/config/lang/en.properties",
    ]  # 语言消息
    data = parse_shell_files(opts["file"])

    # 初始化测试数据和测试文件
    update_meta_properties(path_resolved(path), data)
    [update_lang_properties(lang_file, data) for lang_file in lang_files]


# =============================================================================
# 调试测试函数（写入测试文件并验证更新逻辑）
# =============================================================================
def print_count(file_name, counts):
    file_name = re.sub(r"^.*?/lang/([^/]+)\.([^/]+)", r"\1", file_name)  # 去掉 /lang/ 之前内容和扩展名
    print(f"skip {file_name} files   = {counts[0]}")
    print(f"update {file_name} files = {counts[1]}")
    print(f"new {file_name} files    = {counts[2]}")


# =============================================================================
# 调试测试函数（写入测试文件并验证更新逻辑）
# =============================================================================
def run_test():
    # # 读取指定sh文件的消息数据，写入到 _lang_test.json 文件
    # data = parse_shell_files(["bin/init_main.sh", "bin/i18n.sh", "bin/cmd_help.sh", "lib/hash_util.sh"])
    # with open("/usr/local/shell/config/lang/_lang_test.json", "w", encoding="utf-8") as f:
    #     json.dump(data, f, ensure_ascii=False, indent=4)  # indent=4 用于美化输出
    print("Debug mode is on. Running tests...")

    # 初始化测试数据和测试文件
    meta_file = copy_file("config/lang/_test2.properties", "config/lang/_test.properties")
    data = load_entries_from_file("config/lang/_test.json")
    lang_files = ["/usr/local/shell/config/lang/zh.properties"]  # 语言消息

    counts = update_meta_properties(meta_file, data)
    print_count(meta_file, counts)

    for lang_file in lang_files:
        counts = update_lang_properties(lang_file, data)
        print_count(lang_file, counts)


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    run_test() if (opts := parse_args())["debug"] else run_exec(opts)
