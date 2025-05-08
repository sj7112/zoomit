#!/usr/bin/env python3

from datetime import datetime
import sys
import os
import locale
import re
from ruamel.yaml.comments import CommentedMap
import typer
import re
from typing import List, Optional

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hash_util import set_prop_files
from ast_parser import parse_shell_files
from file_util import (
    read_config,
    read_lang_yml,
    write_config,
    write_lang_yml,
    print_array as file_print_array,
)
from debug_tool import test_assertion, print_array

# 多语言支持
FILE_MODE = "c|cpp|java|js|py|sh|ts"
FILE_TYPE = {
    "c": "c",
    "cpp": "c++",
    "java": "java",
    "py": "python",
    "sh": "shell",
    "ts": "typescript",
}

# 读取环境变量并设置为全局变量，默认值为0
DEL_MODE = 1  # 0=保留；1=注释；2=删除

HASH = "Z-HASH"
FILE_STAT = "Z-STAT"
COUNT = "count"
START = "start"
END = "end"
YML_STAT = "stats"
YML_PATH = "/usr/local/shell/config/lang/_lang.yml"

# 文件匹配模式
FILE_MATCH = rf"^#\s+\d+=[^\s]+\.(?:{FILE_MODE})$"  # 不含捕获组
FILE_MATCH_G = rf"^#\s+\d+=([^\s]+\.(?:{FILE_MODE}))$"  # 含捕获组
# 函数匹配模式
FUNC_MATCH = r"^#===[^\s]+"  # 不含捕获组
FUNC_MATCH_G = r"^#===([^\s]+)"  # 含捕获组
# 消息匹配模式
MSG_MATCH_CHK = r"^\s*[A-Za-z0-9+_]+\s*=\s*.+?(\s*#.*)?\s*$"  # 不含捕获组（检查是否有效消息）
MSG_MATCH_G = r"^#?\s*([A-Za-z0-9+_]+)\s*=\s*(.+?)(\s*#.*)?\s*$"  # 含捕获组


def _current_time():
    """输出当前时间

    返回:
        当前时间的字符串表示，格式为 YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _not_found():
    """找不到数据时输出: NOT FOUND + 时间戳"""
    return f"# NOT FOUND {_current_time()}"


def _locale_code(fn):
    """获取系统语言代码"""
    return re.search(r"lang/([a-zA-Z]{2}(?:_[a-zA-Z]{2})?)\.properties", fn).group(1)


def _system_locale():
    """
    获取系统区域设置代码
    从多个环境变量中依次尝试获取区域设置，并去除编码后缀
    如果都未找到，则返回默认值 'en'

    返回:
        区域设置代码，例如 'zh_CN', 'en_US', 'zhzh', 'en' 等
    """
    # 按优先级顺序尝试不同的环境变量
    for var in ["LANG", "LC_ALL", "LC_MESSAGES"]:
        locale = os.environ.get(var, "")
        if locale:
            # 去除 .UTF-8 等后缀
            locale = locale.split(".")[0]
            if locale:
                return locale

    # 默认返回 en（英语）
    return "en"


def _file_type(fn):
    """获取文件种类"""
    match = re.search(r"(?<=\.)[^./\\\s]+$", fn)
    return FILE_TYPE.get(match.group(0)) if match else None


def _set_flow_style(parentObj, key, data):
    """语言统计采用紧凑模式：写入到一行"""
    zh_data = CommentedMap(data)
    zh_data.fa.set_flow_style()  # 设置为流式样式 (内联格式)
    parentObj[key] = zh_data


def file_lang_inline_format(file_yml, file_name, lang_code, lang_data):
    """语言统计采用紧凑模式：写入到一行

    数据:
        count=有效消息数量；staart=起始位置；end=结束位置
    例子:
        stats:
            zh: {count: 17, start: 8, end: 34}
            en: {count: 17, start: 13, end: 39}
    """
    _set_flow_style(file_yml[file_name][YML_STAT], lang_code, lang_data[file_name][FILE_STAT])


def stat_file_yml(lang_code, lang_data, missing_lang_data, file_yml):
    """汇总信息 file_yml
        [file_name]["stats"][lang_code][count | start | end]

    解释:
        lang_data: 重新计算后的结果列表
        missing_lang_data: 原始配置数据(本次未操作)
    """
    for file_name in lang_data.keys():
        # 调整为流式样式 (内联格式)
        file_lang_inline_format(file_yml, file_name, lang_code, lang_data)

    for file_name in missing_lang_data.keys():
        if file_name in file_yml:  # 如果在yml中未定义，则自动跳过（不负责错误数据清理）
            # 调整为流式样式 (内联格式)
            file_lang_inline_format(file_yml, file_name, lang_code, missing_lang_data)


def config_lang_inline_format(stats):
    """语言统计采用紧凑模式：写入到一行

    例子:
        stats:
            zh: {count: 44}
            en: {count: 44}
    """
    for lc in stats.keys():
        if lc != "file_nos":
            _set_flow_style(stats, lc, stats[lc])  # 有效消息数量


def stat_config_yml(config_yml, file_yml):
    """汇总信息 config_yml
       ["stats"][lang_code][count]

    解释：
        stats.msg_{lang_code}: 有效消息数量总计(所有文件)
        stats.{lang_code}.count: 有效消息数量(单个文件)
    """
    stats = {"file_nos": 0}
    # 遍历所有文件
    for file_info in file_yml.values():
        stats["file_nos"] += 1
        # 遍历stats中的键值对(lang_code, stats[COUNT])
        for lc, stat in file_info[YML_STAT].items():
            if isinstance(stat, dict):
                # 将值累加到config_yml对应项
                if not lc in stats:
                    stats[lc] = {COUNT: stat[COUNT]}
                else:
                    stats[lc][COUNT] += stat[COUNT]

    # 调整为流式样式 (内联格式)
    config_lang_inline_format(stats)
    config_yml[YML_STAT] = stats


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
            case l if re.match(FILE_MATCH, l):
                return i  # 文件标记行，停止处理
            case _:
                new_lines.append(line)  # 普通行，添加
                i += 1
    return i  # 文件结束


# =============================================================================
# 识别文件区块并返回相关信息
# =============================================================================
def identify_file_section(lines, i, new_lines):
    file_name = re.match(FILE_MATCH_G, lines[i]).group(1)
    new_lines.append("")  # 顶部增加一个空行
    new_lines.append(lines[i])

    return i + 1, file_name


# =============================================================================
# 处理单个文件区块的内容
# =============================================================================
def msg_match(lines, i):
    msg_old_data = {}
    while i < len(lines):
        line = lines[i].strip()
        if re.match(FILE_MATCH, line):
            break  # 匹配到下一个文件，退出

        if not line or re.match(FUNC_MATCH, line):
            i += 1
            continue  # 去掉多余空行 | 函数注释行

        match = re.match(MSG_MATCH_G, line)
        if match:
            key = match.group(1)
            msg_old_data[key] = {
                "msg": match.group(2),
                "cmt": (match.group(3) or ""),
            }

        i += 1

    return i, msg_old_data


# =============================================================================
# 跳过不需要处理的文件区块
# =============================================================================
def skip_file_section(lines, i, new_lines, file_data):
    count = 0  # 语言消息条数
    start = len(new_lines) + 1  # 起始位置
    while i < len(lines):
        line = lines[i].strip()
        if re.match(FILE_MATCH, line):
            break  # 匹配到下一个文件，退出

        if not line:
            i += 1
            continue  # 去掉多余空行

        if re.match(MSG_MATCH_CHK, lines[i]):
            count += 1
        new_lines.append(lines[i])
        i += 1
    end = len(new_lines) + 1  # 结束位置
    file_data[FILE_STAT] = {COUNT: count, START: start, END: end}
    return i


# =============================================================================
# 处理单个文件区块的内容
# =============================================================================
def process_file_section(lines, i, new_lines, file_data):
    global DEL_MODE

    count = 0  # 语言消息条数
    start = len(new_lines) + 1  # 起始位置

    i, old_msgs = msg_match(lines, i)  # 匹配msg

    # 跳过processed_file
    for func_name, func_data in file_data.items():
        if isinstance(func_data, dict):
            new_lines.append(f"#==={func_name}")  # 新增函数
            for key, msg in func_data.items():
                new_lines.append(f"{key}={msg}")  # 新增消息
                count += 1
                old_msgs.pop(key, None)  # 删除匹配消息

    if old_msgs:
        new_lines.append(f"#==={_not_found()}")
        for key, value in old_msgs.items():
            msg, cmt = value["msg"], value["cmt"]
            match DEL_MODE:
                case 0:
                    new_lines.append(f"{key}={msg}{cmt}")  # 保留整行，尾部添加注释
                    count += 1
                case 1:
                    new_lines.append(f"# {key}={msg}{cmt}")  # 整行注释，尾部添加注释
                case 2:
                    pass  # 直接跳过 = 删除

    end = len(new_lines) + 1  # 结束位置
    file_data[FILE_STAT] = {COUNT: count, START: start, END: end}
    return i


# =============================================================================
# 添加未出现的语言消息块
# =============================================================================
def append_file_msgs(new_lines, processed_files, lang_data):
    # 跳过processed_files
    for file_name, file_data in (item for item in lang_data.items() if not processed_files.get(item[0], False)):
        count = 0  # 语言消息条数
        new_lines.append("")  # 增加空行
        new_lines.append(f"# {file_data[HASH]}={file_name}")  # 增加顶部行
        start = len(new_lines) + 1  # 起始位置
        for func_name, func_data in file_data.items():
            if isinstance(func_data, dict):
                new_lines.append(f"#==={func_name}")
                for key, msg in func_data.items():
                    new_lines.append(f"{key}={msg}")
                    count += 1
        end = len(new_lines) + 1  # 结束位置
        file_data[FILE_STAT] = {COUNT: count, START: start, END: end}


# =============================================================================
# 主函数：处理语言文件(元数据)
# =============================================================================
def reset_lang_yml(lang_data, data):
    global DEL_MODE

    config_yml = data["config"]
    config_yml["changed"] = _current_time()
    if config_yml["del_mode"]:
        DEL_MODE = config_yml["del_mode"]  # 重置DEL_MODE

    file_yml = data["file"] = data["file"] if isinstance(data.get("file"), dict) else {}

    for file_name in lang_data.keys():
        if file_name in file_yml:
            file_yml[file_name]["changed"] = _current_time()
            if file_yml[file_name].get(YML_STAT) is None:
                file_yml[file_name][YML_STAT] = {}
        else:
            now = _current_time()
            file_yml[file_name] = {
                "type": _file_type(file_name),
                "djb2_len": config_yml["djb2_len"],
                "created": now,
                "changed": now,
                YML_STAT: {},
            }

    return config_yml, file_yml


# 拦截器装饰器
def yaml_file_interceptor():
    """
    拦截器装饰器，处理YAML文件的读取和写入
    1) 前置处理：读取_lang.yml
    2) 主程序：写入properties文件，并重构YAML文件内容
    3）后置处理：写入_lang.yml
    """

    def decorator(main_func):
        def wrapper(lang_files, lang_data, test_run=False):
            # 前置处理：读取YAML文件
            data, yaml = read_lang_yml()

            # 执行主函数 update_lang_files
            result = main_func(lang_files, lang_data, test_run, data)

            # 后置处理：只在数据变化且非测试运行时写入文件
            if not test_run:
                write_lang_yml(result, yaml)

            return result

        return wrapper

    return decorator


# 主函数
@yaml_file_interceptor()
def update_lang_files(lang_files, lang_data, test_run=False, data=None):
    """
    处理语言文件(元数据)
    :param lang_files: 语言文件列表
    :param lang_data: 语言数据
    :param test_run: 是否测试运行
    :param data: 由拦截器注入的YAML数据
    """
    config_yml, file_yml = reset_lang_yml(lang_data, data)  # 重置yaml配置
    set_prop_files(lang_data, file_yml)  # hash code

    for lang_file in lang_files:
        missing_lang_data = update_lang_properties(lang_file, lang_data, test_run)
        stat_file_yml(_locale_code(lang_file), lang_data, missing_lang_data, file_yml)

    stat_config_yml(config_yml, file_yml)

    return data


# =============================================================================
# 主函数：处理语言文件(指定语言)
# =============================================================================
def update_lang_properties(lang_file, lang_data, test_run):
    new_lines = []
    processed_files = {}
    missing_lang_data = {}

    # hash表：文件-函数
    lines = read_config(lang_file)

    # 子程序1：处理头部注释
    i = process_file_head(lines, new_lines)
    while i < len(lines):
        # 子程序2：识别文件标记并返回相关信息
        i, file_name = identify_file_section(lines, i, new_lines)

        if not file_name in lang_data:
            # 子程序3：跳过不需要处理的文件区块
            missing_lang_data[file_name] = {}
            i = skip_file_section(lines, i, new_lines, missing_lang_data[file_name])
        else:
            # 子程序4：处理文件区块内容
            i = process_file_section(lines, i, new_lines, lang_data[file_name])
            processed_files[file_name] = True  # 设置文件已处理标志

    # 子程序5：添加未出现的文件块
    append_file_msgs(new_lines, processed_files, lang_data)
    # 写文件
    if not test_run:
        write_config(lang_file, new_lines)

    return missing_lang_data


# =============================================================================
# 执行逻辑（从STDIN读取数据，调用主函数）
#
# shell调用方法：通过环境变量传参
# =============================================================================
def run_exec(opts):
    lang_files = [
        "/usr/local/shell/config/lang/zh.properties",
        "/usr/local/shell/config/lang/en.properties",
    ]  # 语言消息
    data = parse_shell_files(opts["file"])
    # 修改语言文件(yml和properties)
    update_lang_files(lang_files, data)


# =============================================================================
# 调试测试函数（写入测试文件并验证更新逻辑）
# ./python/lang_util.py --file="bin/i18n.sh bin/init_main.sh" -l"zh en" --debug
# =============================================================================
def run_test(opts):
    # # 读取指定sh文件的消息数据，模拟写入_lang.yml和对应的properties文件
    # data = parse_shell_files(["bin/init_main.sh", "bin/i18n.sh", "bin/cmd_help.sh", "lib/hash_util.sh"])
    print("Debug mode is on. Running tests...")

    lang_files = [
        "/usr/local/shell/config/lang/zh.properties",
        "/usr/local/shell/config/lang/en.properties",
    ]  # 语言消息
    lang_codes = ["zh", "en"]
    data = parse_shell_files(opts["file"])
    # 测试语言文件(yml和properties)
    data = update_lang_files(lang_files, data, True)
    debug_assertion(data, lang_codes)


# =============================================================================
# 调试测试函数（对比新旧yml文件，如有差异，给出差异分析）
# =============================================================================
def debug_assertion(data, lang_codes):
    # 读yaml
    (old_data, yaml) = read_lang_yml()

    old_stat = old_data["config"][YML_STAT]
    new_stat = data["config"][YML_STAT]
    o = old_stat["file_nos"]
    n = new_stat["file_nos"]
    test_assertion("o == n", f"Number of files: {o} => {n}")
    o = old_stat["zh"][COUNT]
    n = new_stat["zh"][COUNT]
    test_assertion("o == n", f"Number of zh messages: {o} => {n}")
    o = old_stat["en"][COUNT]
    n = new_stat["en"][COUNT]
    test_assertion("o == n", f"Number of en messages: {o} => {n}")

    for file_name in data.get("file", {}).keys():
        # 检查文件是否存在于两个字典中
        if file_name not in old_data.get("file", {}):
            test_assertion("False", f"File not exists in yml: {file_name}")
            continue

        # 获取语言代码（中文、英文）
        new = data["file"][file_name].get(YML_STAT)
        old = old_data["file"][file_name].get(YML_STAT)
        if old == None:
            test_assertion("False", f"stats not exists in file yml: {file_name}")
            continue

        for lang_code in lang_codes:
            os = old.get(lang_code).get(START)
            oe = old[lang_code].get(END)
            ns = new[lang_code].get(START)
            ne = new[lang_code].get(END)

            if os != ns or oe != ne:  # 比较 start 和 end 值
                test_assertion("False", f"{lang_code} {file_name} range: [{os} ~ {oe}] => [{ns} ~ {ne}]")


# =============================================================================
# 使用 Typer 实现的命令行参数解析
# =============================================================================

# 根据语言选择帮助文本
if re.match(r"^zh(_[A-Z]{2})?$", _system_locale()):
    main_help = """语言属性文件更新工具
不输入任何参数，则自动检查所有文件，并更新所有语言包"""
else:
    main_help = """Language property file update tool
If no parameters are entered, all files are automatically checked and all language packs are updated"""

app = typer.Typer(pretty_exceptions_show_locals=False, pretty_exceptions_enable=False)


def parse_multi_val(value: List[str]) -> List[str]:
    """将包含分隔符的字符串列表拆分成单独的项目"""
    result = []
    # 如果包含逗号 | 空格 | 分号，予以拆分
    for item in value:
        result.extend(re.split(r"[ ,;]+", item))  # [ ,;]+ 表示一个或多个空格或逗号
    return result


@app.command(help=main_help)
def main(
    lang: Optional[List[str]] = typer.Option(None, "-l", "--lang", help="语言包"),
    file: Optional[List[str]] = typer.Option(None, "-f", "--file", help="待处理文件路径"),
    debug: bool = typer.Option(False, "--debug", help="调试模式"),
    params: List[str] = typer.Argument(None),
):
    """临时文档，将被替换"""
    # 处理多值选项
    lang_list = parse_multi_val(lang) if lang else []
    file_list = parse_multi_val(file) if file else []

    # 构建选项字典
    opts = {"lang": lang_list, "file": file_list, "debug": debug, "params": params}

    # 根据 debug 标志决定运行测试还是执行
    if debug:
        run_test(opts)
    else:
        run_exec(opts)


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    app()  # 直接调用 Typer 命令行入口
