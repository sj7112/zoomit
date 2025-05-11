#!/usr/bin/env python3

from datetime import datetime
import sys
import os
from ruamel.yaml.comments import CommentedMap
import typer
import re
from typing import List, Optional

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ast_parser import parse_shell_files
from file_util import (
    read_lang_prop,
    read_lang_yml,
    write_lang_prop,
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

# 设置全局变量
FILE_HEAD = "Z-HEAD"  # 保留头部信息（头部注释）
FILE_LINE = "Z-LINE"  # 待写入的行内容
FILE_MESSAGE = "Z-MSG"  # 文件所包含的消息
MSG_STATS = "Z-STAT"  # 文件统计信息
COUNT = "count"
START = "start"
END = "end"
YML_STAT = "stats"
YML_PATH = "/usr/local/shell/config/lang/_lang.yml"

# 文件匹配模式
FILE_MATCH = rf"^#\s+■=[^\s]+\.(?:{FILE_MODE})$"  # 不含捕获组
FILE_MATCH_G = rf"^#\s+■=([^\s]+\.(?:{FILE_MODE}))$"  # 含捕获组
# 函数匹配模式
FUNC_MATCH = r"^#\s+◆=[^\s]+"  # 不含捕获组
FUNC_MATCH_G = r"^#\s+◆=([^\s]+)"  # 含捕获组
# 注释匹配模式
CALL_MATCH_G = r"=([^\s]+)\s*$"  # 含捕获组
# 消息匹配模式
MSG_MATCH_CHK = r"^\s*[A-Za-z0-9+_]+\s*=\s*.+?(\s*#.*)?\s*$"  # 不含捕获组（检查是否有效消息）
# MSG_MATCH_G2 = r"^#?\s*([A-Za-z0-9+_]+)\s*=\s*(.+?)\s*$"  # 两个捕获组
# MSG_MATCH_G3 = r"^#?\s*([A-Za-z0-9+_]+)\s*=\s*(.*?)(\s#[A-Za-z0-9+_]+@\d+@\S*)\s*$"  # 三个捕获组
MSG_MATCH_G3 = r"^#?\s*([A-Za-z0-9+_]+)\s*=\s*(.*?)(\s#[A-Za-z0-9+_]+@\d+@\S*)?$"  # 三个捕获组(最后一个可以不存在)


def _current_time():
    """输出当前时间

    返回:
        当前时间的字符串表示，格式为 YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _not_found():
    """找不到数据时输出: NOT FOUND + 时间戳"""
    return f"# NOT FOUND {_current_time()}"


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


def file_lang_inline_format(stats, lang_code, file_stats):
    """语言统计采用紧凑模式：写入到一行

    数据:
        count=有效消息数量；staart=起始位置；end=结束位置
    例子:
        stats:
            zh: {count: 17, start: 8, end: 34}
            en: {count: 17, start: 13, end: 39}
    """
    _set_flow_style(stats, lang_code, file_stats)
    return stats


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


def stat_config_yml(data):
    """汇总信息 config_yml
       ["stats"][lang_code][count]

    解释：
        stats.msg_{lang_code}: 有效消息数量总计(所有文件)
        stats.{lang_code}.count: 有效消息数量(单个文件)
    """
    to_delete = []  # 收集待删除的键
    stats = {"file_nos": 0}
    # 遍历所有文件
    file_yml = data["file"]
    for file_name, file_info in file_yml.items():
        count = 0  # 如果值为空，删除file_yml对应记录
        stats["file_nos"] += 1
        # 遍历stats中的键值对(lang_code, stats[COUNT])
        for lc, stat in file_info[YML_STAT].items():
            if isinstance(stat, dict):
                count += stat[COUNT]
                # 将值累加到config_yml对应项
                stats.setdefault(lc, {COUNT: 0})[COUNT] += stat[COUNT]
        if count == 0:
            to_delete.append(file_name)  # 记录要删除的键

    # 文件名排序，同时剔除没有消息的文件
    data["file"] = {key: file_yml[key] for key in sorted(file_yml) if key not in to_delete}

    # 调整为流式样式 (内联格式)
    config_lang_inline_format(stats)
    data["config"][YML_STAT] = stats


def parse_lang_head(lines, line_number, prop_data):
    """获取文件头部注释"""
    file_lines = prop_data.setdefault(FILE_HEAD, {}).setdefault(FILE_LINE, [])
    while line_number[0] < len(lines):
        line = lines[line_number[0]]
        match line.strip():
            case "":
                line_number[0] += 1  # 空行，跳过
            case l if re.match(FILE_MATCH, l):
                return  # 文件标记行，停止处理
            case _:
                file_lines.append(line)  # 普通行，添加
                line_number[0] += 1


def extract_multi_lines(content, lines, line_number):
    """
    如果为当红，直接返回；如果为多行，添加多行数据并返回
    如果TRIM_SPACE = True，则去掉字符串右侧的空格！！

    参数:
    - content: 输入字符串段落
    - lines: 待处理多行数据
    - line_number：如为多行，动态修改此变量

    返回:
    - content：如为多行，直接修改content内容（用\n拼接）
    """
    # 检查是否多行文本
    if content.endswith("\\"):
        while line_number[0] < len(lines) - 1:
            line_number[0] += 1
            content += "\n"  # 增加换行
            line = lines[line_number[0]]
            content_match = re.match(r"^(.*?(?<!\\)\\)\s*$", line)  # 采用孤立的 \ 结束（捕获组去掉尾部的空格）
            if content_match:
                content += content_match.group(1).rstrip()
            else:
                content += line
                return content.rstrip() if TRIM_SPACE else content

    return content.rstrip() if TRIM_SPACE else content


def parse_comment(line):
    """获取消息备注"""
    match = re.match(CALL_MATCH_G, line)
    return match.group(1) if match else ""


def parse_lang_file(lines, line_number, prop_data, file_name):
    """获取文件分段信息"""
    file_lines = []  # 文件内容
    file_msgs = {}  # 消息的key和value

    while line_number[0] < len(lines):
        line = lines[line_number[0]].strip()
        if re.match(FILE_MATCH, line):
            break  # 匹配到下一个文件，退出

        if not line:
            line_number[0] += 1
            continue  # 去掉多余空行

        file_lines.append(lines[line_number[0]])  # 照抄原lines数据
        match = re.match(MSG_MATCH_G3, line)
        if match:
            pre_line = lines[line_number[0] - 1]  # 上一行，默认存放消息备注
            file_msgs[match.group(1)] = {
                "msg": extract_multi_lines(match.group(2), lines, line_number),  # 获取消息值
                "cmt": parse_comment(pre_line),  # 获取消息备注
            }

        line_number[0] += 1
    prop_data[file_name] = {
        FILE_LINE: file_lines,
        FILE_MESSAGE: file_msgs,
        MSG_STATS: {"count": len(file_msgs)},  # 语言消息条数
    }


def set_global_data(data):
    """根据config参数，重置全局变量和全局配置"""
    global DEL_MODE
    global TRIM_SPACE
    global DJB2_LEN

    # 设置全局配置
    config_yml = data["config"]
    config_yml["changed"] = _current_time()
    data["file"] = data["file"] if isinstance(data.get("file"), dict) else {}
    # 设置全局变量
    DEL_MODE = config_yml.get("del_mode", 2)  # 0=保留；1=注释；2=删除
    TRIM_SPACE = config_yml.get("trim_space", False)  # 默认不处理空格
    DJB2_LEN = config_yml.get("djb2_len", 20)  # 默认20个字符参与hash计算

    return data["file"]


def parse_lang_prop(lang_code):
    """
    主函数：处理语言文件(指定语言)
    1) 读取原有properties数据
    2) 合并重新计算的lang_data数据
    3) 写入文件并返回合并后的结果
    """
    prop_data = {}

    # hash表：文件-函数
    lines = read_lang_prop(lang_code)
    line_number = [0]  # 使用列表包装，以便函数可以修改
    total_lines = len(lines)

    # 子程序1：处理头部注释
    parse_lang_head(lines, line_number, prop_data)
    while line_number[0] < total_lines:
        # 子程序2：处理文件消息
        file_name = re.match(FILE_MATCH_G, lines[line_number[0]]).group(1)
        line_number[0] += 1
        parse_lang_file(lines, line_number, prop_data, file_name)

    return prop_data


def append_msg(file_lines, k, v):
    """添加消息到文件"""
    if v["cmt"]:
        file_lines.append(f"# ●={v['cmt']}")
    msg = v["msg"].split("\n")
    length = len(msg)
    if length == 1:
        file_lines.append(f"{k}={v['msg']}")  # 消息+注释
    else:
        msg[0] = f"{k}={msg[0]}"  # 第一行
        file_lines.extend(msg)


def parse_lang_data(file_data):
    """
    主函数：添加新的文件
    新数据自动添加（_lang有注释；普通语言文件无注释）
    """
    count = 0  # 语言消息条数
    file_lines = []
    for func_name, func_data in file_data.items():
        if isinstance(func_data, dict):
            file_lines.append(f"# ◆={func_name}")
            for k, v in func_data.items():
                append_msg(file_lines, k, v)  # 消息+注释
                count += 1

    return {FILE_LINE: file_lines, MSG_STATS: {"count": count}}


def merge_lang_data(data, file_data, translated):
    """
    主函数：合并新的文件
    1) _lang：数据有冲突，总是用新数据替换旧数据
    2) 普通语言文件：数据有冲突，总是保留旧数据
    3) 新数据自动添加（_lang有注释；普通语言文件无注释）
    4) 旧数据根据DEL_MODE决定是否删除、保留或加注释（原有注释会保留）
    """
    file_lines = []
    count = 0  # 语言消息条数
    old_msgs = data[FILE_MESSAGE]  # 匹配msg

    # 跳过processed_file
    for func_name, func_data in file_data.items():
        if isinstance(func_data, dict):
            file_lines.append(f"# ◆={func_name}")  # 新增函数
            for k, v in func_data.items():
                if k in old_msgs:
                    new_v = old_msgs[k] if translated else v  # 翻译类语言文件，需保留原有翻译内容
                    append_msg(file_lines, k, new_v)  # 消息+注释
                    old_msgs.pop(k)  # 删除匹配消息
                else:
                    append_msg(file_lines, k, v)  # 消息+注释
                count += 1

    if old_msgs and DEL_MODE != 2:  # 没有附加消息，或直接删除，则跳过处理
        file_lines.append(f"# ◆={_not_found()}")
        for k, v in old_msgs.items():
            match DEL_MODE:
                case 0:
                    append_msg(file_lines, k, v)  # 保留整行
                    count += 1
                case 1:
                    append_msg(file_lines, f"# {k}", v)  # 整行注释

    data[FILE_LINE] = file_lines
    data[MSG_STATS] = {"count": count}


def clean_lang_data(lang_data):
    """主函数：清除备注字段"""
    for file_data in lang_data.values():
        for func_data in file_data.values():
            if isinstance(func_data, dict):
                for v in func_data.values():
                    v["cmt"] = ""  # 清空注释（只用一次）


def handle_prop_data(prop_data):
    """主函数：生成new_lines"""
    new_lines = prop_data[FILE_HEAD][FILE_LINE]  # 头部注释
    # 跳过processed_files
    for file_name, file_data in sorted(prop_data.items()):  # 排序：按文件名
        if file_name == FILE_HEAD:
            continue  # 跳过非文件部分
        if file_data[FILE_LINE]:
            new_lines.extend(["", f"# ■={file_name}"])  # 增加空行 | 文件标题行
            new_lines.extend(file_data[FILE_LINE])  # 文件内容
            # 统计MSG_STATS
            file_data[MSG_STATS][START] = len(new_lines) + 1 - len(file_data[FILE_LINE])  # 文件起始行
            file_data[MSG_STATS][END] = len(new_lines) + 1  # 文件结束行

    return new_lines


def handle_prop_yml_data(lang_code, prop_data, file_yml):
    """主函数：生成new_lines，改写file_yml"""
    new_lines = prop_data[FILE_HEAD][FILE_LINE]  # 头部注释
    # 跳过processed_files
    for file_name, file_data in sorted(prop_data.items()):  # 排序：按文件名
        if file_name == FILE_HEAD:
            continue  # 跳过非文件部分
        if file_data[FILE_LINE]:
            new_lines.extend(["", f"# ■={file_name}"])  # 增加空行 | 文件标题行
            new_lines.extend(file_data[FILE_LINE])  # 文件内容
            # 统计MSG_STATS
            file_data[MSG_STATS][START] = len(new_lines) + 1 - len(file_data[FILE_LINE])  # 文件起始行
            file_data[MSG_STATS][END] = len(new_lines) + 1  # 文件结束行

        # 处理file_yml
        if file_name in file_yml:  # 如果在yml中未定义，则自动跳过（不负责YAML错误数据清理）
            file_lang_inline_format(file_yml, file_name, lang_code, file_data[MSG_STATS])

    return new_lines


def handle_yml_data(lang_code, prop_data, file_yml):
    """
    主函数：改写file_yml(元数据)
    1) 现有文件，重置file参数
    2) 新增文件，添加file参数
    3）设置stats
    """
    for file_name, file_data in sorted(prop_data.items()):  # 排序：按文件名
        if file_name == FILE_HEAD:
            continue  # 跳过非文件部分

        now = _current_time()
        if file_name in file_yml:  # 现有文件
            file_yml[file_name]["changed"] = now
            if file_yml[file_name].get(YML_STAT) is None:
                file_yml[file_name][YML_STAT] = {}
        else:  # 新增文件
            file_yml[file_name] = {
                "type": _file_type(file_name),
                "djb2_len": DJB2_LEN,
                "created": now,
                "changed": now,
                YML_STAT: {},
            }
        file_lang_inline_format(file_yml[file_name][YML_STAT], lang_code, file_data[MSG_STATS])


def update_lang_properties(lang_code, lang_data, file_yml, test_run):
    """
    主函数：处理语言文件(指定语言)
    1) 读取原有properties数据
    2) 合并重新计算的lang_data数据
    3) _lang.properties的特殊处理：
         - merge时候，始终采用新数据
         - 执行完毕，清除备注字段
    4) 普通语言文件的特殊处理：
         - merge时候，始终采用旧数据
         - 执行完毕，改写file_yml
    """
    # 从语言文件中读取原始数据
    prop_data = parse_lang_prop(lang_code)
    # 合并重新计算后的语言数据
    for file_name, file_data in lang_data.items():
        if not (file_name in prop_data):
            prop_data[file_name] = parse_lang_data(file_data)  # 补充：新添加的文件
        else:
            merge_lang_data(prop_data[file_name], file_data, lang_code != "_lang")  # 合并：已有的文件

    # 生成new_lines
    new_lines = handle_prop_data(prop_data)

    # 写文件
    if not test_run:
        write_lang_prop(lang_code, new_lines)

    if lang_code == "_lang":
        clean_lang_data(lang_data)  # 清除：备注字段（只在_lang文件中使用一次！）
    else:
        handle_yml_data(lang_code, prop_data, file_yml)  # 改写file_yml


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
            file_yml = set_global_data(data)  # 设置全局变量

            # 执行主函数 update_lang_files
            main_func(lang_files, lang_data, test_run, file_yml)

            # 后置处理：只在数据变化且非测试运行时写入文件
            stat_config_yml(data)  # 设置统计信息
            if not test_run:
                write_lang_yml(data, yaml)

            return data

        return wrapper

    return decorator


# 主函数
@yaml_file_interceptor()
def update_lang_files(lang_codes, files, test_run=False, file_yml=None):
    """
    处理语言文件(元数据)
    :param lang_files: 语言文件列表
    :param lang_data: 语言数据
    :param test_run: 是否测试运行
    :param data: 由拦截器注入的YAML数据
    """
    # 语言消息
    lang_data = parse_shell_files(files, TRIM_SPACE)

    for lang_code in ("_lang", *lang_codes):
        update_lang_properties(lang_code, lang_data, file_yml, test_run)


# =============================================================================
# 执行逻辑（从STDIN读取数据，调用主函数）
#
# shell调用方法：通过环境变量传参
# =============================================================================
def run_exec(opts):
    lang_codes = ["zh", "en"]  # 语言消息
    # 修改语言文件(yml和properties)
    update_lang_files(lang_codes, opts["file"])


# =============================================================================
# 调试测试函数（写入测试文件并验证更新逻辑）
# ./python/lang_util.py --file="bin/i18n.sh bin/init_main.sh" -l"zh en" --debug
# =============================================================================
def run_test(opts):
    # # 读取指定sh文件的消息数据，模拟写入_lang.yml和对应的properties文件
    # data = parse_shell_files(["bin/init_main.sh", "bin/i18n.sh", "bin/cmd_help.sh", "lib/hash_util.sh"])
    print("Debug mode is on. Running tests...")

    lang_codes = ["zh", "en"]  # 语言消息
    # 测试语言文件(yml和properties)
    data = update_lang_files(lang_codes, opts["file"], True)
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
