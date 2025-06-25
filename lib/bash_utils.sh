#!/bin/bash

# Load once only
if [[ -z "${LOADED_BASH_UTILS:-}" ]]; then
  LOADED_BASH_UTILS=1

  # 生成时间戳
  timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
  }

  # 记录日志1
  log_info() {
    echo "$(timestamp) [INFO] $1"
  }

  # 记录错误
  log_error() {
    echo "$(timestamp) [ERROR] $1" >&2
  }

  # ==============================================================================
  # check_root_path - 检测路径（需root权限）是否存在
  # ==============================================================================
  check_root_path() {
    $SUDO_CMD test -f "$1"
  }
  # ==============================================================================
  # Confirmation function with callback
  # Parameters:
  #   $1: prompt message
  #   $2+: callback function name and its arguments
  # Optional parameters:
  #   msg="text": custom cancel message (default: "operation is cancelled")
  #   def="y|n": default value for empty input (default: "y")
  # Returns:
  #   callback function's return value, or 2 when cancelled
  # ==============================================================================
  confirm_action() {
    local prompt="$1"
    shift

    # Parse optional parameters
    local cancel_msg
    local def_val="y" # Default: empty input means Yes
    local args=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        msg=*)
          cancel_msg="${1#msg=}"
          ;;
        def=*)
          def_val="${1#def=}"
          ;;
        *)
          args+=("$1")
          ;;
      esac
      shift
    done

    # Set default cancel message
    if [[ -z "$cancel_msg" ]]; then
      cancel_msg=$(string "operation is cancelled")
    fi

    # Determine default behavior based on def_val parameter
    local default_prompt="[Y/n]"
    if [[ "$def_val" =~ ^[Nn]$ ]]; then
      # If def_val=n, empty input means No
      default_prompt="[y/N]"
    fi

    # User Exit on Ctrl+C
    do_keyboard_interrupt() {
      echo ""
      exiterr "User interrupted the operation, exiting the program"
    }

    trap do_keyboard_interrupt INT # Exit directly on Ctrl+C

    while true; do
      read -p "$prompt $default_prompt " response
      if [[ -z "$response" || "$response" =~ ^[YyNn]$ ]]; then
        break
      else
        error "Please enter 'y' for yes, 'n' for no, or press Enter for default"
      fi
    done

    trap - INT # Remove SIGINT signal handler

    local ret_code=0 # user enter Y or y
    if [[ -z "$response" && "$def_val" =~ ^[Nn]$ ]]; then
      ret_code=1
    elif [[ "$response" =~ ^[Nn]$ ]]; then
      ret_code=1
    fi

    if [[ "$ret_code" -eq 0 ]]; then
      "${args[@]}" # 👈 callback=$1, args=other parameter
      return $?    # Return callback's exit code
    else
      warning "$cancel_msg"
      return $ret_code
    fi
  }

  # ==============================================================================
  # 函数: fl_check_exist
  # 检查文件是否存在，并返回文件路径（如果存在），否则返回错误
  # ==============================================================================
  fl_check_exist() {
    local file="$1"
    if [ ! -f "$file" ]; then
      echo "错误: 文件 '$file' 不存在" >&2
      return 1 # 返回 1 表示文件不存在
    fi
    echo "$file" # 返回文件路径
  }

  # ==============================================================================
  # 函数: fl_toggle_comments
  # 作用: 改配置文件内容（加/去注释）
  # 参数：
  # 1. 配置文件路径
  # 2. 可选参数：
  #    -c: 找到匹配行并加注释（将行首加上 #）
  #    -e: 找到已注释的行并去除注释（去掉行首的 #）
  # 3. 一对或多对参数（每对包含：关键词）
  #
  # 示例: 修改参数（单个/多个）
  #   多个: modify_config "/etc/ssh/sshd_config" "LANG=C" "LANGUAGE=C"
  # ==============================================================================
  fl_toggle_comments() {
    local file mode key
    mode=$(parse_options "ae" "a") # 解析选项，默认 -a
    shift $((OPTIND - 1))          # 移除选项参数，剩下的是关键词

    # 偏移已解析的选项，获取文件路径
    shift $((OPTIND - 1))
    file="$1"
    shift # 剩余的是成对的关键词

    # 检查文件是否存在
    if [ ! -f "$file" ]; then
      echo "错误: 文件 $file 不存在" >&2
      return 1
    fi

    # 遍历剩余的参数，按对处理
    while [ $# -gt 0 ]; do
      key="$1"
      shift # 移动到下一个关键词

      # 如果文件中包含关键词，则执行加/去注释操作
      if grep -q "$key" "$file"; then
        if [ "$mode" == "-c" ]; then
          # 在行首加上 #（注释）
          $SUDO_CMD sed -i "s/^$key/#$key/" "$file" || return 1
        elif [ "$mode" == "-e" ]; then
          # 去掉行首的 #（去注释）
          $SUDO_CMD sed -i "s/^#$key/$key/" "$file" || return 1
        fi
      fi
    done

    return 0
  }

  # ==============================================================================
  # 函数: fl_modify_line
  # 作用: 修改配置文件内容（找到参数，则替换整行！找不到参数，在文件末尾添加！）
  # 参数：
  # 1. 配置文件路径
  # 2. 一对或多对参数（每对包含：关键词、新内容）
  #
  # 示例: 修改参数（单个/多个）
  #   单个: fl_modify_line "/etc/ssh/sshd_config" "PermitRootLogin" "PermitRootLogin yes"
  #   多个: fl_modify_line "/etc/ssh/sshd_config" "LANG=C" "#LANG=C" "LANGUAGE=C" "#LANGUAGE=C"
  # ==============================================================================
  fl_modify_line() {
    local file="$1" # 第一个参数是文件路径
    shift           # 移除文件路径参数，剩余的是成对的 key/new_content

    # 检查文件是否存在
    if [ ! -f "$file" ]; then
      echo "错误: 文件 $file 不存在" >&2
      return 1
    fi

    # 遍历剩余的参数，按对处理
    while [ $# -gt 0 ]; do
      key="$1"
      new_content="$2"
      shift 2 # 移动到下一对参数

      # 如果文件中包含关键词，则替换整行
      if grep -q "$key" "$file"; then
        # 找到匹配行，替换整行
        $SUDO_CMD sed -i "s/^.*$key.*$/$new_content/" "$file" || return 1
      else
        # 没有找到匹配行，添加到文件末尾
        echo "$new_content" >>"$file" || return 1
      fi
    done

    return 0
  }

  # ==============================================================================
  # 函数: file_backup_sj
  # 作用: 生成 .bak 后缀的备份文件（智能防重复备份）
  #
  # 特性：
  #   1. 支持通配符匹配和多文件备份（如 *.conf）
  #   2. 自动检查源文件是否存在
  #   3. 自动跳过已存在的备份文件
  #   4. 保留原文件权限（通过 sudo 执行）
  #
  # 参数：
  #   [必选] src_file - 需要备份的源文件路径（支持通配符）
  #
  # 异常：
  #   有文件备份失败则退出shell命令
  #
  # 示例:
  #   file_backup_sj "/etc/apt/sources.list"          # 备份单个文件
  #   file_backup_sj "/etc/nginx/*.conf"              # 备份所有匹配文件
  #   file_backup_sj "/etc/*.conf" "/etc/*.repo"      # 批量备份多类文件
  # ==============================================================================
  file_backup_sj() {
    # 参数检查
    if [ $# -eq 0 ]; then
      exiterr "未指定需要备份的文件"
    fi

    local backup_count=0
    local skip_count=0
    local error_count=0

    # 处理每个参数（可能包含通配符）
    for pattern in "$@"; do
      # 检查是否存在匹配的文件
      if ! compgen -G "$pattern" >/dev/null; then
        warning "警告：未找到匹配 '$pattern' 的文件"
        continue
      fi

      # 处理每个匹配的文件
      for src_file in $pattern; do
        [ ! -f "$src_file" ] && continue # 确保是普通文件

        local backup_file="${src_file}.bak"

        # 检查备份文件是否已存在
        if check_root_path "$backup_file"; then
          warning "备份文件 $backup_file 已存在，跳过"
          ((skip_count = skip_count + 1))
          continue
        fi

        # 执行备份
        if $SUDO_CMD cp "$src_file" "$backup_file"; then
          info "已创建备份: $src_file -> $backup_file"
          ((backup_count = backup_count + 1))
        else
          error "错误：无法创建备份文件 $backup_file"
          ((error_count = error_count + 1))
        fi
      done
    done

    # 输出统计信息
    if [ $error_count -gt 0 ]; then
      exiterr "重要文件无法备份"
    elif [ $(expr $backup_count + $skip_count + $error_count) -gt 1 ]; then
      info "备份完成：成功 $backup_count 个，跳过 $skip_count 个，失败 $error_count 个"
    fi
  }

fi
