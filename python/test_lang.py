#!/usr/bin/env python3

from pathlib import Path
import sys
import os


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import _mf, exiterr, info, string
from python.i18n import resolve_lang_files
from python.read_util import confirm_action


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


def del_lang_files(lang_code: str, no_prompt: bool = False) -> int:
    """
    删除指定语言代码的语言文件

    Args:
        lang_code: 语言代码
        no_prompt: 是否跳过确认提示，默认False

    Returns:
        int: 返回码，0表示成功
    """
    lang_files = []

    # 获取所有文件路径
    resolve_lang_files(lang_files, lang_code, "0-e")

    # 嵌套删除文件子程序
    def do_del_lang_files():
        delstr = _mf("{0} 语言文件已删除", lang_code)
        # 删除文件
        for file_path in lang_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError as e:
                print(f"删除文件失败: {file_path}, 错误: {e}")

        info(delstr, ignore_translation=True)

    # 如果指定了 no_prompt 为 True，则直接删除文件
    if no_prompt:
        do_del_lang_files()
        return 0

    # 文件存在，提示用户是否删除
    prompt = _mf("确定要删除 {0} 语言文件吗?", lang_code)
    err_msg = _mf("操作已取消，文件未删除")
    confirm_action(prompt, do_del_lang_files, lang_code, lang_files, error_msg=err_msg)

    return 0


def add_lang_files(lang_code: str, lang_files: list[str]):
    # 多行模板字符串
    template = _mf(
        """# {0} 语言包，文档结构：
# 1. 自动处理 bin | lib 目录 sh 文件
# 2. 解析函数 exiterr | error | success | warning | info | string | _mf
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
