#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
import sys
import locale
import inspect


__all__ = ["string", "_mf"]  # export

sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.hash_util import _djb2_with_salt_20, _padded_number_to_base64, md5
from python.cache.lang_cache import LangCache
from python.json_handler import json_getopt
from python.debug_tool import print_array


# 颜色定义
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
GREEN = "\033[0;32m"
LIGHT_BLUE = "\033[1;34m"  # 亮蓝色
DARK_BLUE = "\033[0;34m"  # 暗蓝色
CYAN = "\033[0;36m"  # 青色 (Cyan)
RED_BG = "\033[41m"  # 红色背景
NC = "\033[0m"  # No Color

# global parameter
LANG_CACHE = LangCache.get_instance()
PARENT_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = (PARENT_DIR / "lib").resolve()


# =============================================================================
# 自动检测语言代码
# =============================================================================
def get_lang_code():
    lang_env = os.environ.get("LANG", "")
    if lang_env:
        return lang_env[:2]
    try:
        return locale.getdefaultlocale()[0][:2]
    except (TypeError, IndexError):
        return "en"


# =============================================================================
# 多语言提示文本
# =============================================================================
LANG_MESSAGES = {
    "zh": {"error": "错误", "success": "成功", "warning": "警告", "info": "信息"},
    "de": {"error": "Fehler", "success": "Erfolg", "warning": "Warnung", "info": "Information"},
    "es": {"error": "Error", "success": "Éxito", "warning": "Advertencia", "info": "Información"},
    "fr": {"error": "Erreur", "success": "Succès", "warning": "Avertissement", "info": "Info"},
    "ja": {"error": "エラー", "success": "成功", "warning": "警告", "info": "情報"},
    "ko": {"error": "오류", "success": "성공", "warning": "경고", "info": "정보"},
}

DEFAULT_MESSAGES = {"error": "ERROR", "success": "SUCCESS", "warning": "WARNING", "info": "INFO"}

# 根据系统语言设置消息文本
LANG_CODE = get_lang_code()
messages = LANG_MESSAGES.get(LANG_CODE, DEFAULT_MESSAGES)

MSG_ERROR = messages["error"]
MSG_SUCCESS = messages["success"]
MSG_WARNING = messages["warning"]
MSG_INFO = messages["info"]


# ==============================================================================
# 函数名: print_stack_err
# 描述: 格式化输出程序调用堆栈，以树状结构展示调用链
# 参数:
#   max_depth - 最大堆栈深度 (默认显示6层，1 <= max_depth <= 9)
#   start_depth - 从第几层开始 (默认从第2层开始)
# 输出:
#   以树状结构格式化的调用堆栈，包含文件名、函数名和行号
# 示例:
# print_stack_err(6, 3)   # 从第3层开始，显示最近6层调用栈
# ==============================================================================
def print_stack_err(max_depth=6, start_depth=2):
    stack = inspect.stack()
    max_depth = min(max_depth, 9, len(stack) - start_depth)
    stack_info = []  # 存储堆栈信息的数组
    max_func_name_len = 0  # 最大函数名长度，用于对齐
    level_funcs = []  # 存储每个级别的所有函数

    # 第一次遍历：收集堆栈信息和确定最大函数名长度
    for depth in range(start_depth, start_depth + max_depth):
        if depth < len(stack):
            frame = stack[depth]
            file = frame.filename
            func = frame.function
            line = frame.lineno

            if not file:
                continue

            # 添加到堆栈信息数组
            stack_info.append(f"{file}:{func}:{line}")

            # 记录函数名长度
            level_funcs.append(func)
            max_func_name_len = max(max_func_name_len, len(func))

    # 计算用于对齐的总宽度（包括函数名和必要空隙）
    align_width = max_func_name_len + 3  # 函数名 + 至少3个空格

    # 第二次遍历：构建和打印树状结构
    result = ["\n"]  # 以空行开始
    files_seen = []
    file_level = {}
    current_level = 0
    last_file = ""
    prefix_map = {}  # 存储每个文件的前缀
    has_more_files = {}  # 标记该级别后面是否还有文件

    # 预处理：找出每个文件在哪个层级，以及该层级后面是否还有文件
    file_count = len(stack_info)
    current_index = 0
    file_level_stack = []

    # 构建一个文件到层级的映射
    for entry in stack_info:
        current_index += 1
        file, func, line = entry.split(":")

        if file not in files_seen:
            files_seen.append(file)

            # 确定文件的层级
            if not last_file:
                file_level[file] = 0
                file_level_stack = [file]
            else:
                # 查看是否需要回溯到之前的层级
                found = False
                for i in range(len(file_level_stack) - 1, -1, -1):
                    if file_level_stack[i] == last_file:
                        file_level[file] = file_level[last_file] + 1
                        file_level_stack.append(file)
                        found = True
                        break

                # 如果不是回溯，就是同级或新层级
                if not found:
                    if last_file:
                        file_level[file] = file_level[last_file]
                        file_level_stack[len(file_level_stack) - 1] = file
                    else:
                        file_level[file] = 0
                        file_level_stack = [file]

            last_file = file

    # 重置变量用于实际打印
    last_file = ""
    func_in_file = []
    current_file = ""
    current_entry = 0

    # 处理堆栈信息以构建树形结构
    for entry in stack_info:
        current_entry += 1
        file, func, line = entry.split(":")

        # 如果是新文件，打印文件节点
        if file != current_file:
            # 结束上一个文件的函数列表
            if current_file:
                # 打印上一个文件中的所有函数
                prefix = prefix_map[current_file]
                file_funcs_count = len(func_in_file)

                for i in range(file_funcs_count):
                    f_name, f_line = func_in_file[i].split(":")
                    connector = "├" if i < file_funcs_count - 1 else "└"
                    result.append(f"{prefix}{connector}── {f_name:{max_func_name_len}} {int(f_line):4d}")

                func_in_file = []

            # 打印新文件节点
            level = file_level[file]
            prefix = ""

            for i in range(level):
                prefix += "    "

            if not last_file:
                result.append(f"└── {file}")
                prefix_map[file] = "    "
            else:
                result.append(f"{prefix}└── {file}")
                prefix_map[file] = prefix + "    "

            current_file = file
            last_file = file

        # 添加函数到当前文件的函数列表
        func_in_file.append(f"{func}:{line}")

    # 打印最后一个文件的函数
    if current_file and func_in_file:
        prefix = prefix_map[current_file]
        file_funcs_count = len(func_in_file)

        for i in range(file_funcs_count):
            f_name, f_line = func_in_file[i].split(":")
            connector = "├" if i < file_funcs_count - 1 else "└"
            result.append(f"{prefix}{connector}── {f_name:{max_func_name_len}} {int(f_line):4d}")

    return "\n".join(result)


# ==============================================================================
# 功能：
# 获取当前执行的函数名和文件名
#
# 输出格式：
# 返回全局变量：CURRENT_FUNCTION | CURRENT_FILE
# ==============================================================================
def get_trans_msg(msg):
    """
    Translate message using global variables

    Args:
        msg (str): Original message

    Returns:
        str: Translated message or original message if translation not found
    """
    global LANG_CACHE, LIB_DIR

    # Get the calling file path
    frame = inspect.currentframe()
    try:
        caller_frame = frame.f_back.f_back.f_back  # Equivalent to BASH_SOURCE[3]
        if caller_frame is None:
            caller_frame = frame.f_back
        source_file = caller_frame.f_code.co_filename
    finally:
        del frame

    # Remove root directory
    if LIB_DIR:
        root_dir = os.path.dirname(LIB_DIR)
        if source_file.startswith(root_dir + "/"):
            source_file = source_file[len(root_dir) + 1 :]

    # Try DJB2 hash first
    current_hash = _djb2_with_salt_20(msg)
    current_hash = _padded_number_to_base64(f"{current_hash}_6")
    key = f"{source_file}:{current_hash}"

    result = LANG_CACHE.get(key)

    if not result:
        # Try MD5
        current_hash = md5(msg)
        key = f"{source_file}:{current_hash}"
        result = LANG_CACHE.get(key)

    if not result:
        result = msg

    return result


def msg_parse_tmpl(template, *args):
    """
    功能：
    template自动合并动态参数(每轮循环，replace the frist{}，和{i}占位符)

    参数：
    template: 带占位符的模板字符串
    *args: 用来替换模板中占位符的参数

    使用示例：
    msg_parse_tmpl("How {0} {1} {0}!", "do", "you")  # => "How do you do!"
    msg_parse_tmpl("How {} {} {0}!", "do", "you")    # => "How do you do!"
    msg_parse_tmpl("How {0} {1} {}!", "do", "you")   # => "How do you do!"

    返回：
    替换占位符后的字符串
    """
    for i, var in enumerate(args):
        template = template.replace("{}", str(var), 1)  # replace the frist {}
        template = template.replace(f"{{{i}}}", str(var))  # replace all {i}

    return template


# ==============================================================================
# 功能：
# 字符串翻译和字符串解析
# 1. 链接自动翻译，获取template
# 2. template自动合并动态参数
# 3. 区分调用者名称，输出不同颜色和风格
#    exiterr：❌ 展示错误消息并退出
#      error：❌ 错误消息
#    success：✅ 成功消息
#    warning：⚠️ 警告消息
#       info：🔷  提示消息
#      string：  普通文本
#
# 参数：
# options - 选项字典
# args - 消息和参数
#
# 选项：
# ignore = i - 忽略翻译
# stack = s - 显示调用栈(测试)
# error = e - 返回错误状态
#
# 使用示例：
# msg_parse_param({}, "How {0} {1} {0}!", "do", "you") ==> "How do you do!"
# msg_parse_param({}, "How are you!") ==> 无需解析
#
# 注意事项：
# 1) 调试只能用print(..., file=sys.stderr) ！！！否则父函数接收返回值时，会出错
# ==============================================================================
def msg_parse_param(options, *args):
    # 自动翻译
    if not json_getopt(options, "ignore"):
        result = get_trans_msg(args[0])  # 获取翻译消息
    else:
        result = args[0]
    template = msg_parse_tmpl(result, *args[1:])  # parse text by template

    # 检查stack参数
    if json_getopt(options, "stack"):
        if len(options["stack"]) == 1:
            print("警告: stack 参数需要2个数字，已自动使用默认值 6 3", file=sys.stderr)
            options["stack"] = [6, 3]
        elif len(options["stack"]) > 2:
            print("警告: stack 参数最多只取前两个数字，多余的已忽略", file=sys.stderr)
            options["stack"] = options["stack"][:2]
        stackerr = print_stack_err(6, 3)  # print stack error (level ≤ 6)
        template += f" {stackerr}"

    # 获取调用者的函数名
    caller_name = inspect.currentframe().f_back.f_code.co_name

    if caller_name in ["exiterr", "error"]:
        print(f"{RED}❌ {MSG_ERROR}: {template}{NC}")
        return 1  # 报错

    if caller_name == "success":
        print(f"{GREEN}✅ {MSG_SUCCESS}: {template}{NC}")
        return 0  # 成功

    if caller_name in ["string", "_mf"]:
        return template  # 转换 normal text (no color)

    if caller_name == "warning":
        print(f"{YELLOW}⚠️ {MSG_WARNING}: {template}{NC}")
    elif caller_name == "info":
        print(f"{LIGHT_BLUE}🔷 {MSG_INFO}: {template}{NC}")

    if json_getopt(options, "error"):
        return 1  # 如有需要，返回错误，供调用者使用
    return 0  # 警告或提示


# 解析命令行选项
def parse_options(args):
    """解析命令行选项并返回字典"""
    options = {}
    remaining_args = []

    i = 0
    while i < len(args):
        arg = args[i]
        if isinstance(arg, str) and arg.startswith("-"):
            if arg == "-i":
                options["i"] = True
            elif arg == "-s":
                options["s"] = True
            elif arg == "-e":
                options["e"] = True
            elif arg == "-o":
                if i + 1 < len(args):
                    options["o"] = args[i + 1]
                    i += 1
                else:
                    options["o"] = True
            else:
                remaining_args.append(arg)
        else:
            remaining_args.append(arg)
        i += 1

    return options, remaining_args


# ==============================================================================
# Auto translation:  exiterr | error | success | warning | info | string | _mf
# 自动翻译 + 解析函数
#
# params:
# ignore = i - 忽略翻译
# stack = s - 显示调用栈(测试)
# error = e - 返回错误状态
# ==============================================================================
def _mf(*args, **kwargs):
    """
    格式化字符串，支持参数替换
    直接返回字符串转换结果
    """
    return msg_parse_param(kwargs, *args)


def string(*args, **kwargs):
    """
    格式化字符串，支持参数替换
    直接返回字符串转换结果
    """
    return msg_parse_param(kwargs, *args)


def exiterr(*args, **kwargs):
    """输出错误消息并退出"""
    msg_parse_param(kwargs, *args)
    # raise typer.Exit(code=1)  # 替代 sys.exit(1)
    sys.exit(1)


def error(*args, **kwargs):
    """输出错误消息(消息种类=1)"""
    return msg_parse_param(kwargs, *args)


def success(*args, **kwargs):
    """输出成功消息(消息种类=0)"""
    return msg_parse_param(kwargs, *args)


def warning(*args, **kwargs):
    """输出警告消息
    返回消息种类（0=非error；1=error）
    """
    return msg_parse_param(kwargs, *args)


def info(*args, **kwargs):
    """输出信息消息
    返回消息种类（0=非error；1=error）
    """
    return msg_parse_param(kwargs, *args)


def parse_args(*args, kwargs):
    """参数解析（标准入口参数处理）"""
    parser = argparse.ArgumentParser(
        description="msg_parse_param 辅助参数解析器",
        formatter_class=argparse.RawTextHelpFormatter,  # 保持帮助文本格式
    )
    # 选项参数（Option Arguments）
    parser.add_argument("-i", "--ignore", action="store_true", help="忽略翻译 (ignore)")  # 标志（Flag）
    parser.add_argument(
        "-s", "--stack", nargs="*", type=int, help="显示调用栈 (stack)，可跟最多2个数字参数，默认6 3\n例如: -s 8 2"
    )
    parser.add_argument("-e", "--error", action="store_true", help="返回错误状态 (error)")  # 标志（Flag）
    # 普通参数（Positional Arguments）
    parser.add_argument("params", nargs="*", help="输入文件路径列表（多个路径通过空格分隔）")

    # 解析预处理后的参数
    args = parser.parse_args(args)

    # 检查stack参数
    if args.stack is not None:
        if len(args.stack) == 1:
            print("警告: -s 参数需要2个数字，已自动使用默认值 6 3", file=sys.stderr)
            args.stack = [6, 3]
        elif len(args.stack) > 2:
            print("警告: -s 参数最多只取前两个数字，多余的已忽略", file=sys.stderr)
            args.stack = args.stack[:2]

    args_dict = vars(args)
    # 分离位置参数和选项参数
    position_args = args_dict.pop("params", [])
    options = args_dict  # 剩余的都是选项参数
    return options, *position_args  # 第一个元素是options，后面是普通变量的拆分


# 用于测试
if __name__ == "__main__":
    string("-i", "这是一个普通字符串: {0}", "测试")
    info("这是一条信息: {0}", "测试信息")
    warning("这是一条警告: {0}", "测试警告")
    success("这是一条成功消息: {0}", "测试成功")
    error("这是一条错误消息: {0}", "测试错误")
    exiterr("这会导致程序退出: {0}", "测试退出")
