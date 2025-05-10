#!/usr/bin/env python3

import os
from pathlib import Path
import re
import sys


# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).parent.parent.resolve()

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hash_util import (
    set_prop_msgs,
)

from file_util import (
    get_shell_files,
    read_file,
)

from debug_tool import (
    print_array,
)


# ==============================================================================
# parse_line_preprocess     预处理行：移除注释部分和前后空格
# check_heredoc_block       检查并处理heredoc块
# get_function_name         从函数定义行中提取函数名
# init_brace_count          初始化大括号计数器
# split_match_type          分割并匹配函数调用
# extract_quoted_string     提取字符串中第一个未转义双引号之间的内容
# parse_match_type          解析脚本行中的函数调用信息
# parse_function            处理函数内容，递归解析函数体
# parse_shell_files         主解析函数：解析shell文件，遇到函数，则进入解析
# ==============================================================================


def parse_line_preprocess(line_content):
    """
    预处理行：移除注释部分和前后空格

    返回值:
    - processed_line: 处理后的行内容
    - status:
        0: 注释或空行
        1: 普通非函数行或单行函数（需进一步解析）
        2: 是函数定义且不是单行函数
        3: heredoc 标记
        8: 单个左括号
        9: 单个右括号
    """
    # 处理注释行
    if re.match(r"^\s*#", line_content):
        return "", 0  # 整行注释

    line_content = re.sub(r"\s+#.*", "", line_content)  # 移除右侧注释
    line_content = line_content.strip()  # 去除前后空格

    if not line_content:
        return "", 0  # 空行

    # 函数定义检测
    func_match = re.match(r"^\s*(\w+)\s*\(\)\s*\{?", line_content)
    if func_match:
        if re.search(r"\}\s*$", line_content):
            return "", 0  # 单行函数：跳过
        else:
            return line_content, 2  # 多行函数定义（直接返回函数名！！）

    # heredoc 检查：包含 << 但不包含 <<<
    if "<<" in line_content and "<<<" not in line_content:
        return line_content, 3  # heredoc 标记

    # 检查单个括号
    if line_content == "{":
        return line_content, 8  # 单个左括号
    elif line_content == "}":
        return line_content, 9  # 单个右括号

    return line_content, 1  # 需进一步解析


def check_heredoc_block(lines, line_number, total_lines):
    """
    检查并处理heredoc块

    参数:
    - lines: 所有行的列表
    - line_number: 当前行号的引用
    - total_lines: 总行数

    返回:
    - True: 如果遇到heredoc块
    - False: 如果没有遇到heredoc块
    """
    line = lines[line_number[0]]

    # 去除单双引号里的内容
    def remove_quotes(text):
        # 移除双引号内容
        text = re.sub(r'"([^"\\]|\\.)*"', "", text)
        # 移除单引号内容
        text = re.sub(r"'([^'\\]|\\.)*'", "", text)
        return text

    stripped_line = remove_quotes(line)

    # 查找heredoc标记
    match = re.search(r"<<-?\s*([_A-Za-z0-9]+)", stripped_line)
    if match:
        heredoc_end = match.group(1)
        # 从下一行开始搜索 heredoc 结束
        while True:
            line_number[0] += 1
            if line_number[0] >= total_lines:
                return True
            if lines[line_number[0]] == heredoc_end:
                return True

    return False


def get_function_name(line):
    """
    从函数定义行中提取函数名
    """
    match = re.match(r"^\s*([a-zA-Z0-9_]+)\s*\(\)\s*\{?", line)
    if match:
        return match.group(1)
    return ""


def init_brace_count(line):
    """
    初始化大括号计数器
    """
    return 1 if re.search(r"\{$", line) else 0


def split_match_type(line):
    """
    分割并匹配函数调用

    将行分割成可能的函数调用段落
    """
    # 添加前导空格以避免偏移计算错误
    line = " " + line

    # 要匹配的函数模式
    function_pattern = r"(string|exiterr|error|success|warning|info)"

    # 完整匹配模式
    pattern = r"([\s;{\(\[]|&&|\|\|)(" + function_pattern + r")([\s;}\)\]]|&&|\|\||$)"

    matches = []
    last_pos = 0

    for match in re.finditer(pattern, line):
        match_start = match.start(2)  # 函数关键字开始位置

        if last_pos > 0:
            segment = line[last_pos:match_start]
            # 移除前导符号
            if segment.startswith("&&") or segment.startswith("||"):
                segment = segment[2:]
            elif segment[0] in " ;{([":
                segment = segment[1:]
            matches.append(segment)

        last_pos = match_start  # 更新上一个函数关键字的开始位置

    # 处理最后一个匹配之后的部分
    if last_pos > 0:
        segment = line[last_pos:]
        # 移除前导符号
        if segment.startswith("&&") or segment.startswith("||"):
            segment = segment[2:]
        elif segment and segment[0] in " ;{([":
            segment = segment[1:]
        matches.append(segment)

    return matches


def extract_quoted_string(segment):
    """
    提取字符串中第一个未转义双引号之间的内容

    参数:
    - segment: 输入字符串段落

    返回:
    - 提取的内容，如果不满足条件则返回None
    """
    # 查找第一个双引号
    match = re.search(r'"(.*)', segment)
    if not match:
        return None

    content = match.group(1)

    # 截断未转义的结束引号(前面不能有转义字符"\")
    content_match = re.match(r'^(.*?)(?<!\\)"', content)
    if content_match:
        content = content_match.group(1)

    # 拒绝纯变量引用（如$abc; $abc123; $123）
    if re.match(r"^\$([a-zA-Z][a-zA-Z0-9_]*|\d+)$", content):
        return None

    # 空内容视为无效
    if not content:
        return None

    return content


def extract_multi_lines(content, lines, line_number):
    """
    如果为当红，直接返回；如果为多行，添加多行数据并返回

    参数:
    - content: 输入字符串段落
    - lines: 待处理多行数据
    - line_number：如为多行，动态修改此变量

    返回:
    - content：如为多行，直接修改content内容（用\n拼接）
    - ln_cnt：返回行数（如为多行，返回实际行数）
    """
    ln_cnt = 1
    # 检查是否多行文本
    if content.endswith("\\"):
        while line_number[0] < len(lines):
            line_number[0] += 1
            line = lines[line_number[0]]
            ln_cnt += 1
            content_match = re.match(r'^(.*?)(?<!\\)"', line)
            if content_match:
                content += "\n" + content_match.group(1)
                return content, ln_cnt
            else:
                content += "\n" + line

    return content, ln_cnt


def parse_match_type(segment, lines, line_number, results):
    """
    解析脚本行中的函数调用信息

    参数:
    - segment: 当前处理的脚本文本段
    - line_number: 当前行号
    """
    # 跳过：空行 | 含 -i 的行
    if not segment or "-i" in segment:
        return

    # 提取第一个字段（命令名）
    cmd = segment.split()[0] if segment.split() else ""

    ln_no = line_number[0] + 1

    # 提取双引号之间内容
    result = extract_quoted_string(segment)
    if not result:
        return
    else:
        (content, ln_cnt) = extract_multi_lines(result, lines, line_number)

    # 将结果添加到全局数组
    results.append(f"{cmd} {ln_no} {ln_cnt} {content}")


def parse_function(lines, line_number, total_lines, sh_file, file_records):
    """
    处理函数内容，递归解析函数体

    参数:
    - lines: 所有行的列表
    - line_number: 当前行号的引用(列表形式，以便可以修改)
    - total_lines: 总行数
    - sh_file: 源文件名
    """
    current_line = lines[line_number[0]]
    func_name = get_function_name(current_line)
    brace_count = init_brace_count(current_line)
    result_lines = []  # 分函数结果集

    # 处理函数体内容
    while True:
        line_number[0] += 1
        if line_number[0] >= total_lines:
            break

        line, status = parse_line_preprocess(lines[line_number[0]])

        match status:
            case 0:
                continue  # 注释、空行、单行函数：跳过
            case 2:
                parse_function(lines, line_number, total_lines, sh_file, file_records)  # 递归解析嵌套函数
            case 3:
                if check_heredoc_block(lines, line_number, total_lines):  # 检测heredoc块
                    continue
            case 8:
                brace_count += 1  # 出现左括号，计数器+1
            case 9:
                brace_count -= 1  # 出现右括号，计数器-1
                if brace_count <= 0:
                    # hash：转换"文件名@@函数名"；msgs：key=hash, value=msg # type@linNo@order
                    if result_lines:
                        file_records[func_name] = set_prop_msgs(result_lines)
                    return  # 函数结束

        # 解析匹配项
        matches = split_match_type(line)
        for matched in matches:
            parse_match_type(matched, lines, line_number, result_lines)


def parse_shell_files(target):
    """
    主解析函数：解析shell文件，遇到函数，则进入解析

    参数:
    - sh_file: 要解析的shell文件路径
    """
    sh_files = get_shell_files(target)  # 文件列表
    results = {}  # 文件=>函数 | 消息

    for sh_file in sh_files:
        # 读取文件内容
        lines = read_file(sh_file)
        line_number = [0]  # 使用列表包装，以便函数可以修改
        total_lines = len(lines)

        sh_file = str(Path(sh_file).relative_to(PARENT_DIR))  # 相对工程的根路径
        results[sh_file] = {}

        while line_number[0] < total_lines:
            line, status = parse_line_preprocess(lines[line_number[0]])

            if status == 2:  # 函数定义
                parse_function(lines, line_number, total_lines, sh_file, results[sh_file])

            line_number[0] += 1
    return results


# =============================================================================
# 调试测试函数
# =============================================================================
def main():  # 获取输入参数（如果没传，就设置为 None）
    print_array(parse_shell_files(sys.argv[1:]))  # 打印解析结果


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    main()
