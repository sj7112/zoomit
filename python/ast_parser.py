#!/usr/bin/env python3

from collections import OrderedDict
import os
from pathlib import Path
import re
import sys

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hash_util import set_file_msgs, set_func_msgs
from file_util import get_shell_files, read_file, write_array
from debug_tool import print_array


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


class ASTParser:
    """
    AST parser class
    """

    # Class variables
    PARENT_DIR = Path(__file__).parent.parent.resolve()
    DUPL_HASH = "Z-HASH"  # Hash pool (duplicate hashes are not allowed in a file)

    def __init__(self, trim_space=False):
        """
        Initialize the parser
        """
        self.trim_space = trim_space

    def _parse_line_preprocess(self, line_content):
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
                return line_content, 2  # 多行函数定义

        # heredoc 检查：包含 << 但不包含 <<<
        if "<<" in line_content and "<<<" not in line_content:
            return line_content, 3  # heredoc 标记

        # 检查单个括号
        if line_content == "{":
            return line_content, 8  # 单个左括号
        elif line_content == "}":
            return line_content, 9  # 单个右括号

        return line_content, 1  # 需进一步解析

    def _check_heredoc_block(self, lines, line_number, total_lines):
        """
        Check and process heredoc block

        Parameters:
        - lines: List of all lines
        - line_number: Reference to current line number
        - total_lines: Total number of lines

        Returns:
        - True: If heredoc block is encountered
        - False: If no heredoc block is encountered
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
        match = re.search(r"<<-?\s*([A-Za-z0-9_]+)", stripped_line)
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

    def _get_function_name(self, line):
        """
        Extract function name from function definition line
        """
        match = re.match(r"^\s*([a-zA-Z0-9_]+)\s*\(\)\s*\{?", line)
        if match:
            return match.group(1)
        return ""

    def _init_brace_count(self, line):
        """
        Initialize brace counter
        """
        return 1 if re.search(r"\{$", line) else 0

    def _split_match_type(self, line):
        """
        Split and match function calls

        Split the line into possible function call segments
        """
        # Add leading space to avoid offset calculation errors
        line = " " + line

        # 要匹配的函数模式
        function_pattern = r"(string|exiterr|error|success|warning|info)"

        # 完整匹配模式
        pattern = r"([\s;{\(\[]|&&|\|\|)" + function_pattern + r"([\s;}\)\]]|&&|\|\||$)"

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

    def _extract_quoted_string(self, segment):
        """
        提取字符串中第一个未转义双引号之间的内容

        Parameters:
        - segment: 输入字符串段落

        Returns:
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

    def _extract_multi_lines(self, content, lines, line_number):
        """
        单行直接返回；多行，添加多行数据并返回
        以下一个有效的双引号为结束条件
        如果TRIM_SPACE = True，则去掉字符串右侧的空格！！

        Example:
            exiterr "Usage: show_help_info [command]\n \
                Available commands: find, ls"

        Parameters:
        - content: Input string segment
        - lines: Multi-line data to process
        - line_number: For multi-line, dynamically modify this variable

        Returns:
        - content: Multi-line joined with \n
        """
        # 检查是否多行文本
        if content.endswith("\\"):
            while line_number[0] < len(lines) - 1:
                line_number[0] += 1
                content += "\n"  # 增加换行
                line = lines[line_number[0]]
                content_match = re.match(r'^(.*?)(?<!\\)"', line)  # 采用双引号结束（读取代码文件）
                if content_match:  # 最后一行
                    content += content_match.group(1)
                    return content.rstrip() if self.trim_space else content
                else:  # 中间行
                    content += line.rstrip()

        return content.rstrip() if self.trim_space else content

    def _parse_match_type(self, segment, lines, line_number, results):
        """
        解析脚本行中的函数调用信息

        Parameters:
        - segment: Current script text segment
        - line_number: Current line number
        """
        # 跳过：空行 | 含 -i 的行
        if not segment or "-i" in segment:
            return

        # 提取第一个字段（命令名）
        cmd = segment.split()[0] if segment.split() else ""
        ln_no = line_number[0] + 1
        # 提取双引号之间内容
        result = self._extract_quoted_string(segment)
        if not result:
            return
        else:
            content = self._extract_multi_lines(result, lines, line_number)
        # 将结果添加到全局数组
        results.append(f"{cmd} {ln_no} {content}")

    def _parse_function(self, lines, line_number, total_lines, file_rec):
        """
        处理函数内容，递归解析函数体

        Parameters:
        - lines: List of all lines
        - line_number: Reference to current line number (list form for modification)
        - total_lines: Total number of lines
        """
        current_line = lines[line_number[0]]
        func_name = self._get_function_name(current_line)
        brace_count = self._init_brace_count(current_line)
        result_lines = []  # 分函数结果集

        # 处理函数体内容
        while True:
            line_number[0] += 1
            if line_number[0] >= total_lines:
                break

            line, status = self._parse_line_preprocess(lines[line_number[0]])

            match status:
                case 0:
                    continue  # 注释、空行、单行函数：跳过
                case 2:
                    self._parse_function(lines, line_number, total_lines, file_rec)
                case 3:
                    if self._check_heredoc_block(lines, line_number, total_lines):
                        continue
                case 8:
                    brace_count += 1  # 出现左括号，计数器+1
                case 9:
                    brace_count -= 1  # 出现右括号，计数器-1
                    if brace_count <= 0:
                        if result_lines:
                            set_func_msgs(file_rec, func_name, result_lines)
                        return  # 函数结束

            # 解析匹配项
            matches = self._split_match_type(line)
            for matched in matches:
                self._parse_match_type(matched, lines, line_number, result_lines)

    def parse_shell_files(self, target):
        """
        主解析函数：解析shell文件

        Parameters:
        - sh_file: Path to shell file to parse
        """
        sh_files = get_shell_files(target)  # File list
        results = {}  # File => Function | Messages

        for sh_file in sh_files:
            # Read file content
            lines = read_file(sh_file)
            line_number = [0]  # Wrap in list so functions can modify
            total_lines = len(lines)

            sh_file = str(Path(sh_file).relative_to(self.PARENT_DIR))  # Relative path to project root
            results[sh_file] = {self.DUPL_HASH: {}}

            while line_number[0] < total_lines:
                line, status = self._parse_line_preprocess(lines[line_number[0]])
                if status == 2:  # Function definition
                    self._parse_function(lines, line_number, total_lines, results[sh_file])
                line_number[0] += 1

            set_file_msgs(results, sh_file)

        return results


# =============================================================================
# Debug test function
# ./python/ast_parser.py bin/i18n.sh bin/init_main.sh
# =============================================================================
def main():
    parser = ASTParser()
    print_array(parser.parse_shell_files(sys.argv[1:]))


# =============================================================================
# Command-line entry point
# =============================================================================
if __name__ == "__main__":
    main()
