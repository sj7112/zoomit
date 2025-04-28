#!/usr/bin/env python3

from rich import print as rprint
import sys


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
