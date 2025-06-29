#!/usr/bin/env python3

from pathlib import Path
import re
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.lang.ast_parser import ASTParser, FuncParser
from python.debug_tool import print_array


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


class ShellASTParser(ASTParser):
    """
    AST parser class
    """

    # Class variables
    DIRS = ["bin", "lib"]
    EXTS = "sh"
    PATTERNS = "exiterr|error|success|warning|info|string|_mf"

    def _set_function_end_flag(self):
        """python set function end flag"""
        if not self.parsers:
            return False

        parser = self.parsers[0]
        parser.end_flag = True  # set function end flag by indenting

        return True

    def _parse_line_preprocess(self):
        """
        预处理行：移除注释部分和前后空格

        返回值:
        - processed_line: 处理后的行内容
        - status:
            0: 注释、空行、单行函数
            1: 普通非函数行（需进一步解析）
            2: 是函数定义且不是单行函数
            3: heredoc 标记
            8: 单个左括号
            9: 单个右括号
        """
        if self.line_number >= len(self.lines):
            self._set_function_end_flag()
            return 9  # end of file

        line_content = self.strip_comment_and_calc_indent()  # 移除右侧注释
        if not line_content:
            return 0  # 整行注释或空白：跳过

        # 正则捕获组是函数名称
        func_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)\s*(\{)?", line_content)
        if func_match:
            if re.search(r"\}\s*$", line_content):
                return 0  # 单行函数：跳过
            else:
                # add new function parser (name, brace_counts)
                func_name = func_match.group(1)  # 函数名
                brace_count = 1 if func_match.group(2) else None
                self.parsers.insert(0, FuncParser.sh(func_name, self.line_number, brace_count))
                if len(self.parsers) == 1:
                    return 0  # 主函数初始化：继续
                else:
                    return 2  # 子函数初始化：递归

        # heredoc check： include << not include <<<
        if "<<" in line_content and "<<<" not in line_content:
            if self._check_heredoc_block():
                return 0  # heredoc 标记：跳过

        # 检查单个括号
        if self.parsers:
            parser = self.parsers[0]
            if line_content == "{":
                parser.brace_count += 1  # 出现左括号，计数器+1
            elif line_content == "}":
                parser.brace_count -= 1  # 出现右括号，计数器-1
                if parser.brace_count <= 0:
                    self._set_function_end_flag()
                    return 9  # 函数结束条件：单个右括号

            return 1  # 需进一步解析

        return 0  # 异常处理：不在函数内部

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
        pattern = r"([\s;{\(\[]|&&|\|\|)" + f"({self.PATTERNS})" + r"([\s;}\)\]]|&&|\|\||$)"

        last_pos = 0

        for match in re.finditer(pattern, line):
            match_start = match.start(2)  # 函数关键字开始位置
            if last_pos > 0:
                segment = line[last_pos:match_start]
                # # 移除前导符号
                # if segment.startswith("&&") or segment.startswith("||"):
                #     segment = segment[2:]
                # elif segment[0] in " ;{([":
                #     segment = segment[1:]
                self._parse_match_type(segment)
            last_pos = match_start  # 更新上一个函数关键字的开始位置

        # 处理最后一个匹配之后的部分
        if last_pos > 0:
            segment = line[last_pos:]
            # # 移除前导符号
            # if segment.startswith("&&") or segment.startswith("||"):
            #     segment = segment[2:]
            # elif segment and segment[0] in " ;{([":
            #     segment = segment[1:]
            self._parse_match_type(segment)

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

        # 空内容视为无效
        if not content:
            return None

        # 拒绝纯变量引用（如$abc; $abc123; $123）
        if re.match(r"^\$([a-zA-Z][a-zA-Z0-9_]*|\d+)$", content):
            return None

        # 判断是否多行文本
        if content.endswith("\\"):
            content = self._extract_multi_lines(content)

        return content.rstrip() if self.trim_space else content

    def _extract_multi_lines(self, content):
        """
        添加多行数据并返回
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
        # 检查是否多行文本
        lines = self.lines
        while self.line_number < len(lines):
            content += "\n"  # Add a newline
            line = lines[self.line_number]
            content_match = re.match(r'^(.*?)(?<!\\)"', line)  # 采用双引号结束（读取代码文件）
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
        if not segment or "-i" in segment:
            return

        # 提取第一个字段（命令名）
        cmd = segment.split()[0] if segment.split() else ""
        ln_no = self.line_number
        # 提取双引号之间内容
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
                    continue  # comment line / blank line / one-line func / heredoc / main function
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
# ./python/ast_parser.py bin/i18n.sh bin/init_main.sh
# =============================================================================
def main():
    sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path
    parser = ShellASTParser()
    print_array(parser.parse_code_files(sys.argv[1:]))


# =============================================================================
# Command-line entry point
# =============================================================================
if __name__ == "__main__":
    print(str(Path(__file__).resolve().parent.parent))
    main()
