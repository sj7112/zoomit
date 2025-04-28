#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_AST_PARSER:-}" ]]; then
  LOADED_AST_PARSER=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  source "$LIB_DIR/msg_handler.sh"

  # Shell AST 解析器
  # 用于解析 shell 脚本中的特定函数调用

  # ==============================================================================
  # 移除注释部分和前后空格
  # exit 0：注释或空行
  # exit 1：普通非函数行或单行函数（不输出）
  # exit 2：是函数定义且不是单行函数（输出处理后的行）
  # ==============================================================================
  parse_line_preprocess() {
    local -n out="$1" # 引用传入变量
    local idx="$2"    # 行号索引

    # 使用 perl 处理注释、空白并返回精简结果
    # shellcheck disable=SC2034
    out=$(perl -ne '
      # 处理注释或空行，退出 0
      if (/^\s*#/) { exit 0; }  # 整行注释退出
      s/\s+#.*//;               # 移除右侧注释
      s/^\s+|\s+$//g;           # 去除前后空格
      if (/^$/) { exit 0; }     # 空行退出
      
      # 函数定义检测
      if (/^\s*(\w+)\s*\(\)\s*\{?/) {
        if (/\}\s*$/) {
          exit 0; # 单行函数：跳过
        } else {
          print;
          exit 2; # 多行函数定义
        }
      }
      
      # heredoc 检查：包含 << 但不包含 <<<
      if (/<</ && !/<<</) {
        print;
        exit 3;  # heredoc 标记
      }

      if (/^{$/) { exit 4; } # 单个左括号
      if (/^}$/) { exit 5; } # 单个右括号
      
      print;
      exit 1; # 需进一步解析
    ' <<<"${lines[$idx]}")

    return $? # 返回 perl 命令的退出状态
  }

  # 处理heredoc
  check_heredoc_block() {
    local -n ln="line_number" # 设置引用，直接修改外部函数名
    local line="${lines[$ln]}"

    # 去除单双引号里的内容
    local stripped_line
    stripped_line="$(echo "$line" | sed -E 's/"([^"\\]|\\.)*"|'\''([^'\'']|\\.)*'\''//g')"

    if [[ "$stripped_line" =~ \<\<-?[[:space:]]*([_A-Za-z0-9]+) ]]; then
      local heredoc_end="${BASH_REMATCH[1]}"
      # 从下一行开始搜索 heredoc 结束
      while ((++ln <= total_lines)); do
        if [[ "${lines[ln]}" == "$heredoc_end" ]]; then
          return 0 # 返回true，表示遇到heredoc
        fi
      done
      return 0 # 返回true，表示遇到heredoc
    fi

    return 1 # 返回false，表示没有遇到heredoc
  }

  # 处理function首行
  get_function_name() {
    local line="$1"
    [[ "$line" =~ ^[[:space:]]*([a-zA-Z0-9_]+)[[:space:]]*\(\)[[:space:]]*\{? ]]
    echo "${BASH_REMATCH[1]}"
  }

  # 初始化大括号计数器
  init_brace_count() {
    local line="$1"
    [[ "$line" =~ \{$ ]] && echo 1 || echo 0
  }

  # 处理function内容
  parse_function() {
    local -n ln="line_number"                     # 设置引用，直接修改外部函数名
    local line="${lines[ln]}"                     # 当前行内容
    local func_name=$(get_function_name "$line")  # 函数名称
    local brace_count=$(init_brace_count "$line") # 大括号计数器

    # 处理内容行
    while ((++ln <= total_lines)); do
      parse_line_preprocess line "$ln"
      case $? in
        0) continue ;; # 注释、空行、单行函数：跳过
          # 1) ;;                # 待完善
        2) parse_function ;;                  # 递归算法：搜索嵌套子程序
        3) check_heredoc_block && continue ;; # 检测是否 heredoc 块，是的话跳过
        4) ((brace_count++)) ;;               # 出现左括号，计数器 + 1
        5)
          ((brace_count--))
          ((brace_count <= 0)) && return # 出现左括号，计数器 - 1，判断是否结束点
          ;;
      esac

      # 输出每个匹配项
      while IFS= read -r matched; do
        parse_match_type "$matched" "$sh_file" "$func_name" "$((ln + 1))"
      done <<<"$(split_match_type "$line")"

      # 处理跨行字符串（以反斜杠结尾的行）
      # 注意：这部分需要进一步实现以支持跨行字符串解析
    done
  }

  # ==============================================================================
  # 将结果保存在数组中 function name + 剩余部分（下一个function，或行尾）
  # lead = "([\s;{\(\[]|&&|\|\|)"
  # function = "string|exiterr|error|success|warning|info"
  # trail = "([\s;}\)\]]|&&|\|\||$)"
  #     空白字符 \s
  #     分号 ;
  #     命令块 {}
  #     命令 ()          <==> \( \)
  #     逻辑表达式 []     <==> \[ \]
  #     逻辑运算符 &&
  #     逻辑运算符 ||     <==> \|\|
  #     行尾 ($)
  # 输入：
  #  { info --order=1 -i "[1/1] 检查用户权限..."; info --order=2 "test order 2"; }
  # 输出：
  # info --order=1 -i "[1/1] 检查用户权限...";
  # info --order=2 "test order 2"; }
  # ==============================================================================
  split_match_type() {
    local line=" $1" # 左侧加一个空格，避免offset计算错误

    perl -e '
      sub trim_lead_symbol {
        my ($s) = @_;
        my $first2 = substr($s, 0, 2);
        return substr($s, 2) if $first2 eq "&&" or $first2 eq "||";
        my $first1 = substr($s, 0, 1);
        return substr($s, 1) if $first1 =~ /^[\s;{\(\[]$/;
        return $s;
      }

      my $function_pattern = qr/(string|exiterr|error|success|warning|info)/;
      my $pattern = qr{([\s;{\(\[]|&&|\|\|)($function_pattern)([\s;}\)\]]|&&|\|\||$)};

      my $line = shift;
      my $last = 0;

      while ($line =~ /$pattern/g) {
        my $match_start = $-[2]; # function keyword start (Current)
        if ($last > 0) {
          my $segment = substr($line, $last, $match_start - $last);
          $segment = trim_lead_symbol($segment); # remove prefix
          print "$segment\n";
        }
        $last = $match_start; # function keyword start (Previous)
      }

      if ($last > 0) {
        my $segment = substr($line, $last);
        $segment = trim_lead_symbol($segment);
        print "$segment";
      }
    ' -- "$line"
  }

  # ==============================================================================
  # 用途: 提取字符串中第一个未转义双引号之间的内容（忽略转义引号），
  #       并排除纯变量（如 "$var"）的情况。
  #
  # 参数:
  #   $1 - 输入字符串，通常是一行代码或命令调用
  #
  # 行为:
  #   - 跳过转义引号 \"，仅识别未转义的双引号成对包裹的内容
  #   - 若内容为一个变量（$abc_def），则跳过返回 1
  #   - 若只找到一个双引号，且原始行以 \ 结尾，则从第一个引号提取到行尾
  #
  # 返回:
  #   - 成功：输出提取的字符串内容
  #   - 失败：返回状态码 1，无输出
  # ==============================================================================
  extract_quoted_string() {
    perl -e '
      my $line = shift;

      if ($line =~ /"(.*)/) {
        my $content = $1;

        # 截断未转义的结束引号
        $content =~ s/^(.*?)(?<!\\)".*/$1/;

        # # 拒绝变量引用
        exit 1 if $content =~ /^\$[a-zA-Z_][a-zA-Z0-9_]*$/;

        print $content;
        exit ($content eq "") ? 1 : 0;
      } else {
        exit 1;
      }
    ' -- "$1"
  }

  # ==============================================================================
  # 解析脚本行中的函数调用信息，并将结果追加到 MSG_FUNC_CALLS 数组中
  # 参数：
  #   $1 - segment       当前处理的脚本文本段
  #   $2 - filename：    来源文件名
  #   $3 - function_name：所在函数名
  #   $4 - line_number： 当前行号
  # 要求：
  #   - 忽略含有 -i 参数的行（如 info -i "..."）
  #   - 提取命令名（如 info、exiterr）
  #   - 提取 --order=数字（如 --order=2），未指定则为 "-"
  #   - 提取第一个和第二个双引号之间的内容
  #     · 若只出现一个双引号且以 \ 结尾，视为包含至行尾
  # 输入：
  # info --order=1 -i "[1/1] 检查用户权限...";
  # info --order=2 "test order 2"; }
  # 输出：
  # bin/init_main.sh check_env 70 info 2 test order 2
  # ==============================================================================
  parse_match_type() {
    local segment="$1"
    local filename="$2"
    local function_name="$3"
    local line_number="$4"
    local -n ln="MSG_FUNC_CALLS" # 设置引用，直接修改外部函数名

    # 跳过：空行 | 含 -i 的行
    [[ -z $segment || "$segment" == *"-i"* ]] && return

    # 提取第一个字段
    local cmd="${segment%% *}"

    # 提取 --order=数字，没有就用 -
    local order="-"
    [[ "$segment" =~ --order=([0-9]+) ]] && order="${BASH_REMATCH[1]}"

    # 提取第一个和第二个双引号之间内容
    local content
    content=$(extract_quoted_string "$segment") || return

    MSG_FUNC_CALLS+=("$filename $function_name $cmd $line_number $order $content")
  }

  # ==============================================================================
  # 主解析函数：解析shell文件，遇到函数，则进入解析
  # 大括号的处理：只关心单行的大括号，或函数头的大括号（推荐用shfmt格式化代码后再试）
  #   function_name() {
  #     ...
  #   }
  # ==============================================================================
  parse_shell_file() {
    local sh_file="$1"
    declare -a lines
    local line=""
    mapfile -t lines <"$sh_file" # 按行读取内容

    local line_number=0
    local total_lines=${#lines[@]}
    for (( ; line_number < total_lines; line_number++)); do
      parse_line_preprocess line "$line_number" # 移除注释和前后空白
      case $? in
        # 0) continue ;; # 注释、空行、单行函数：跳过
        # 1) ;;                # 待完善
        2) parse_function ;; # 递归算法：搜索嵌套子程序
      esac
    done
  }

  # ==============================================================================
  # 主程序（用于测试）
  # 扫描目录中的所有shell脚本
  # 解析shell文件中的语言函数
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    main() {
      declare -a MSG_FUNC_CALLS # 结果数组 filename function_name line_number matched_type order

      [[ $# -eq 0 ]] && exiterr "用法: $0 <shell脚本或目录>"

      # 如果是目录，递归查找所有sh文件
      local dir="$1"
      if [[ -d "$dir" ]]; then
        find "$dir" -type f -name "*.sh" | while read -r file; do
          parse_shell_file "$file"
        done
      # 如果是单个文件
      elif [[ -f "$dir" ]]; then
        parse_shell_file "$dir"
      else
        error "'$dir' 不是有效的文件或目录"
      fi

      print_array MSG_FUNC_CALLS # 检查解析结果
    }

    main "$@"
  fi

fi
