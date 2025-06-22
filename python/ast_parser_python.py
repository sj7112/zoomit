#!/usr/bin/env python3

from collections import OrderedDict
import os
from pathlib import Path
import re
import sys
from typing import List


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ast_parser import ASTParser, FuncParser
from hash_util import set_file_msgs, set_func_msgs
from file_util import get_code_files, read_file, write_array
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
# parse_code_files         主解析函数：解析代码文件，遇到函数，则进入解析
# ==============================================================================


class PythonASTParser(ASTParser):
    """
    AST parser class
    """

    # Class variables
    DIRS = ["python"]
    EXTS = "py"
    PATTERNS = r"(string|exiterr|error|success|warning|info)"

    def _parse_line_preprocess(self):
        """
        预处理行：移除注释部分和前后空格

        返回值:
        - processed_line: 处理后的行内容
        - status:
            0: 注释或空行
            1: 普通非函数行（需进一步解析）
            2: 是函数定义
            3: Multi-line 标记
        """
        line_content = self.lines[self.line_number]
        if re.match(r"^\s*#", line_content):
            return "", 0  # 整行注释

        line_content = re.sub(r"\s+#.*", "", line_content)  # 移除右侧注释
        line_content = line_content.strip()  # 去除前后空格
        self.line = line_content  # 保存简化后的行内容

        if not line_content:
            return 0  # 空行

        # 正则捕获组是函数名称
        func_match = re.match(r"^(\s*)def\s+(\w+)\s*\([^)]*\)\s*:", line_content)
        # func_match = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)\s*\{?", line_content)
        if func_match:
            # add new function parser
            indent = func_match.group(1)  # 缩进字符串
            indent = indent.count(" ") + indent.count("\t") * 4  # 1 tab = 4 space
            func_name = func_match.group(2)  # 函数名
            self.parsers.append(FuncParser.py(func_name, indent))
            return 2  # 多行函数定义

        # Multi-line string literals check
        if "'''" in line_content or '"""' in line_content:
            return 3  # Multi-line 标记

        # 检查单个括号
        if line_content == "{":
            return 8  # 单个左括号
        elif line_content == "}":
            return 9  # 单个右括号

        return 1  # 需进一步解析

    def _check_heredoc_block(self):
        """
        Check and process heredoc block

        Returns:
        - True: If heredoc block is encountered
        - False: If no heredoc block is encountered
        """
        lines = self.lines
        line = lines[self.line_number]

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
                self.line_number += 1
                if self.line_number >= len(self.lines):
                    return True
                if lines[self.line_number] == heredoc_end:
                    return True

        return False

    def _split_match_type(self):
        """
        Split and match function calls

        Split the line into possible function call segments
        """
        # Add leading space to avoid offset calculation errors
        line = " " + self.line

        # 完整匹配模式
        pattern = r"([\s;{\(\[]|&&|\|\|)" + self.PATTERNS + r"([\s;}\)\]]|&&|\|\||$)"

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

    def _extract_multi_lines(self, content):
        """
        单行直接返回；多行，添加多行数据并返回
        以下一个有效的双引号为结束条件
        如果TRIM_SPACE = True，则去掉字符串右侧的空格！！

        Example:
            exiterr "Usage: show_help_info [command]\n \
                Available commands: find, ls"

        Parameters:
        - content: Input string segment

        Returns:
        - content: Multi-line joined with \n
        """
        lines = self.lines
        # 检查是否多行文本
        if content.endswith("\\"):
            while self.line_number < len(lines) - 1:
                self.line_number += 1
                content += "\n"  # 增加换行
                line = lines[self.line_number]
                content_match = re.match(r'^(.*?)(?<!\\)"', line)  # 采用双引号结束（读取代码文件）
                if content_match:  # 最后一行
                    content += content_match.group(1)
                    return content.rstrip() if self.trim_space else content
                else:  # 中间行
                    content += line.rstrip()

        return content.rstrip() if self.trim_space else content

    def _parse_match_type(self, segment):
        """
        解析脚本行中的函数调用信息

        Parameters:
        - segment: Current script text segment
        """
        # 跳过：空行 | 含 -i 的行
        if not segment or "-i" in segment:
            return

        # 提取第一个字段（命令名）
        cmd = segment.split()[0] if segment.split() else ""
        ln_no = self.line_number + 1
        # 提取双引号之间内容
        result = self._extract_quoted_string(segment)
        if not result:
            return
        else:
            content = self._extract_multi_lines(result)
        # 将结果添加到全局数组
        results = self.parsers[-1].result_lines  # get last function parser
        results.append(f"{cmd} {ln_no} {content}")

    def _parse_function(self, file_rec):
        """
        处理函数内容，递归解析函数体
        """

        # 处理函数体内容
        while True:
            self.line_number += 1
            if self.line_number >= len(self.lines):
                break

            status = self._parse_line_preprocess()
            curr_parser = self.parsers[-1]
            match status:
                case 0:
                    continue  # 注释、空行、单行函数：跳过
                case 2:
                    self._parse_function(file_rec)
                case 3:
                    if self._check_heredoc_block():
                        continue
                case 8:
                    curr_parser.brace_count += 1  # 出现左括号，计数器+1
                case 9:
                    curr_parser.brace_count -= 1  # 出现右括号，计数器-1
                    if curr_parser.brace_count <= 0:
                        if curr_parser.result_lines:
                            set_func_msgs(file_rec, curr_parser.func_name, curr_parser.result_lines)

                        self.parsers.pop()  # remove current function parser
                        return  # end of function

            # 解析匹配项
            matches = self._split_match_type()
            for matched in matches:
                self._parse_match_type(matched)


# =============================================================================
# Debug test function
# ./python/ast_parser.py bin/i18n.sh bin/init_main.sh
# =============================================================================
def main():
    parser = PythonASTParser()
    print_array(parser.parse_code_files(sys.argv[1:]))


# =============================================================================
# Command-line entry point
# =============================================================================
if __name__ == "__main__":
    main()
