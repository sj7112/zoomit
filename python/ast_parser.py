#!/usr/bin/env python3

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import List


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.hash_util import set_file_msgs, set_func_msgs
from python.file_util import get_code_files, read_file


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


@dataclass
class FuncParser:

    name: str  # function name
    line_no: int  # line number
    brace_count: int = 0  # function brace ounts (for shell)
    indent: int = 0  # function indent (only for python)
    end_flag: bool = False  # sign of function ended
    results: List[str] = field(default_factory=list)  # function parse result set

    @classmethod
    def sh(cls, name: str, line_no: int, brace_count: int = 0):
        return cls(name=name, line_no=line_no, brace_count=brace_count)

    @classmethod
    def py(cls, name: str, line_no: int, indent: int = 0):
        return cls(name=name, line_no=line_no, indent=indent)


def count_indent(line: str) -> int:
    """count indent size for Python code line"""
    count = 0
    for ch in line:
        if ch == "\t":
            count += 4
        elif ch == " ":
            count += 1
        else:
            break
    return count


class ASTParser:
    """
    AST parser class
    """

    # Class variables
    PARENT_DIR = Path(__file__).resolve().parent.parent
    DUPL_HASH = "Z-HASH"  # Hash pool (duplicate hashes are not allowed in a file)

    def __init__(self, trim_space=False):
        """
        Initialize the parser
        """
        self.trim_space: bool = trim_space

        self.code_file: str
        self.results: List = []

        self.lines: List[str]
        self.line_number: int
        self.parsers: List[FuncParser]  # nested functions, may have multiple items
        self.line: str  # used by _split_match_type
        self.indent: int  # calc the indent for Python code line

    def strip_comment_and_calc_indent(self):
        """calculate indents, remove comments, and trim result"""

        line = self.lines[self.line_number]

        if re.match(r"^\s*(#|$)", line):
            return None  # comment line | blank line

        self.indent = count_indent(line)  # Number of leading blanks (tab=4space)
        line = line.strip()  # remove leading and trailing spaces
        self.line = line

        # 1. Check if the line is a continuation (ends with a backslash)
        if self.EXTS == "sh" and line.endswith("\\"):
            return line

        in_single = False
        in_double = False
        escape = False

        # 2. Check if the line has comments
        for i, c in enumerate(line):
            if escape:
                escape = False
                continue

            if c == "\\":
                escape = True
                continue

            if c == "'" and not in_double:
                in_single = not in_single
                continue

            if c == '"' and not in_single:
                in_double = not in_double
                continue

            if c == "#" and not in_single and not in_double:
                if self.EXTS == "sh" and i > 0 and not line[i - 1].isspace():
                    continue  # shell comments, must have one leading space, e.g. " #"

                self.line = line[:i].rstrip()  # remove comments and blank spaces
                return self.line

        # 3. trim result and return
        return line

    def parse_function_end(self):
        """
        Finish parse function
        """
        if not self.parsers:
            return

        processed_count = 0
        for parser in self.parsers:
            if not parser.end_flag:
                break
            if parser.results:
                file_rec = self.results[self.code_file]
                set_func_msgs(file_rec, parser.name, parser.results)
            processed_count += 1

        # Remove the finished items at once
        if processed_count:
            self.parsers = self.parsers[processed_count:]

    def parse_code_files(self, target):
        """
        Main parsing function: Parse code files

        Parameters:
        - target: Path of code files to parse
        """
        code_files = get_code_files(self.DIRS, self.EXTS, target)  # File list
        self.results = {}  # File => Function | Messages

        for code_file in code_files:
            # Read file content
            self.lines = read_file(code_file)
            code_file = str(Path(code_file).relative_to(self.PARENT_DIR))  # Relative path to project root
            self.code_file = code_file
            self.line_number = 0
            self.parsers = []
            self.results[code_file] = {self.DUPL_HASH: {}}

            while self.line_number < len(self.lines):
                self._parse_function()

            set_file_msgs(self.results, code_file)

        return self.results
