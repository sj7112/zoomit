#!/bin/bash

# 确保只被加载一次
if [[ -z "$LOADED_CMD_HELP" ]]; then
  LOADED_CMD_HELP=1

  : "${BIN_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${LIB_DIR:=$(dirname "$BIN_DIR")/lib}"                     # lib directory
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/json_handler.sh"

  # ==============================================================================
  # 函数: parse_meta_json
  # 描述: 解析函数元数据JSON，提取短选项、长选项和帮助信息
  # 参数:
  #   $1 - 包含函数元数据的JSON字符串
  # 返回值:
  #   通过全局变量以备后用:
  #   - META_SHORT_OPTS - 短选项字符串
  #   - META_LONG_OPTS - 长选项数组
  #   - META_OPTIONS_MAP - 选项映射数组
  #   - META_HELP_MAP - 帮助信息映射数组
  # ==============================================================================
  parse_meta_json() {
    local meta_json="$1"

    # 初始化全局变量
    META_SHORT_OPTS=""
    META_LONG_OPTS=()
    declare -gA META_OPTIONS_MAP
    declare -gA META_HELP_MAP

    # 提取所有行
    local lines
    mapfile -t lines <<<"$meta_json"

    for line in "${lines[@]}"; do
      # 跳过空行和花括号
      if [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*[{}][[:space:]]*$ ]]; then
        continue
      fi

      # 移除开头的空格和可能的逗号
      line=$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/,$//')

      # 检查是否是短选项到长选项的映射
      if [[ "$line" =~ ^-([a-zA-Z])\ *=\ *--([a-zA-Z0-9_-]+) ]]; then
        local short_opt="${BASH_REMATCH[1]}"
        local long_opt="${BASH_REMATCH[2]}"

        # 添加到短选项字符串
        META_SHORT_OPTS+="$short_opt"
        # 添加到选项映射
        META_OPTIONS_MAP["$short_opt"]="$long_opt"
        META_OPTIONS_MAP["$long_opt"]="$long_opt"

        # 提取帮助信息
        if [[ "$line" =~ ^#\ *(.*) ]]; then
          local help_text="${BASH_REMATCH[1]}"
          META_HELP_MAP["$short_opt"]="$help_text"
          META_HELP_MAP["$long_opt"]="$help_text"
        fi

        # 检查长选项是否需要参数
        if [[ "$long_opt" =~ ^([a-zA-Z0-9_-]+):?$ ]]; then
          META_LONG_OPTS+=("$long_opt")
        fi
      # 检查是否是带参数的长选项
      elif [[ "$line" =~ ^--([a-zA-Z0-9_-]+)="(.*)" ]]; then
        local long_opt="${BASH_REMATCH[1]}"

        # 添加到长选项数组，带冒号表示需要参数
        META_LONG_OPTS+=("$long_opt:")
        META_OPTIONS_MAP["$long_opt"]="$long_opt"

        # 提取帮助信息
        if [[ "$line" =~ ^#\ *(.*) ]]; then
          local help_text="${BASH_REMATCH[1]}"
          META_HELP_MAP["$long_opt"]="$help_text"
        fi
      # 检查是否是独立的长选项
      elif [[ "$line" =~ ^--([a-zA-Z0-9_-]+) ]]; then
        local long_opt="${BASH_REMATCH[1]}"

        # 添加到长选项数组
        META_LONG_OPTS+=("$long_opt")
        META_OPTIONS_MAP["$long_opt"]="$long_opt"

        # 提取帮助信息
        if [[ "$line" =~ ^#\ *(.*) ]]; then
          local help_text="${BASH_REMATCH[1]}"
          META_HELP_MAP["$long_opt"]="$help_text"
        fi
      fi
    done
  }

  # ==============================================================================
  # 函数: parse_arguments
  # 描述: 使用getopt和函数元数据解析命令行参数
  # 参数:
  #   $1 - 函数元数据JSON
  #   $@ - 从第二个参数开始，传递给脚本的所有命令行参数
  # 返回值:
  #   通过全局变量设置解析结果:
  #   - ARGS_OPTIONS - 包含所有选项的关联数组
  #   - ARGS_PARAMS - 包含所有普通参数的数组
  #   - ARGS_JSON - JSON格式的解析结果(用于需要JSON的情况)
  # ==============================================================================
  parse_arguments() {
    local meta_json="$1"
    shift

    # 解析元数据
    parse_meta_json "$meta_json"

    # 初始化全局变量
    declare -gA ARGS_OPTIONS
    declare -ga ARGS_PARAMS
    ARGS_PARAMS=()

    # 准备getopt选项
    local short_opts="$META_SHORT_OPTS"
    local long_opts_str=""

    for opt in "${META_LONG_OPTS[@]}"; do
      if [ -n "$long_opts_str" ]; then
        long_opts_str+=","
      fi
      long_opts_str+="$opt"
    done

    # 使用getopt解析参数
    local args
    args=$(getopt -o "$short_opts" -l "$long_opts_str" -n "$0" -- "$@" 2>/dev/null)

    if [ $? -ne 0 ]; then
      echo "参数解析失败，请检查您的命令语法" >&2
      return 1
    fi

    eval set -- "$args"

    # 初始化结果JSON
    local options_json='"options":{'
    local params_json='"params":['
    local has_options=false
    local has_params=false

    # 处理解析后的参数
    while true; do
      if [ "$1" = "--" ]; then
        shift
        break
      fi

      local opt_name="${1#-}"
      opt_name="${opt_name#-}"
      local mapped_name="${META_OPTIONS_MAP[$opt_name]}"

      if [ -z "$mapped_name" ]; then
        mapped_name="$opt_name"
      fi

      if [ "$has_options" = true ]; then
        options_json+=','
      fi
      has_options=true

      # 检查是否是需要值的选项
      if [[ " ${META_LONG_OPTS[*]} " == *" $mapped_name: "* ]] || [[ "$short_opts" == *"$opt_name:"* ]]; then
        shift
        ARGS_OPTIONS["$mapped_name"]="$1"
        options_json+="\"$mapped_name\":\"$1\""
      else
        ARGS_OPTIONS["$mapped_name"]="true"
        options_json+="\"$mapped_name\":true"
      fi

      shift
    done

    # 处理剩余的普通参数
    while [ $# -gt 0 ]; do
      ARGS_PARAMS+=("$1")

      if [ "$has_params" = true ]; then
        params_json+=','
      fi
      has_params=true
      params_json+="\"$1\""
      shift
    done

    # 完成JSON构建
    options_json+='}'
    params_json+=']'
    ARGS_JSON='{'
    ARGS_JSON+="$options_json,"
    ARGS_JSON+="\"param_count\":${#ARGS_PARAMS[@]},"
    ARGS_JSON+="$params_json"
    ARGS_JSON+='}'

    return 0
  }

  # ==============================================================================
  # 函数: show_help_info
  # 描述: 根据函数元数据（META_Command）显示帮助信息
  # 参数:
  #   $1 - 命令名称
  # ==============================================================================
  show_help_info() {
    local cmd=$1
    [[ -z "$cmd" ]] && exiterr "Usage: show_help_info [command]\n \
        Available commands: find, ls"

    # 使用jq解析JSON
    local command_info=$(jq -e ".${cmd}" <<<"$META_Command" 2>/dev/null)
    [[ -z "$command_info" ]] && exiterr "Error: Command '$cmd' not found."

    # 提取命令信息
    name=$(jq -r '.name' <<<"$command_info")

    echo "名称: $name"
    echo "用法: $cmd [选项...]"
    echo ""
    echo "选项:"

    # 提取所有选项并格式化
    jq -r '
  .options[] |
  [
    (if .key != "" then .key + ", " else "    " end) + .long,
    .desc
  ] | @tsv' <<<"$command_info" | while IFS=$'\t' read -r opt desc; do
      # 输出第一行（选项 + 第一行描述）
      printf "  %-24s%s\n" "$opt" "${desc%%$'\n'*}"
      # 如果描述中有多行，继续按行输出
      if [[ "$desc" == *$'\n'* ]]; then
        while IFS= read -r line; do
          printf "%24s%s\n" "" "$line"
        done <<<"${desc#*$'\n'}"
      fi
    done
  }

  # ==============================================================================
  # 函数: run_command
  # 描述: 执行自定义命令，处理参数解析和传递
  # 参数:
  #   $1 - 命令名称（不含my_前缀）
  #   $2... - 命令的所有参数
  # ==============================================================================
  run_command() {
    local cmd_name="$1"
    shift

    # 检查命令函数是否存在
    type "cmd_${cmd_name}" &>/dev/null || exiterr "未找到命令 '$cmd_name'"
    # 检查元数据是否存在
    local meta_var="META_${cmd_name}"
    declare -p "$meta_var" &>/dev/null || exiterr "未找到命令 '$cmd_name' 的元数据"

    # 获取元数据、解析参数
    local meta_json="${!meta_var}"
    parse_arguments "$meta_json" "$@"
    echo ${ARGS_OPTIONS["-l"]}
    # 检查是否需要显示帮助
    if [[ "${ARGS_OPTIONS["help"]}" == "true" ]]; then
      show_help "$meta_json" "my_$cmd_name"
      return 0
    fi

    # 执行命令函数
    "cmd_${cmd_name}"

    return $?
  }

  #============================
  # 自定义命令示例
  #============================

  # 元数据: my_ls 命令
  META_ls='{
-l = --long # 使用长列表格式
-t = --time # 按修改时间排序
-r = --reverse # 逆序排列
-h = --human # 人类可读的文件大小
--help # 显示此帮助信息
}'

  # 函数: cmd_ls
  # 描述: 自定义ls命令实现
  cmd_ls() {
    local ls_args=""

    # 处理选项
    [[ "${ARGS_OPTIONS["long"]}" == "true" ]] && ls_args+="l"
    [[ "${ARGS_OPTIONS["time"]}" == "true" ]] && ls_args+="t"
    [[ "${ARGS_OPTIONS["reverse"]}" == "true" ]] && ls_args+="r"
    [[ "${ARGS_OPTIONS["human"]}" == "true" ]] && ls_args+="h"

    # 构建ls命令
    local cmd="ls"
    [[ -n "$ls_args" ]] && cmd="ls -$ls_args"

    # 处理目录参数
    if [[ ${#ARGS_PARAMS[@]} -eq 0 ]]; then
      # 无参数，列出当前目录
      $cmd
    else
      # 对每个目录参数执行ls命令
      for dir in "${ARGS_PARAMS[@]}"; do
        echo "=== $dir ==="
        $cmd "$dir"
        echo ""
      done
    fi
  }

  # 元数据: my_find 命令

  # 元数据: my_find 命令

  # 函数: cmd_find
  # 描述: 自定义find命令实现
  cmd_find() {
    local find_args=""

    # 检查是否有指定目录
    if [[ ${#ARGS_PARAMS[@]} -eq 0 ]]; then
      echo "错误: 请指定要查找的目录" >&2
      return 1
    fi

    # 目录是第一个参数
    local search_dir="${ARGS_PARAMS[0]}"

    # 构建find命令
    local cmd="find $search_dir"

    # 处理选项
    if [[ -n "${ARGS_OPTIONS["name"]}" ]]; then
      cmd+=" -name \"${ARGS_OPTIONS["name"]}\""
    fi

    if [[ -n "${ARGS_OPTIONS["type"]}" ]]; then
      cmd+=" -type ${ARGS_OPTIONS["type"]}"
    fi

    if [[ -n "${ARGS_OPTIONS["maxdepth"]}" ]]; then
      cmd+=" -maxdepth ${ARGS_OPTIONS["maxdepth"]}"
    fi

    # 执行find命令
    eval "$cmd"
  }

  # ==============================================================================
  # 主程序（用于测试）
  # 解析命令和参数并执行
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main() {
      local cmd_names=$(json_get_keys "$META_Command" ", ")
      # 检查命令参数
      if [[ $# -eq 0 ]]; then
        echo "错误: 请指定要执行的命令" >&2
        echo "可用命令: $cmd_names" >&2
        return 1
      fi

      # 获取命令名称
      local cmd_name="$1"
      shift
      show_help_info "$cmd_name"
      # 执行命令
      run_command "$cmd_name" "$@"
      return $?
    }

    main "$@"
  fi

fi
