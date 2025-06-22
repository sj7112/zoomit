#!/usr/bin/env python3

from collections import OrderedDict
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import sys
from typing import List


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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


@dataclass
class FuncParser:

    name: str  # function name
    brace_count: int = 0  # function brace ounts (for shell)
    indent: int = 0  # function indent (only for python)
    results: List[str] = field(default_factory=list)  # function parse result set

    @classmethod
    def sh(cls, name: str, brace_count: int = 0):
        return cls(name=name, brace_count=brace_count)

    @classmethod
    def py(cls, name: str, indent: int = 0):
        return cls(name=name, indent=indent)


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
        self.trim_space: bool = trim_space
        self.code_file: str
        self.lines: List[str]
        self.line_number: int
        self.line: str  # used by _split_match_type
        self.parsers: List[FuncParser] = []

    def parse_code_files(self, target):
        """
        Main parsing function: Parse code files

        Parameters:
        - target: Path of code files to parse
        """
        code_files = get_code_files(self.DIRS, self.EXTS, target)  # File list
        results = {}  # File => Function | Messages

        for code_file in code_files:
            # Read file content
            self.lines = read_file(code_file)
            code_file = str(Path(code_file).relative_to(self.PARENT_DIR))  # Relative path to project root
            self.code_file = code_file
            self.line_number = 0

            results[code_file] = {self.DUPL_HASH: {}}

            while self.line_number < len(self.lines):
                status = self._parse_line_preprocess()
                if status == 2:  # Function definition
                    self._parse_function(results[code_file])
                self.line_number += 1

            set_file_msgs(results, code_file)

        return results
