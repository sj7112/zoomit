#!/usr/bin/env python3

from pathlib import Path
import re
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.debug_tool import print_array
from python.lang.ast_parser import ASTParser, FuncParser


# ==============================================================================
# parse_line_preprocess     预处理行：移除注释部分和前后空格
# check_heredoc_block       检查并处理heredoc块
# split_match_type          分割并匹配函数调用
# extract_quoted_string     提取字符串中第一个未转义双引号之间的内容
# parse_match_type          解析脚本行中的函数调用信息
# parse_function            处理函数内容，递归解析函数体
# parse_code_files          主解析函数：解析代码文件，遇到函数，则进入解析
# ==============================================================================


class PythonASTParser(ASTParser):
    """
    AST parser class
    """

    # Class variables
    DIRS = ["python"]
    EXTS = "py"

    def _set_function_end_flag(self):
        """python set function end flag"""
        if not self.parsers:
            return False

        end_flag: bool = False
        for parser in self.parsers:
            if self.indent > parser.indent:
                break
            parser.end_flag = True  # set function end flag by indenting
            end_flag = True

        return end_flag

    def _parse_line_preprocess(self):
        """
        Preprocess the line: remove comments and trim leading/trailing spaces

        Return values:
        - processed_line: The processed line content
        - status:
            0: Skip line: comments, blank line
            1: Normal content line (requires further parsing)
            2: Function definition line
            9: End of function or code file
        """
        if self.line_number >= len(self.lines):
            self.indent = 0
            self._set_function_end_flag()
            return 9  # end of file

        line_content = self.strip_comment_and_calc_indent()  # 移除右侧注释
        if not line_content:
            return 0  # 整行注释或空白：跳过

        if self._set_function_end_flag():
            self.line_number -= 1  # 回退一行，先处理函数结束，再重新处理当前行
            return 9  # 函数结束条件：未缩进

        # 正则捕获组是函数名称
        func_match = re.match(r"^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line_content)
        if func_match:
            func_name = func_match.group(1)  # 函数名

            # add new function parser
            self.parsers.insert(0, FuncParser.py(func_name, self.line_number, self.indent))
            if len(self.parsers) == 1:
                return 0  # 主函数初始化：继续
            else:
                return 2  # 子函数初始化：递归

        # Multi-line string literals check
        if "'''" in line_content or '"""' in line_content:
            if self._check_heredoc_block():
                return 0  # Multi-line ：跳过

        if self.parsers:
            return 1  # 需进一步解析

        return 0  # 异常处理：不在函数内部

    def _check_heredoc_block(self):
        """
        Check and process heredoc block

        Returns:
        - True: If heredoc block is encountered
        - False: If no heredoc block is encountered
        """
        line = self.lines[self.line_number]

        triple_match = re.search(r"(\"\"\"|''')", line)
        quote = triple_match.group(1)
        quote_start = triple_match.start()
        quote_end = triple_match.end()

        # 向前检查，排除这种可能性：前方是函数（函数调用内的参数）
        prefix = line[:quote_start]
        if re.search(rf"{self.PATTERNS}\s*\(", prefix.strip()):
            return False

        # 向后检查，排除quote在同一行的情况：后面可能有函数（函数调用内的参数）
        triple_match2 = re.search(f"{quote}", line[quote_end:])
        if triple_match2:
            return False

        # 从下一行开始搜索 heredoc 结束
        while True:
            self.line_number += 1
            if self.line_number >= len(self.lines):
                return True
            if re.search(f"{quote}", self.lines[self.line_number]):
                return True

    def _split_match_type(self):
        """
        Split and match function calls

        Split the line into possible function call segments
        """
        # Add leading space to avoid offset calculation errors
        line = " " + self.line

        # match left : ' ' OR ',' OR ';' OR '=' OR '{' OR '(' OR '['
        # match right: '(' OR 'SPACES' + '('
        pattern = r"([\s,;={(\[])" + f"({self.PATTERNS})" + r"\s*\("

        last_pos = 0

        for match in re.finditer(pattern, line):
            match_start = match.start(2)  # 函数关键字开始位置
            if last_pos > 0:
                segment = line[last_pos:match_start]
                self._parse_match_type(segment)
            last_pos = match_start  # 更新上一个函数关键字的开始位置

        # 处理最后一个匹配之后的部分
        if last_pos > 0:
            segment = line[last_pos:]
            self._parse_match_type(segment)

    def _extract_quoted_string(self, segment):
        """
        提取字符串中第一个未转义单引号 / 双引号之间的内容

        Parameters:
        - segment: 输入字符串段落

        Returns:
        - 提取的内容，如果不满足条件则返回None
        """
        # 查找左括号
        while True:
            match = re.search(r"\(\s*(.*)", segment)
            if not match:
                if self.line_number >= len(self.lines):
                    return None  # 异常处理，到达文件末尾

                segment = self.lines[self.line_number]
                self.line_number += 1
                continue
            content = match.group(1)
            break

        # 跳过空行
        while True:
            if not content.rstrip():
                if self.line_number >= len(self.lines):
                    return None  # 异常处理，到达文件末尾

                content = self.lines[self.line_number].lstrip()
                self.line_number += 1
                continue
            break

        # 处理可能的字符串前缀：r, f, b, u 及其组合（确保第一个字符为单引号或双引号）
        match = re.match(r'^[rRfFbBuU]{1,2}(["\'].*)$', content)
        if match:
            content = match.group(1)

        # 保留单引号或双引号开始的行内容
        if content.startswith("'''") or content.startswith('"""'):
            content = self._extract_multi_lines(content)  # 多行文本
        elif content.startswith("'") or content.startswith('"'):
            content = self._extract_single_line(content)  # 单行文本
        else:
            return None  # 异常处理（非单引号/双引号开头）

        # 空内容视为无效
        if not content:
            return None

        return content.rstrip() if self.trim_space else content

    def _extract_single_line(self, content):
        """
        获取单行数据并返回（截断未转义的结束引号，跳过转义的引号）
        """
        if content[0] == '"':
            content_match = re.match(r'^"(.*?)(?<!\\)"', content)  # 取双引号中内容
        else:
            content_match = re.match(r"^'(.*?)(?<!\\)'", content)  # 取单引号中内容

        if not content_match:
            return None

        content = content_match.group(1)

        # 拒绝纯变量引用（如{abc}; {abc123}; {1}）
        if re.match(r"^\{([a-zA-Z][a-zA-Z0-9_]*|\d+)?\}$", content):
            return None

        return content

    def _extract_multi_lines(self, content):
        """
        添加多行数据并返回
        以下一个有效的单引号 / 双引号为结束条件
        如果TRIM_SPACE = True，则去掉字符串右侧的空格！！

        Example:
        exiterr(
            '''Usage: show_help_info [command]
            Available commands: find, ls   '''
        )

        Parameters:
        - content: Input string segment

        Returns:
        - content: Multi-line joined with 3 single/double quote
        """
        pattern = content[:3]  # '''或"""
        content = content[3:]  # 第一行内容

        # 检查结束条件是否在同一行
        content_match = re.match(r"^(.*?)(?<!\\)" + f"{pattern}", content)  # 采用单引号 / 双引号结束（读取代码文件）
        if content_match:
            return content_match.group(1)

        # 检查是否多行文本
        lines = self.lines
        while self.line_number < len(lines):
            content += "\\"  # Add "\" (used as a multi-line reading marker when reading messages)
            content += "\n"  # Add a newline
            line = self.lines[self.line_number]
            content_match = re.match(r"^(.*?)(?<!\\)" + f"{pattern}", line)  # 采用单引号 / 双引号结束（读取代码文件）
            if content_match:  # 最后一行
                content += content_match.group(1)
                return content
            else:  # 中间行
                content += line
                self.line_number += 1

        return content

    def _parse_match_type(self, segment):
        """
        解析脚本行中的函数调用信息

        Parameters:
        - segment: Current script text segment
        """
        # 跳过：空行 | 含 -i 的行
        if not segment or "ignore=True" in segment:
            return

        # 提取第一个字段（命令名）
        match = re.match(rf"^({self.PATTERNS})", segment)
        cmd = match.group(1)
        ln_no = self.line_number
        # 提取单引号/双引号之间内容
        content = self._extract_quoted_string(segment)
        if not content:
            return

        # 将结果添加到全局数组
        results = self.parsers[0].results  # get last function parser
        results.append(f"{cmd} {ln_no} {content}")

    def _parse_function(self):
        """
        处理函数内容，递归解析函数体
        """

        # 处理函数体内容
        while True:
            status = self._parse_line_preprocess()
            self.line_number += 1
            match status:
                case 0:
                    continue  # 注释、空行、Multi-line：跳过
                case 1:
                    self._split_match_type()  # Parse matching items
                case 2:
                    self._parse_function()
                    return  # sub function
                case 9:
                    self.parse_function_end()
                    return  # end of function | end of file


# =============================================================================
# Debug test function
# ./python/ast_parser.py python/i18n.py python/docker_util.py
# =============================================================================
def main():
    parser = PythonASTParser()
    print_array(parser.parse_code_files(sys.argv[1:]))


# =============================================================================
# Command-line entry point
# =============================================================================
if __name__ == "__main__":
    main()
