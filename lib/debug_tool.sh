#!/bin/bash

# Load once only
if [[ -z "${LOADED_DEBUGTOOL:-}" ]]; then
  LOADED_DEBUGTOOL=1

  # 判断字符串是否包含在数组中
  string_array_contain() {
    declare -n array=$1 # 引用传递
    local str="$2"      # 使用第二个参数（目标字符串）

    for element in "${array[@]}"; do
      if [[ "$element" == "$str" ]]; then
        return 0 # 找到匹配的元素，返回 0
      fi
    done

    return 1 # 未找到匹配，返回 1
  }

  # 测试程序：提取函数中的局部变量名
  extract_local_variables() {
    local func_name="${FUNCNAME[1]}" # 获取父函数的名称

    # 获取父函数的源代码并提取local声明的变量
    declare -f "$func_name" | grep -oP 'local\s+\K\w+' # 使用正则表达式提取局部变量名
  }

  # 测试程序：打印父函数所有参数一览表
  list_vars() {
    local local_output="$1"   # 本地变量清单
    local declare_output="$2" # declare -p 的输出

    local global_output_vars=(
      "COLUMNS" "COMP_WORDBREAKS" "DIRSTACK" "EPOCHREALTIME" "EPOCHSECONDS" "EUID" "FUNCNAME" "GROUPS" "HISTCMD" "HOSTNAME"
      "HOSTTYPE" "IFS" "LINENO" "LINES" "MACHTYPE" "OPTERR" "OPTIND" "OSTYPE" "PIPESTATUS" "PPID"
      "PS4" "RANDOM" "SECONDS" "SHELLOPTS" "SRANDOM" "UID" "_" "choice" "cmd" "key"
      "line" "long")
    local local_output_vars=()
    local bash_vars=()
    local env_vars=()
    local global_vars=()
    local user_vars=()
    local local_vars=()

    # 获取并循环 compgen -v 的结果，存储所有全局变量
    while IFS= read -r var; do
      local_output_vars+=("$var")
    done <<<"$local_output"

    # 循环读取每一行并分类存储
    while IFS= read -r line; do
      if [[ "$line" =~ ^declare\ -x ]]; then # 使用 -x 标记环境变量
        env_vars+=("$line")                  # 存储环境变量
      elif [[ "$line" =~ ^declare\ -([^\ ]+)\ BASH.* ]]; then
        bash_vars+=("$line") # 存储 Bash 内建变量
      else
        local var_name=$(echo "$line" | sed 's/=.*//' | awk '{print $NF}')
        if string_array_contain global_output_vars "$var_name"; then
          global_vars+=("$line") # 如果不在 all_vars 中，认为是局部变量
        elif string_array_contain local_output_vars "$var_name"; then
          local_vars+=("$line") # 如果不在 all_vars 中，认为是局部变量
        else
          user_vars+=("$line") # 存储用户自定义全局变量
        fi
      fi
    done <<<"$declare_output"

    # 输出环境变量
    if [ ${#env_vars[@]} -gt 0 ]; then
      echo -e "\n==== 🌱 环境变量 ===="
      printf "%s\n" "${env_vars[@]}" | grep -Ev '^declare -- (FUNCNAME|LINENO)'
    fi

    # 输出 Bash 内建变量
    if [ ${#bash_vars[@]} -gt 0 ]; then
      echo -e "\n==== 🧵 Bash 内建变量 ===="
      printf "%s\n" "${bash_vars[@]}"
    fi

    # 输出用户自定义的全局变量
    if [ ${#global_vars[@]} -gt 0 ]; then
      echo -e "\n==== 🌏 Bash 内置特殊变量 ===="
      printf "%s\n" "${global_vars[@]}"
    fi

    # 输出用户自定义的全局变量
    if [ ${#user_vars[@]} -gt 0 ]; then
      echo -e "\n==== 📦 用户自定义全局变量 ===="
      printf "%s\n" "${user_vars[@]}"
    fi

    echo -e "\n===== 🧪 Shell 参数信息 ====="

    # 根据父函数的所有参数，统一用 ${i} 格式
    echo "\$0 (脚本名称): $0"
    local arg_val
    for i in $(seq 3 $#); do
      arg_val=$(eval echo \${$i})
      echo "\$$((i - 2)): $arg_val"
    done

    echo "\$# (参数个数): $(($# - 2))" # 扣除前两个参数
    echo "\$$ (当前进程ID): $$"        # 和父函数一致
    echo "\$! (最后后台进程ID): $!"      # 和父函数一致
    echo "\$? (最后命令退出状态): $?"      # 和父函数一致
    echo "\$- (当前选项标志): $-"        # 和父函数一致

    # 输出并排序局部变量
    if [ ${#local_vars[@]} -gt 0 ]; then
      echo -e "\n==== 🧪 函数内局部变量（按字母顺序） ===="
      printf "%s\n" "${local_vars[@]}" | sort
    fi
    echo "========================="
  }

  # 打印参数
  print_args() {
    for arg in "$@"; do
      echo " - $arg" >&2
    done
  }

  # 打印数组
  # print_array() {
  #   local -n arr=$1 # 引用传递数组参数
  #   for key in "${!arr[@]}"; do
  #     echo "$key: ${arr[$key]}" >&2
  #   done
  # }
  # 打印数组（兼容 Bash 4.2）
  print_array() {
    local arr_name="$1"
    local -a keys
    local -a values

    eval "keys=(\"\${!${arr_name}[@]}\")"  # 获取所有键
    eval "values=(\"\${${arr_name}[@]}\")" # 获取所有值

    for i in "${!keys[@]}"; do
      echo "${keys[$i]}: ${values[$i]}" >&2
    done
  }

  # write_array() {
  #   local array_name="$1" # 数组名
  #   local filename="$2"   # 文件名

  #   # 使用 nameref 方式引用传入的数组名（需要 Bash 4.3+）
  #   local -n arr="$array_name"

  #   # 创建或清空目标文件
  #   : >"$filename" || return 1

  #   # 遍历数组并写入文件
  #   for item in "${arr[@]}"; do
  #     printf '%s\n' "$item" >>"$filename"
  #   done
  # }
  # 打印数组到文件（兼容 Bash 4.2）
  write_array() {
    local array_name="$1"
    local filename="$2"

    : >"$filename" || return 1

    local -a values
    eval "values=(\"\${${array_name}[@]}\")" # 先复制数组到本地变量

    for item in "${values[@]}"; do
      printf '%s\n' "$item" >>"$filename"
    done
  }

  # 打印json对象
  print_json() {
    local -n arr=$1 # 引用传递数组参数
    for key in "${!arr[@]}"; do
      echo "$key: ${arr[$key]}" >&2
    done
  }

  # 打印完整调用链
  print_full_stack() {
    # echo "<===="
    local i
    local depth=${#FUNCNAME[@]} # 总层级数
    for ((i = 0; i < depth; i++)); do
      echo "Function: ${FUNCNAME[$i]}"
      echo "  File: ${BASH_SOURCE[$i]}"
      echo "  Line: ${BASH_LINENO[$i - 1]}"
      echo "  Parent: ${FUNCNAME[$i + 1]-}" # 父函数（可能不存在）
      echo "---"
    done
    # echo "====>"
  }

  # ==============================================================================
  # 断言测试并彩色输出结果函数
  # 用法: test_assertion "条件表达式" "结果消息"
  # ==============================================================================
  test_assertion() {
    local assertion="$1"
    local message="$2"

    # 绿色和红色的 ANSI 转义码
    local GREEN='\033[0;32m'
    local RED='\033[0;31m'
    local NC='\033[0m' # No Color

    # 执行条件判断
    if eval "$assertion"; then
      echo -e "${GREEN}true${NC} ====> $message"
      return 0
    else
      echo -e "${RED}false${NC} ====> $message"
      return 1
    fi
  }

  # ==============================================================================
  # 测速函数
  # 用法: time_function 原函数 原函数参数
  # ==============================================================================
  time_function() {
    local func_name="$1"
    shift

    # 颜色设置
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    GREEN='\033[0;32m'
    local NC='\033[0m'

    # 构建函数命令
    local cmd="$func_name"
    for arg in "$@"; do
      cmd="$cmd $(printf %q "$arg")"
    done

    # 起始时间
    local start_time=$(date +%s.%N)

    eval "$cmd"
    local status=$?

    # 结束时间
    local end_time=$(date +%s.%N)

    # 拆分秒和纳秒
    local start_seconds=${start_time%.*}
    local start_nanoseconds=${start_time#*.}
    local end_seconds=${end_time%.*}
    local end_nanoseconds=${end_time#*.}

    local seconds_diff=$((end_seconds - start_seconds))
    local nanoseconds_diff=$((10#$end_nanoseconds - 10#$start_nanoseconds))
    if [ $nanoseconds_diff -lt 0 ]; then
      seconds_diff=$((seconds_diff - 1))
      nanoseconds_diff=$((nanoseconds_diff + 1000000000))
    fi

    # 计算毫秒
    local milliseconds=$((nanoseconds_diff / 1000000))

    # 颜色判断
    local color=$GREEN
    if [ $seconds_diff -ge 10 ]; then
      color=$RED
    elif [ $seconds_diff -ge 2 ]; then
      color=$YELLOW
    fi

    # 打印毫秒精度时间（仅在耗时 > 0 时打印）
    if [ $seconds_diff -ne 0 ] || [ $milliseconds -ne 0 ]; then
      printf "${color}函数 %s 执行时间: %d.%03d秒${NC}\n" "$func_name" $seconds_diff $milliseconds >&2
    fi

    return $status
  }

fi
