#!/bin/bash

# Load once only
if [[ -z "${LOADED_I18N:-}" ]]; then
  LOADED_I18N=1

  # Declare global
  : "${BIN_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${LIB_DIR:=$(dirname "$BIN_DIR")/lib}"                     # lib directory
  : "${CONF_DIR:=$(dirname "$BIN_DIR")/config}"                 # config directory
  LANG_DIR="$CONF_DIR/lang"                                     # lang dierctory
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/json_handler.sh"
  source "$LIB_DIR/system.sh"
  source "$LIB_DIR/hash_util.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/python_bridge.sh"

  : "${SYSTEM_LANG:=$(get_locale_code)}" # 默认语言
  CURRENT_FUNCTION=""
  CURRENT_FILE=""
  OVERWRITE_ALL=0             # 是否全部覆盖（-y参数）
  declare -A MESSAGE_COUNTERS # 用于跟踪消息计数

  # ==============================================================================
  # load_lang_files 载入语言文件列表
  # 结果：创建全局关联数组 LANG_FILES，key 是语言名，value 是完整路径
  # ==============================================================================
  load_lang_files() {
    declare -gA LANG_FILES # 创建全局关联数组

    info "查找可用语言..."
    local count=0
    for lang_file in "$LANG_DIR"/*.properties; do
      echo "$count" "$lang_file"
      ((count = count + 1))
      if [[ -f "$lang_file" ]]; then
        local lang_name
        lang_name=$(basename "$lang_file" .properties)
        LANG_FILES["$lang_name"]="$lang_file"
        info "找到语言: $lang_name ($lang_file)"
      fi
    done
  }

  # ==============================================================================
  # 找到多个语言文件路径，并进行存在性检查。
  # 参数：
  #   $1: lang_file   - 父函数中变量名（用于接收 lang_code 路径）
  #   $2: lang_code   - 语言代码（如 zh_CN）
  #   $3: mode        - 报错条件（-：文件不存在报错；+：文件存在报错；e:报错；w:警告；i:提示）
  #                    - "0-e": 一个文件都不存在
  #                    - "1-e": 至少一个文件不存在
  #                    - "1+e": 至少一个文件存在
  #                    - "2+e": 所有文件都存在
  # ==============================================================================
  resolve_lang_files() {
    local -n _lf="$1" # 引用父函数的 lang_file
    local lang_code="$2"
    local mode="$3"
    local max="${4:-1}" # 默认为一个文件（多文件用{lang_code}_x.properties表示（x从2开始）

    # 生成文件路径列表
    _lf[0]="${LANG_DIR}/${lang_code}.properties" # 第一个文件没有数字后缀
    for ((i = 1; i < max; i++)); do
      _lf[$i]="${LANG_DIR}/${lang_code}_$((i + 1)).properties"
    done

    local mode_err=$(_mf "模式参数错误 {0}" "$mode")
    # shellcheck disable=SC2034
    local exist=$(_mf "{0} 语言文件已存在" "$lang_code")
    local notexist
    # shellcheck disable=SC2034
    notexist=$(_mf "{0} 语言文件不存在" "$lang_code")

    [ -z "$mode" ] && return 0

    # 判断调用函数
    local func
    case "$mode" in
      *e) func='exiterr' ;;
      *w) func='warning -e' ;;
      *i) func='info -e' ;;
      *) exiterr "$mode_err" ;;
    esac

    # 检查文件存在性
    local any_exists=false
    local all_exist=true

    for file in "${_lf[@]}"; do
      if [[ -f "$file" ]]; then
        any_exists=true
      else
        all_exist=false
      fi
    done

    # eval调用函数
    case "$mode" in
      0-*) $any_exists || eval "$func \"\$notexist\"" ;; # 一个文件都不存在
      1-*) $all_exist || eval "$func \"\$notexist\"" ;;  # 至少一个文件不存在
      1+*) $any_exists && eval "$func \"\$exist\"" ;;    # 至少一个文件存在
      2+*) $all_exist && eval "$func \"\$exist\"" ;;     # 所有文件都存在
      *) exiterr "$mode_err" ;;
    esac
  }

  # ==============================================================================
  # 解析语言文件，提取语言代码并存入数组
  # 参数：
  #   $1 - 引用返回数组lang_codes
  # ==============================================================================
  resolve_lang_codes() {
    local -n _lc="$1"

    local file
    for file in "${LANG_DIR}"/.*.properties; do
      [[ "$file" =~ /\.([a-zA-Z_]+)\.properties$ ]] && _lc+=("${BASH_REMATCH[1]}")
    done
  }

  # ==============================================================================
  #  添加语言文件
  # ==============================================================================
  add_lang_files() {
    local lang_code="$1"
    local lang_file=()
    # 获取所有文件路径
    resolve_lang_files lang_file "$lang_code" "1+w"

    # 标准模板内容
    local template="$(_mf "# {0} 语言包，文档结构：\n\
# 1. 自动处理 bin | lib 目录 sh 文件\n\
# 2. 解析函数 exiterr | error | success | warning | info | string | _mf\n\
# 3. key=distinct hash code + position + order\n\
# 4. value=localized string" "${lang_code}")"

    # 遍历所有文件路径创建文件
    for file in "${lang_file[@]}"; do
      if [[ ! -f "$file" ]]; then
        echo -e "$template" >"$file"
        info "{0} 语言文件已创建" "$file"
      fi
    done
  }

  # ==============================================================================
  #  删除语言文件
  # ==============================================================================
  del_lang_files() {
    local lang_code="$1"
    local lang_file=()
    # 获取所有文件路径
    resolve_lang_files lang_file "$lang_code" "0-e"

    # 嵌套删除文件子程序
    do_del_lang_files() {
      local delstr=$(_mf "{0} 语言文件已删除" "$lang_code")
      rm -f "${lang_file[@]}"
      info -i "$delstr" # ignore translation
    }

    # 如果指定了 noPrompt 为 yes，则直接删除文件
    if [[ "$2" == 1 ]]; then
      do_del_lang_files
      return 0
    fi

    # 文件存在，提示用户是否删除
    local prompt=$(_mf "确定要删除 {0} 语言文件吗?" "$lang_code")
    confirm_action "$prompt" do_del_lang_files msg="$(_mf "操作已取消，文件未删除")" # 👈 msg="cancel_msg"
  }

  # ==============================================================================
  #  处理语言文件
  # ==============================================================================
  get_lang_files() {
    local lang_code=$1
    local lang_file=()

    if [[ -n "$lang_code" ]]; then
      lang_codes+=("$lang_code")
    else
      resolve_lang_codes lang_codes
    fi

    for i in "${!lang_codes[@]}"; do
      lang_code="${lang_codes[i]}"

      # 指定语言代码，添加对应文件
      if ! resolve_lang_files lang_file "$lang_code" "1-w"; then
        local prompt=$(_mf "确定要新增 {0} 语言文件吗?" $lang_code)
        confirm_action "$prompt" add_lang_files "$lang_code" # 提示用户是否新增文件

        if [[ $? -eq 2 ]]; then
          unset 'lang_codes[i]' # 如果用户返回 2，则从数组中删除当前 lang_code
          continue
        fi
      fi
      lang_files+=("${lang_file[@]}")
    done

    # 重建数组索引（去掉 unset 留下的空位）
    lang_codes=("${lang_codes[@]}")
    [[ ${#lang_files[@]} -eq 0 ]] && exiterr "请先添加语言文件"
  }

  # ==============================================================================
  #  获取shell文件列表
  # ==============================================================================
  get_shell_files() {
    # 处理 shell 脚本文件
    if [[ $# -gt 0 ]]; then
      # 如果指定了文件名，检查文件是否存在并添加
      for file in "$@"; do
        if [[ -f "$file" ]]; then
          sh_files+=("$file")
        else
          warning "警告: 脚本文件 '{0}' 不存在" "$file"
        fi
      done
    else
      # 如果没有指定文件名，查找所有 bin 和 lib 目录下的 .sh 文件
      while IFS= read -r file; do
        sh_files+=("$file")
      done < <(find "bin" "lib" -type f -name "*.sh" 2>/dev/null)
    fi

    [[ ${#sh_files[@]} -eq 0 ]] && exiterr "没有找到任何 shell 脚本文件"
  }

  # ==============================================================================
  # 修改语言文件
  # ==============================================================================
  upd_lang_files() {
    local options="$1"
    shift # 剩余参数为可选的文件名列表
    local lang_files=()
    local sh_files=()
    # declare -a MSG_FUNC_CALLS # 结果数组 filename function_name line_number matched_type order

    # 处理语言文件
    get_lang_files $(json get options "lang")

    # 处理 shell 脚本文件
    get_shell_files "$@"

    mapfile -t MSG_FUNC_CALLS < <(parse_code_files)

    hash_init_msg MSG_FUNC_CALLS # 计算每个函数调用的hash值

    # 对每个 shell 脚本调用子程序
    info "开始更新语言文件"
    # for sh_file in "${sh_files[@]}"; do
    #   echo "处理脚本: $sh_file"

    #   mapfile -t MSG_FUNC_CALLS < <(parse_code_files "$sh_file")
    #   # print_array MSG_FUNC_CALLS2 # 检查解析结果
    #   # parse_shell_file "$sh_file" # 解析shell文件中的函数
    #   # print_array MSG_FUNC_CALLS  # 检查解析结果
    #   hash_init_msg MSG_FUNC_CALLS # 计算每个函数调用的hash值
    #   echo "# $sh_file"
    #   print_array _LANG_PROPS
    #   echo "3===>"
    #   print_array LANG_PROPS
    #   echo "4===>"
    #   # 处理每个语言文件
    #   for lang_file in "${lang_files[@]}"; do
    #     echo "Processing language file: $lang_file"

    #   done
    # done
    print_array MSG_FUNC_CALLS # 检查解析结果
    info "语言文件更新完成"
    return 0
  }

  # 初始化翻译系统
  init_i18n() {
    # 创建语言目录（如果不存在）
    mkdir -p "$LANG_DIR"

    # 检查默认语言文件是否存在，不存在则创建
    if [ ! -f "$LANG_DIR/$SYSTEM_LANG.properties" ]; then
      touch "$LANG_DIR/$SYSTEM_LANG.properties"
    fi
    # 初始化消息计数器
    init_message_counters
  }

  # 初始化消息计数器（用于保持消息ID的一致性）
  init_message_counters() {
    # 从现有的properties文件中提取计数器
    if [ -f "$LANG_DIR/$SYSTEM_LANG.properties" ]; then
      while IFS='=' read -r key value; do
        # 忽略注释行和空行
        if [[ "$key" =~ ^#.*$ || -z "$key" ]]; then
          continue
        fi

        # 提取函数名和消息类型
        local func_type=${key%.*} # 如 initial_env.info
        local counter=${key##*.}  # 如 001

        # 更新计数器（如果需要）
        if [[ "$counter" =~ ^[0-9]+$ ]]; then
          local current_count=${MESSAGE_COUNTERS["$func_type"]:-0}
          if [ "$counter" -ge "$current_count" ]; then
            MESSAGE_COUNTERS["$func_type"]=$((counter + 1))
          fi
        fi
      done <"$LANG_DIR/$SYSTEM_LANG.properties"
    fi
  }

  # 从properties文件中获取翻译
  get_translation() {
    local key="$1"
    local default_text="$2"

    # 检查properties文件是否存在
    if [ ! -f "$LANG_DIR/$SYSTEM_LANG.properties" ]; then
      echo "$default_text"
      return
    fi

    # 搜索翻译
    local translation
    translation=$(grep "^$key=" "$LANG_DIR/$SYSTEM_LANG.properties" | cut -d'=' -f2- | sed 's/^"\(.*\)"$/\1/')

    # 如果未找到翻译，返回默认文本
    if [ -z "$translation" ]; then
      echo "$default_text"
    else
      echo "$translation"
    fi
  }

  # 获取消息ID
  get_message_id() {
    local func="$1"
    local type="$2"

    local func_type="$func.$type"

    # 获取当前计数
    local count=${MESSAGE_COUNTERS["$func_type"]:-1}

    # 格式化为三位数字（如001）
    printf "%s.%03d" "$func_type" "$count"
  }

  # 更新消息计数器
  update_message_counter() {
    local func="$1"
    local type="$2"

    local func_type="$func.$type"
    local current_count=${MESSAGE_COUNTERS["$func_type"]:-0}
    MESSAGE_COUNTERS["$func_type"]=$((current_count + 1))
  }

  # 格式化字符串，替换{0}, {1}等占位符
  format_string() {
    local template="$1"
    shift

    local result="$template"
    local i=0
    for arg in "$@"; do
      result="${result//\{$i\}/$arg}"
      ((i++))
    done

    echo "$result"
  }

  # ==============================================================================
  # 主程序（用于实际功能）
  # 处理shell文件中的语言函数
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    i18n_main() {
      eval "$(parse_options "$@")" # 需在cmd_meta定义同名子对象
      local options="$1"

      local noPrompt="$(json get options "y")"  # 直接操作
      OVERWRITE_ALL="$(json get options "y")"   # 直接操作
      local sys_lang=$(json get options "lang") # 选择语言

      local operate="$2"
      case "$operate" in
        add)
          [[ "$sys_lang" == 0 ]] && sys_lang="$SYSTEM_LANG"
          add_lang_files "$sys_lang"
          ;;
        del)
          [[ "$sys_lang" == 0 ]] && exiterr "请输入语言参数，如 --lang={0}" "$SYSTEM_LANG"
          del_lang_files "$sys_lang" "$noPrompt"
          ;;
        *)
          upd_lang_files "${@}"
          ;;
      esac

    }

    i18n_main "$@"
  fi

fi
