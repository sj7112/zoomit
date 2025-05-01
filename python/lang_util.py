#!/usr/bin/env python3

from datetime import datetime
import sys
import os
import argparse
import locale
import re
import click
from ruamel.yaml.comments import CommentedMap

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hash_util import set_prop_files
from ast_parser import parse_shell_files
from file_util import (
    read_config,
    read_lang_yml,
    write_config,
    write_lang_yml,
)
from debug_tool import test_assertion

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
COUNT = "Z-COUNT"
START = "Z-START"
END = "Z-END"
STATS = "stats"
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


def get_current_time():
    """输出当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _not_found():
    """输出提示信息 + 时间戳"""
    return f"# NOT FOUND {get_current_time()}"


def get_locale_code(fn):
    """获取系统语言代码"""
    return re.search(r"lang/([a-zA-Z]{2}(?:_[a-zA-Z]{2})?)\.properties", fn).group(1)


def get_system_locale():
    """
    获取系统区域设置代码
    从多个环境变量中依次尝试获取区域设置，并去除编码后缀
    如果都未找到，则返回默认值 'en'

    返回:
        区域设置代码，例如 'zh_CN', 'en_US', 'en' 等
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


def get_file_type(fn):
    """获取文件种类"""
    match = re.search(r"(?<=\.)[^./\\\s]+$", fn)
    return FILE_TYPE.get(match.group(0)) if match else None


def file_lang_inline_format(stat_dict, lang_code, data):
    """语言统计采用紧凑模式：写入到一行

    例子:
        stats:
            zh: {count: 17, start: 8, end: 34}
            en: {count: 17, start: 13, end: 39}
    """
    zh_data = CommentedMap()
    zh_data["count"] = data[COUNT]  # 有效消息数量
    zh_data["start"] = data[START]  # 起始位置
    zh_data["end"] = data[END]  # 结束位置
    zh_data.fa.set_flow_style()  # 设置为流式样式 (内联格式)
    stat_dict[lang_code] = zh_data


def stat_file_yml(lang_code, lang_data, missing_lang_data, file_yml):
    """汇总信息 file_yml
        [file_name]["stats"][lang_code][count | start | end]

    解释:
        lang_data: 重新计算后的结果列表
        missing_lang_data: 原始配置数据(本次未操作)
    """
    for file_name in lang_data.keys():
        # 调整为流式样式 (内联格式)
        file_lang_inline_format(file_yml[file_name][STATS], lang_code, lang_data[file_name])

    for file_name in missing_lang_data.keys():
        if file_name in file_yml:  # 如果在yml中未定义，则自动跳过（不负责错误数据清理）
            # 调整为流式样式 (内联格式)
            file_lang_inline_format(file_yml[file_name][STATS], lang_code, missing_lang_data[file_name])


def config_lang_inline_format(stats):
    """语言统计采用紧凑模式：写入到一行

    例子:
        stats:
            zh: {count: 44}
            en: {count: 44}
    """
    for lc in stats.keys():
        if lc != "file_nos":
            zh_data = CommentedMap()
            zh_data["count"] = stats[lc]["count"]  # 有效消息数量
            zh_data.fa.set_flow_style()  # 设置为流式样式 (内联格式)
            stats[lc] = zh_data


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
        # 遍历stats中的键值对(lang_code, stats["count"])
        for lc, stat in file_info[STATS].items():
            if isinstance(stat, dict):
                # 将值累加到config_yml对应项
                if not lc in stats:
                    stats[lc] = {"count": stat["count"]}
                else:
                    stats[lc]["count"] += stat["count"]

    # 调整为流式样式 (内联格式)
    config_lang_inline_format(stats)
    config_yml[STATS] = stats


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
    file_data[COUNT] = count
    file_data[START] = start
    file_data[END] = len(new_lines) + 1  # 结束位置
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

    file_data[COUNT] = count
    file_data[START] = start
    file_data[END] = start = len(new_lines) + 1  # 结束位置
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
        file_data[COUNT] = count
        file_data[START] = start
        file_data[END] = len(new_lines) + 1  # 结束位置


# =============================================================================
# 主函数：处理语言文件(元数据)
# =============================================================================
def reset_lang_yml(lang_data, data):
    global DEL_MODE

    config_yml = data["config"]
    config_yml["changed"] = get_current_time()
    if config_yml["del_mode"]:
        DEL_MODE = config_yml["del_mode"]  # 重置DEL_MODE

    file_yml = data["file"] = data["file"] if isinstance(data.get("file"), dict) else {}

    for file_name in lang_data.keys():
        if file_name in file_yml:
            file_yml[file_name]["changed"] = get_current_time()
            if not STATS in file_yml[file_name]:
                file_yml[file_name][STATS] = {}
        else:
            now = get_current_time()
            file_yml[file_name] = {
                "type": get_file_type(file_name),
                "djb2_len": config_yml["djb2_len"],
                "created": now,
                "changed": now,
                STATS: {},
            }

    return config_yml, file_yml


# =============================================================================
# 主函数：处理语言文件(元数据)
# =============================================================================
# def update_lang_files(lang_files, lang_data, test_run=False):

# # 读yaml
# data, yaml = read_lang_yml()

# config_yml, file_yml = reset_lang_yml(lang_data, data)  # 重置yaml配置
# set_prop_files(lang_data, file_yml),  # hash code
# for lang_file in lang_files:
#     missing_lang_data = update_lang_properties(lang_file, lang_data, test_run)
#     stat_file_yml(get_locale_code(lang_file), lang_data, missing_lang_data, file_yml)
# stat_config_yml(config_yml, file_yml)

# # 写yaml
# if not test_run:
#     write_lang_yml(data, yaml)

# return data


def yaml_file_interceptor(yaml_file_path):
    """
    拦截器装饰器，处理YAML文件的读取和写入
    :param yaml_file_path: YAML文件路径
    """

    def decorator(main_func):
        def wrapper(lang_files, lang_data, test_run=False):
            # 前置处理：读取YAML文件
            data, yaml = read_lang_yml()

            # 执行主函数
            result = main_func(lang_files, lang_data, test_run, data)

            # 后置处理：只在数据变化且非测试运行时写入文件
            if not test_run:
                write_lang_yml(data, yaml)

            return result

        return wrapper

    return decorator


# 修改后的主函数
@yaml_file_interceptor(YML_PATH)  # 替换为实际的YAML文件路径
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
        stat_file_yml(get_locale_code(lang_file), lang_data, missing_lang_data, file_yml)

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
    data = parse_shell_files(opts["file"])

    # 测试语言文件(yml和properties)
    data = update_lang_files(lang_files, data, True)

    # 读yaml
    (old_data, yaml) = read_lang_yml()

    old_stat = old_data["config"][STATS]
    new_stat = data["config"][STATS]
    o = old_stat["file_nos"]
    n = new_stat["file_nos"]
    test_assertion("o == n", f"Number of files: {o} => {n}")
    o = old_stat["zh"]["count"]
    n = new_stat["zh"]["count"]
    test_assertion("o == n", f"Number of zh messages: {o} => {n}")
    o = old_stat["en"]["count"]
    n = new_stat["en"]["count"]
    test_assertion("o == n", f"Number of en messages: {o} => {n}")

    for lang_code in ["zh", "en"]:
        for file_name in data.get("file", {}).keys():
            # 检查文件是否存在于两个字典中
            if file_name not in old_data.get("file", {}):
                test_assertion("False", f"File not exists in yml: {file_name}")
                continue
            old = old_data["file"][file_name]["stats"]
            new = data["file"][file_name]["stats"]
            # 获取语言代码（中文、英文）
            os = old[lang_code].get("start")
            ns = new[lang_code].get("start")
            oe = old[lang_code].get("end")
            ne = new[lang_code].get("end")
            if os != ns or oe != ne:  # 比较 start 和 end 值
                test_assertion("False", f"{lang_code} {file_name} range: [{os} ~ {oe}] => [{ns} ~ {ne}]")


# =============================================================================
# 使用 Click 实现的命令行参数解析
# =============================================================================

# 根据语言选择帮助文本

if re.match(r"^zh(_[A-Z]{2})?$", get_system_locale()):
    main_help = """语言属性文件更新工具
不输入任何参数，则自动检查所有文件，并更新所有语言包"""
else:
    main_help = """Language property file update tool
If no parameters are entered, all files are automatically checked and all language packs are updated"""


def parse_multi_val(ctx, param, value):
    # ctx: 命令上下文
    # param: 当前处理的参数对象
    # value: 参数的值
    result = []
    # 如果包含逗号 | 空格 | 分号，予以拆分
    for item in value:
        result.extend(re.split(r"[ ,;]+", item))  # [ ,;]+ 表示一个或多个空格或逗号
    return result


@click.command(help=main_help)
@click.option("-l", "--lang", multiple=True, callback=parse_multi_val, help="语言包")
@click.option("-f", "--file", multiple=True, callback=parse_multi_val, help="待处理文件路径")
@click.option("--debug", is_flag=True, help="调试模式")
@click.argument("params", nargs=-1)
def cli(**kwargs):
    """临时文档，将被替换"""

    # 根据 debug 标志决定运行测试还是执行
    if kwargs["debug"]:
        run_test(kwargs)
    else:
        run_exec(kwargs)


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    cli()  # 直接调用 Click 命令行入口
