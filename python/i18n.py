#!/usr/bin/env python3

import locale
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import typer


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.lang.lang_util import debug_assertion, update_lang_files
from python.msg_handler import _mf, string, info, warning, error, exiterr
from python.debug_tool import create_app, default_cmd, print_array
from python.file_util import write_array
from python.read_util import confirm_action


# 设置默认路径
PARENT_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = (PARENT_DIR / "lib").resolve()
CONF_DIR = (PARENT_DIR / "config").resolve()
LANG_DIR = (CONF_DIR / "lang").resolve()


# 确保目录存在
os.makedirs(LANG_DIR, exist_ok=True)


# =============================================================================
# 自动检测语言代码
# =============================================================================
def get_lang_code():
    lang_env = os.environ.get("LANG", "en_US:en")
    if lang_env:
        return lang_env[:2]
    try:
        return locale.getdefaultlocale()[0][:2]
    except (TypeError, IndexError):
        return "en"


def resolve_lang_files(lang_code: str, mode: str = "", max_files: int = 1) -> List[str]:
    """Checks for the existence of multiple language files

    Args:
        lang_code: Language code (e.g., zh_CN)
        mode: Error condition mode:
            - "-" : Error if a file does not exist
            - "+" : Error if a file already exists
            - "e": Raise error
            - "w": Warn only
            - "i": Info message only

        Mode combinations:
            - "0-e": Error if no file exists
            - "1-e": Error if at least one file is missing
            - "1+e": Error if at least one file exists
            - "2+e": Error if all files exist

        max_files: Maximum number of files to check

    Returns:
        A list of language file paths, and a result code (0 = OK, 1 = Error)
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
        exiterr(r"Invalid mode parameter {}", mode)

    # 检查文件存在性
    any_exists = any(os.path.isfile(file) for file in lang_files)
    all_exist = all(os.path.isfile(file) for file in lang_files)

    exist_msg = _mf("{0} Language file already exists", lang_code)
    notexist_msg = _mf("{0} Language file does not exist", lang_code)

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
    """Parse language files, extract language codes, and return them as a list"""
    lang_codes = []

    # 查找所有 .properties 文件
    for file in Path(LANG_DIR).glob(".*.properties"):
        match = re.search(r"/\.([a-zA-Z_]+)\.properties$", str(file))
        if match:
            lang_codes.append(match.group(1))

    return lang_codes


def get_lang_files(langs: List[str] = None) -> Tuple[List[str], List[str]]:
    """
    Get language files
    Args:
        lang_code: Specific language code to filter. returned all available language codes if empty
    Returns:
        lang_codes: A list of language codes
    """
    lang_codes = []

    if langs:
        lang_codes.extend(langs)
    else:
        lang_codes.extend(resolve_lang_codes())

    ret_langs = add_lang_files(lang_codes, False)
    if not ret_langs:
        exiterr("Please add the language file first")

    return lang_codes


def add_lang_files(langs: List[str], no_prompt: bool = True) -> Tuple[str, List[str]]:
    """Add language files, use language code such as 'zh_CN'"""

    def do_add_lang_files(lang_code, lang_files):
        template = _mf(
            "# {0} 语言包，文档结构：\n\
# 1. 自动处理 bin | lib 目录 sh 文件\n\
# 2. 解析函数 exiterr | error | success | warning | info | string | _mf\n\
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
            info("{0} Language file has been created", lang_code)  # 新增通知消息

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
        prompt = _mf("Are you sure to create the {0} language file?", lang_code)
        errmsg = _mf("Action cancelled. The {0} file was not created", lang_code)
        ret_code = confirm_action(prompt, do_add_lang_files, lang_code, lang_files, msg=errmsg)
        if ret_code == 0:
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
            info("{0} Language file has been deleted", lang_code)  # 删除通知消息

    for lang_code in langs:
        lang_files, flag = resolve_lang_files(lang_code, "0-e")
        if flag == 1:
            continue  # 无需处理
        # 如果指定了 no_prompt 为 True，则直接删除文件
        if no_prompt:
            do_del_lang_files(lang_code, lang_files)
            continue

        # 文件存在，提示用户是否删除
        prompt = _mf("Are you sure to delete the {0} language file?", lang_code)
        confirm_action(
            prompt, do_del_lang_files, lang_code, lang_files, errmsg=_mf("Action cancelled. File deletion aborted")
        )


def upd_lang_files(langs: List[str], files: List[str], test_run: bool) -> None:
    """修改语言文件

    Args:
        lang: 语言代码（如 zh_CN）
    """
    # 获取所有文件路径
    lang_codes = get_lang_files(langs)
    # 修改语言文件(yml和properties)
    data = update_lang_files(lang_codes, files, test_run)
    if test_run:
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
        test_run: bool = typer.Option(False, "--test_run", help="调试模式"),
    ):
        """更新语言文件（默认操作）"""
        # 处理多值选项
        langs = parse_multi_val(lang) if lang else []
        files = parse_multi_val(file) if file else []
        upd_lang_files(langs, files, test_run)

    # 如果没有子命令，默认运行update
    commands = ["add", "del", "update"]
    default_cmd("update", commands)

    app()


if __name__ == "__main__":
    main()
