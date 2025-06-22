#!/usr/bin/env python3

import sys
import os


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from msg_handler import exiterr, info, string


# ==============================================================================
# 语言包测试代码 - 复杂场景
# 1) show_help_info 多行文本带空格
# 2) add_lang_files 多行文本包含"#"
# ==============================================================================
def show_help_info(cmd: str, meta_command: dict):
    """
    string with multiple lines
    """
    if not cmd:
        exiterr(
            """Usage: show_help_info [command]   
        Available commands: find, ls   """
        )

    # 获取 command 对应的内容（模拟 jq .cmd）
    command_info = meta_command.get(cmd)
    if not command_info:
        exiterr(f"Error: Command '{cmd}' not found.")


def add_lang_files(lang_code: str, lang_files: list[str]):
    # 多行模板字符串
    template = string(
        """# {0} 语言包，文档结构：
# 1. 自动处理 bin | lib 目录 sh 文件
# 2. 解析函数 string | info | exiterr | error | success | warning
# 3. key=distinct hash code + position + order
# 4. value=localized string""",
        lang_code,
    )

    # 遍历文件路径，创建文件
    for file in lang_files:
        if not os.path.exists(file):
            with open(file, "w", encoding="utf-8") as f:
                f.write(template + "\n")
            info("{0} 语言文件已创建", file)


def test_same_line_heredoc(lang_code: str, lang_files: list[str]):
    # 多行模板字符串
    template = string(
        """# {0} 语言包，文档结构：
# 1. 自动处理 bin | lib 目录 sh 文件
# 2. 解析函数 string | info | exiterr | error | success | warning
# 3. key=distinct hash code + position + order
# 4. value=localized string""",
        lang_code,
    )

    # 遍历文件路径，创建文件
    for file in lang_files:
        if not os.path.exists(file):
            with open(file, "w", encoding="utf-8") as f:
                f.write(template + "\n")
            info("""{0} test comments """, "{0} 语言文件已创建", file)
