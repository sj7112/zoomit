#!/usr/bin/env python3

import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import typer


# 设置默认路径
PARENT_DIR = Path(__file__).parent.parent.resolve()
LIB_DIR = (PARENT_DIR / "lib").resolve()
CONF_DIR = (PARENT_DIR / "config").resolve()
LANG_DIR = (CONF_DIR / "lang").resolve()

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lang_util import debug_assertion, update_lang_files
from msg_handler import string, info, warning, error, exiterr, get_lang_code
from debug_tool import create_app, default_cmd, print_array
from file_util import print_array as file_print_array
from system import confirm_action

# 确保目录存在
os.makedirs(LANG_DIR, exist_ok=True)


def resolve_lang_files(lang_code: str, mode: str = "", max_files: int = 1) -> List[str]:
    """找到多个语言文件路径，并进行存在性检查

    Args:
        lang_code: 语言代码（如 zh_CN）
        mode: 报错条件（-：文件不存在报错；+：文件存在报错；e:报错；w:警告；i:提示）
              - "0-e": 一个文件都不存在
              - "1-e": 至少一个文件不存在
              - "1+e": 至少一个文件存在
              - "2+e": 所有文件都存在
        max_files: 最大文件数量

    Returns:
        包含所有语言文件路径的列表, 提示消息的返回值（0=正常；1=出错）
    """
    # 生成文件路径列表
    lang_files = []
    lang_files.append(os.path.join(LANG_DIR, f"{lang_code}.properties"))  # 第一个文件没有数字后缀

    for i in range(1, max_files):
        lang_files.append(os.path.join(LANG_DIR, f"{lang_code}_{i+1}.properties"))

    if not mode:
        return lang_files

    # 判断调用函数
    func = None
    if "e" in mode:
        func = error
    elif "w" in mode:
        func = lambda msg: warning(msg, error=True)
    elif "i" in mode:
        func = lambda msg: info(msg, error=True)
    else:
        exiterr(string("模式参数错误 {0}", mode))

    # 检查文件存在性
    any_exists = any(os.path.isfile(file) for file in lang_files)
    all_exist = all(os.path.isfile(file) for file in lang_files)

    exist_msg = string("{0} 语言文件已存在", lang_code, ignore=True)
    notexist_msg = string("{0} 语言文件不存在", lang_code)

    # 执行报错逻辑
    result = 0
    if mode.startswith("0-") and not any_exists:
        result = func(notexist_msg)
    elif mode.startswith("1-") and not all_exist:
        result = func(notexist_msg)
    elif mode.startswith("1+") and any_exists:
        result = func(exist_msg)
    elif mode.startswith("2+") and all_exist:
        result = func(exist_msg)

    return lang_files, result


def resolve_lang_codes() -> List[str]:
    """解析语言文件，提取语言代码并返回列表"""
    lang_codes = []

    # 查找所有 .properties 文件
    for file in Path(LANG_DIR).glob(".*.properties"):
        match = re.search(r"/\.([a-zA-Z_]+)\.properties$", str(file))
        if match:
            lang_codes.append(match.group(1))

    return lang_codes


def get_lang_files(langs: List[str] = None) -> Tuple[List[str], List[str]]:
    """处理语言文件

    Args:
        lang_code: 指定语言代码，为空则获取所有

    Returns:
        (lang_codes, lang_files): 语言代码列表和文件路径列表
    """
    lang_codes = []

    if langs:
        lang_codes.extend(langs)
    else:
        lang_codes.extend(resolve_lang_codes())

    ret_langs = add_lang_files(lang_codes, False)
    if not ret_langs:
        exiterr("请先添加语言文件")

    # 返回语言文件列表
    # lang_files = [file for _, files in ret_langs for file in files]
    return lang_codes


def add_lang_files(langs: List[str], no_prompt: bool = True) -> Tuple[str, List[str]]:
    """添加语言文件

    Args:
        lang_code: 语言代码（如 zh_CN）
    """

    # 新增文件子程序
    def do_add_lang_files(lang_code, lang_files):
        # 标准模板内容
        template = string(
            "# {0} 语言包，文档结构：\n\
# 1. 自动处理 bin | lib 目录 sh 文件\n\
# 2. 解析函数 string | info | exiterr | error | success | warning\n\
# 3. key=hash code of wording\n\
# 4. value=localized string",
            lang_code,
        )

        flag = False
        for file in lang_files:
            if not os.path.exists(file):
                with open(file, "w", encoding="utf-8") as f:
                    f.write(template)
                flag = True
        if flag:
            info("{0} 语言文件已创建", lang_code)  # 新增通知消息

    ret_lang = []
    for lang_code in langs:
        lang_files, flag = resolve_lang_files(lang_code, "1+i")
        if flag == 1:
            ret_lang.append((lang_code, lang_files))
            continue  # 无需处理
        # 如果指定了 no_prompt 为 True，则直接删除文件
        if no_prompt:
            do_add_lang_files(lang_code, lang_files)
            ret_lang.append((lang_code, lang_files))
            continue

        # 文件存在，提示用户是否删除
        prompt = string("确定要新增 {0} 语言文件吗?", lang_code)
        errmsg = string("操作已取消，未增加 {0} 文件文件", lang_code)
        act = confirm_action(prompt, do_add_lang_files, lang_code, lang_files, msg=errmsg)
        if act == 0:
            ret_lang.append((lang_code, lang_files))

    return ret_lang


def del_lang_files(langs: List[str], no_prompt: bool = False) -> None:
    """删除语言文件

    Args:
        lang_code: 语言代码（如 zh_CN）
        no_prompt: 是否不提示直接删除
    """

    # 删除文件子程序
    def do_del_lang_files(lang_code, lang_files):
        flag = False
        for file in lang_files:
            if os.path.exists(file):
                os.remove(file)
                flag = True
        if flag:
            info("{0} 语言文件已删除", lang_code)  # 删除通知消息

    for lang_code in langs:
        lang_files, flag = resolve_lang_files(lang_code, "0-e")
        if flag == 1:
            continue  # 无需处理
        # 如果指定了 no_prompt 为 True，则直接删除文件
        if no_prompt:
            do_del_lang_files(lang_code, lang_files)
            continue

        # 文件存在，提示用户是否删除
        prompt = string("确定要删除 {0} 语言文件吗?", lang_code)
        confirm_action(prompt, do_del_lang_files, lang_code, lang_files, errmsg=string("操作已取消，文件未删除"))


def upd_lang_files(langs: List[str], files: List[str], debug: bool) -> None:
    """修改语言文件

    Args:
        lang: 语言代码（如 zh_CN）
    """
    # 获取所有文件路径
    lang_codes = get_lang_files(langs)
    # 修改语言文件(yml和properties)
    data = update_lang_files(lang_codes, files, debug)
    if debug:
        debug_assertion(data, lang_codes)


def main():
    """主程序入口"""
    app = create_app(help="i18n tools 国际化工具")

    def parse_multi_val(value: List[str]) -> List[str]:
        """将包含分隔符的字符串列表拆分成单独的项目"""
        result = []
        # 如果包含逗号 | 空格 | 分号，予以拆分
        for item in value:
            result.extend(re.split(r"[ ,;]+", item))  # [ ,;]+ 表示一个或多个空格或逗号
        return result

    @app.command("add")
    def add_command(
        lang: Optional[List[str]] = typer.Option(None, "-l", "--lang", help="指定语言包"),
    ):
        """新增语言文件"""
        langs = parse_multi_val(lang) if lang else [get_lang_code()]
        add_lang_files(langs)

    @app.command("del")
    def del_command(
        lang: Optional[List[str]] = typer.Option(None, "-l", "--lang", help="指定语言包"),
        yes: bool = typer.Option(False, "--yes", "-y", help="不提示直接执行"),
    ):
        """删除语言文件"""
        langs = parse_multi_val(lang) if lang else [get_lang_code()]
        del_lang_files(langs, yes)

    @app.command()
    def update(
        lang: Optional[List[str]] = typer.Option(None, "-l", "--lang", help="指定语言包"),
        file: Optional[List[str]] = typer.Option(None, "-f", "--file", help="待处理文件路径"),
        debug: bool = typer.Option(False, "--debug", help="调试模式"),
    ):
        """更新语言文件（默认操作）"""
        # 处理多值选项
        langs = parse_multi_val(lang) if lang else []
        files = parse_multi_val(file) if file else []

        upd_lang_files(langs, files, debug)

    # 如果没有子命令，默认运行update
    commands = ["add", "del", "update"]
    default_cmd("update", commands)

    app()


if __name__ == "__main__":
    main()
