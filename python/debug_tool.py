#!/usr/bin/env python3

import os
from typing import Any, List
from rich import print as rprint
import sys
import typer


def create_app(**kwargs: Any) -> typer.Typer:
    """
    创建并配置 Typer 应用，默认只在帮助模式下启用 Rich 格式输出

    Args:
        **kwargs: 传递给 typer.Typer 的参数

    Returns:
        配置好的 Typer 应用实例
    """
    # 检查是否为帮助模式
    help_mode = any(arg in ["--help", "-h"] for arg in sys.argv[1:])

    # 设置默认参数
    defaults = {
        "pretty_exceptions_enable": False,
        "pretty_exceptions_show_locals": False,
        "rich_markup_mode": "rich" if help_mode else None,
    }
    # 如果不是 help 模式，关闭 rich 异常格式化
    if not help_mode:
        # 这个环境变量会被Click使用，但不足以完全禁用Typer的Rich格式
        os.environ["CLICK_EXCEPTION_FORMAT"] = "plaintext"

    # 仅当用户未指定时应用默认值
    for key, value in defaults.items():
        kwargs.setdefault(key, value)

    return typer.Typer(**kwargs)


def default_cmd(default: str, commands: List[str]) -> None:
    """
    检查命令行参数，如果没有指定已知的子命令，则插入默认命令

    Args:
        default: 默认命令名称
        commands: 所有可用命令的列表
    """
    # 检查是否有子命令
    has_command = False

    # 检查首个参数是否为已知子命令
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        if sys.argv[1] in commands:
            has_command = True

    # 如果没有子命令，默认插入指定的默认命令
    if not has_command:
        sys.argv.insert(1, default)


def print_array(arr):
    """
    打印字典或列表的内容
    如果是字典，rich自动处理复杂数据结构
    如果是列表，打印索引和对应的值
    """
    if isinstance(arr, dict):
        # 如果是字典，打印键值对
        rprint(arr, file=sys.stderr)
    elif hasattr(arr, "__dict__"):
        # 如果是具有__dict__属性的对象（如Namespace）
        rprint(arr.__dict__, file=sys.stderr)
    else:
        # 如果是列表，打印索引和值
        for key, value in enumerate(arr):
            print(f"{key}: {value}", file=sys.stderr)


def test_assertion(condition, message):
    """
    断言测试并彩色输出结果函数

    参数:
        condition: 条件表达式
        message: 结果消息
    """
    # 绿色和红色的ANSI转义码
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    NC = "\033[0m"  # No Color

    # 在try外部初始化为None
    caller_frame = None

    try:
        # 检查condition是否为可调用对象(lambda或函数)
        if callable(condition):
            result = condition()  # 直接调用函数
        else:
            # 如果是字符串表达式，则使用eval
            import inspect  # 获取调用者的栈帧

            caller_frame = inspect.currentframe().f_back
            caller_locals = caller_frame.f_locals  # 获取调用者的局部变量
            result = eval(condition, globals(), caller_locals)

        if result:
            print(f"{GREEN}true{NC} ====> {message}")
            return True
        else:
            print(f"{RED}false{NC} ====> {message}")
            return False
    except Exception as e:
        print(f"{RED}error{NC} ====> {message} ({e})")
        return False
    finally:
        # 当caller_frame被定义时清理引用，避免内存问题
        if caller_frame is not None:
            del caller_frame
