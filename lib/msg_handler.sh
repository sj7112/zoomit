#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_MSG_HANDLER:-}" ]]; then
  LOADED_MSG_HANDLER=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  source "$LIB_DIR/json_handler.sh"

  # 颜色定义
  RED='\033[0;31m'
  YELLOW='\033[0;33m'
  GREEN='\033[0;32m'
  DARK_BLUE='\033[0;34m' # 暗蓝色
  CYAN='\033[0;36m'      # 青色 (Cyan)
  RED_BG='\033[41m'      # 红色背景
  NC='\033[0m'           # No Color

  # 获取当前系统语言
  ENVIRONMENT="TEST"    # TEST 测试环境 | PROD 生产环境
  LANG_CODE=${LANG:0:2} # 取前两个字母，比如 "en"、"zh"

  # 根据语言定义消息文本
  if [[ "$LANG_CODE" == "zh" ]]; then
    MSG_ERROR="错误"
    MSG_SUCCESS="成功"
    MSG_WARNING="警告"
    MSG_INFO="信息"
  elif [[ "$LANG_CODE" == "de" ]]; then
    MSG_ERROR="Fehler"
    MSG_SUCCESS="Erfolg"
    MSG_WARNING="Warnung"
    MSG_INFO="Information"
  elif [[ "$LANG_CODE" == "es" ]]; then
    MSG_ERROR="Error"
    MSG_SUCCESS="Éxito"
    MSG_WARNING="Advertencia"
    MSG_INFO="Información"
  elif [[ "$LANG_CODE" == "fr" ]]; then
    MSG_ERROR="Erreur"
    MSG_SUCCESS="Succès"
    MSG_WARNING="Avertissement"
    MSG_INFO="Info"
  elif [[ "$LANG_CODE" == "ja" ]]; then
    MSG_ERROR="エラー"
    MSG_SUCCESS="成功"
    MSG_WARNING="警告"
    MSG_INFO="情報"
  elif [[ "$LANG_CODE" == "ko" ]]; then
    MSG_ERROR="오류"
    MSG_SUCCESS="성공"
    MSG_WARNING="경고"
    MSG_INFO="정보"
  else
    MSG_ERROR="ERROR"
    MSG_SUCCESS="SUCCESS"
    MSG_WARNING="WARNING"
    MSG_INFO="INFO"
  fi

  # 返回所有输入参数中的最小值
  min() {
    local min_val=$1

    # 遍历所有参数
    for val in "$@"; do
      # 比较并更新最小值
      ((val < min_val)) && min_val=$val
    done

    echo $min_val
  }

  # 返回所有输入参数中的最大值
  max() {
    local max_val=$1

    # 遍历所有参数
    for val in "$@"; do
      # 比较并更新最大值
      ((val > max_val)) && max_val=$val
    done

    echo $max_val
  }

  # **get translations**
  msg_match_lang() {
    local key="$1"
    local lang_file="./lang/${LANG_CODE}.lang" # lang files are named like 'en.lang', 'zh.lang', etc.

    # 获取当前的父函数及父函数的父函数
    local caller_func_name="${FUNCNAME[2]}"              # 获取父函数的名字
    local caller_func_depth="${#FUNCNAME[@]}"            # 计算当前函数调用栈的深度
    local key_suffix=$(printf "%03d" $caller_func_depth) # 生成类似 "003" 这样的编号

    # 构造翻译键，例如 config_sshd_003
    local translation_key="${caller_func_name}_${key_suffix}"

    # 如果 ENVIRONMENT 是 TEST，自动添加缺失的翻译
    if [[ "$ENVIRONMENT" == "TEST" ]]; then
      # 检查翻译文件中是否存在对应的键
      if ! grep -q "^$key=" "$lang_file"; then
        # 如果没有找到对应的翻译，自动将 key 添加到文件中
        echo "$key=$key" >>"$lang_file"
        echo "Translation for '$key' not found. Added to $lang_file."
      fi
    fi

    # 如果 ENVIRONMENT 是 TEST，自动添加缺失的翻译
    if [[ "$ENVIRONMENT" == "TEST" ]]; then
      # 检查翻译文件中是否存在对应的键
      if ! grep -q "^$translation_key=" "$lang_file"; then
        # 如果没有找到对应的翻译，自动将 key 添加到文件中
        echo "$translation_key=$key" >>"$lang_file"
        echo "Translation for '$translation_key' not found. Added to $lang_file."
      fi
    fi

    # 读取翻译
    local translation
    translation=$(grep -oP "^$translation_key=\K.+" "$lang_file")

    # 如果找不到翻译，返回原始 key
    if [[ -z "$translation" ]]; then
      translation="$key"
    fi

    # 返回翻译文本
    echo "$translation"
  }

  # ==============================================================================
  # 函数名: print_stack_err
  # 描述: 格式化输出程序调用堆栈，以树状结构展示调用链
  # 参数:
  #   $1 - 最大堆栈深度 (默认显示6层，1 <= $1 <= 9)
  # 输出:
  #   以树状结构格式化的调用堆栈，包含文件名、函数名和行号
  # 示例:
  # print_stack_err 6 3   # 从第3层开始，显示最近6层调用栈
  # ==============================================================================
  print_stack_err() {
    local max_depth=$(min ${1:99} 9 $((${#FUNCNAME[@]} - ${2:-2}))) # max stack level = 9
    local -a stack_info=()                                          # 存储堆栈信息的数组
    local max_func_name_len=0                                       # 最大函数名长度，用于对齐
    local -a level_funcs=()                                         # 存储每个级别的所有函数

    # 第一次遍历：收集堆栈信息和确定最大函数名长度
    for ((depth = 1; depth <= max_depth; depth++)); do
      if read -r line func file <<<"$(caller $depth 2>/dev/null)"; then
        if [[ -z "$file" ]]; then
          continue
        fi

        # 添加到堆栈信息数组
        stack_info+=("$file:$func:$line")

        # 记录函数名长度
        level_funcs+=("$func")
      fi
    done

    # 寻找最长的函数名
    for func in "${level_funcs[@]}"; do
      if ((${#func} > max_func_name_len)); then
        max_func_name_len=${#func}
      fi
    done
    # stack_info+=("/usr/local/shell/lib/msg_handler.sh:testwidth:123")
    # print_array stack_info
    # 计算用于对齐的总宽度（包括函数名和必要空隙）
    local align_width=$((max_func_name_len + 3)) # 函数名 + 至少3个空格

    # 第二次遍历：构建和打印树状结构
    echo "" # 以空行开始
    local -a files_seen=()
    local -A file_level=()
    local current_level=0
    local last_file=""
    local -A prefix_map=()     # 存储每个文件的前缀
    local -A has_more_files=() # 标记该级别后面是否还有文件

    # 预处理：找出每个文件在哪个层级，以及该层级后面是否还有文件
    local file_count=${#stack_info[@]}
    local current_index=0
    local file_level_stack=()

    # 构建一个文件到层级的映射
    for entry in "${stack_info[@]}"; do
      current_index=$((current_index + 1))
      IFS=":" read -r file func line <<<"$entry"

      if [[ ! " ${files_seen[*]} " =~ " ${file} " ]]; then
        files_seen+=("$file")

        # 确定文件的层级
        if [[ -z "$last_file" ]]; then
          file_level["$file"]=0
          file_level_stack=("$file")
        else
          # 查看是否需要回溯到之前的层级
          local found=false
          for ((i = ${#file_level_stack[@]} - 1; i >= 0; i--)); do
            if [[ "${file_level_stack[$i]}" == "$last_file" ]]; then
              file_level["$file"]=$((${file_level["$last_file"]} + 1))
              file_level_stack+=("$file")
              found=true
              break
            fi
          done

          # 如果不是回溯，就是同级或新层级
          if ! $found; then
            if [[ -n "$last_file" ]]; then
              file_level["$file"]=${file_level["$last_file"]}
              file_level_stack[${#file_level_stack[@]} - 1]="$file"
            else
              file_level["$file"]=0
              file_level_stack=("$file")
            fi
          fi
        fi

        last_file="$file"
      fi
    done

    # 重置变量用于实际打印
    last_file=""
    local -a func_in_file=()
    local current_file=""
    local current_entry=0

    # 处理堆栈信息以构建树形结构
    for entry in "${stack_info[@]}"; do
      current_entry=$((current_entry + 1))
      IFS=":" read -r file func line <<<"$entry"

      # 如果是新文件，打印文件节点
      if [[ "$file" != "$current_file" ]]; then
        # 结束上一个文件的函数列表
        if [[ -n "$current_file" ]]; then
          # 打印上一个文件中的所有函数
          local prefix="${prefix_map[$current_file]}"
          local file_funcs_count=${#func_in_file[@]}

          for ((i = 0; i < file_funcs_count; i++)); do
            IFS=":" read -r f_name f_line <<<"${func_in_file[$i]}"
            local connector="├"
            if ((i == file_funcs_count - 1)); then
              connector="└"
            fi
            printf "%s%s── %-*s %4d\n" "$prefix" "$connector" "$max_func_name_len" "$f_name" "$f_line"
          done

          func_in_file=()
        fi

        # 打印新文件节点
        local level=${file_level["$file"]}
        local prefix=""

        for ((i = 0; i < level; i++)); do
          prefix="${prefix}    "
        done

        if [[ -z "$last_file" ]]; then
          echo "└── $file"
          prefix_map["$file"]="    "
        else
          echo "${prefix}└── $file"
          prefix_map["$file"]="${prefix}    "
        fi

        current_file="$file"
        last_file="$file"
      fi

      # 添加函数到当前文件的函数列表
      func_in_file+=("$func:$line")
    done

    # 打印最后一个文件的函数
    if [[ -n "$current_file" && ${#func_in_file[@]} -gt 0 ]]; then
      local prefix="${prefix_map[$current_file]}"
      local file_funcs_count=${#func_in_file[@]}

      for ((i = 0; i < file_funcs_count; i++)); do
        IFS=":" read -r f_name f_line <<<"${func_in_file[$i]}"
        local connector="├"
        if ((i == file_funcs_count - 1)); then
          connector="└"
        fi
        printf "%s%s── %-*s %4d\n" "$prefix" "$connector" "$max_func_name_len" "$f_name" "$f_line"
      done
    fi
  }

  # ==============================================================================
  # 功能：
  # 获取当前执行的函数名和文件名
  #
  # 输出格式：
  # 返回全局变量：CURRENT_FUNCTION | CURRENT_FILE
  # ==============================================================================
  get_current_context() {
    local stack
    stack=$(caller 2) # 绕过消息函数，找到实际执行的函数
    echo "$stack" >&2
    local func=$(echo "$stack" | awk '{print $2}')
    local file=$(echo "$stack" | awk '{print $3}')

    CURRENT_FUNCTION="$func"
    CURRENT_FILEPATH="$file"
    CURRENT_FILE=$(basename "$file")
    echo "===>" "$CURRENT_FUNCTION" "$CURRENT_FILEPATH" "$CURRENT_FILE" >&2
  }

  # ==============================================================================
  # 功能：
  # template自动合并动态参数
  #
  # 参数：
  # 第一个参数为模板；后续参数用来替换模板中的字符串
  #
  # 使用示例：
  # msg_parse_tmpl "How {0} {1} {0}!" "do" "you" ==> "How do you do!"
  #
  # 注意事项：
  # 1) 调试只能用echo "..." >&2 ！！！否则父函数接收echo输出时，会出错
  # ==============================================================================
  msg_parse_tmpl() {
    local template="$1" # 带占位符的模板：{0}{1}...

    local i=0
    for var in "${@:2}"; do
      template="${template//\{$i\}/$var}" # 替换 {i}
      ((i = i + 1))
    done
    echo -e "$template"
  }

  # ==============================================================================
  # 功能：
  # 字符串翻译和字符串解析
  # 1. 链接自动翻译，获取template
  # 2. template自动合并动态参数
  # 3. 区分FUNCNAME[1]，输出不同颜色和风格
  #    exiterr：❌ 展示错误消息并退出
  #      error：❌ 错误消息
  #    success：✅ 成功消息
  #    warning：⚠️ 警告消息
  #       info：🔷  提示消息
  #      string：  普通文本
  #
  # 参数：
  # -i : 无需翻译
  # -s : 打印错误栈stack
  # -e : 返回1（表示本条信息为错误提示）
  #
  # 使用示例：
  # msg_parse_param "How {0} {1} {0}!" "do" "you" ==> "How do you do!"
  # msg_parse_param "How are you!" ==> 无需解析
  #
  # 注意事项：
  # 1) 调试只能用echo "..." >&2 ！！！否则父函数接收echo输出时，会出错
  # ==============================================================================
  msg_parse_param() {
    eval "$(parse_options "$@")" # 需在cmd_meta定义同名子对象
    local options="$1"
    shift

    # 自动翻译
    # if ! json_getopt "i"; then
    #   get_current_context
    #   # 构建消息ID
    #   local msg_id=$(get_message_id "$CURRENT_FUNCTION" "${FUNCNAME[1]}")
    #   update_message_counter "$CURRENT_FUNCTION" "${FUNCNAME[1]}"

    #   # 获取翻译
    #   local translated_message
    #   translated_message=$(get_translation "$msg_id" "$message")
    # fi

    local template=$(msg_parse_tmpl "$@") # parse text by template

    local stackerr
    if json_getopt "$options" "s"; then
      stackerr=$(print_stack_err 6 3) # print stack error (level ≤ 6)
      template+=" $stackerr"
    fi

    if [[ "${FUNCNAME[1]}" == "exiterr" || "${FUNCNAME[1]}" == "error" ]]; then
      echo -e "${RED}❌ ${MSG_ERROR}: $template${NC}" >&2
    elif [[ "${FUNCNAME[1]}" == "success" ]]; then
      echo -e "${GREEN}✅ ${MSG_SUCCESS}: $template${NC}"
    elif [[ "${FUNCNAME[1]}" == "warning" ]]; then
      echo -e "${YELLOW}⚠️ ${MSG_WARNING}: $template${NC}"
    elif [[ "${FUNCNAME[1]}" == "info" ]]; then
      echo -e "${DARK_BLUE}🔷 ${MSG_INFO}: $template${NC}"
    elif [[ "${FUNCNAME[1]}" == "string" ]]; then
      echo -e "$template" # normal text (no color)
    fi

    if json_getopt "$options" "e"; then return 1; fi # 如有需要，返回错误，供调用者使用
  }

  #
  # ==============================================================================
  # Auto translation: string | exiterr | error | success | warning | info
  # 自动翻译 + 解析函数
  #
  # params:
  # -i : ignore (跳过多语言翻译)
  # -s : sequence (手动设置序号)
  # -o : line order (行内序号 - 需手动输入)
  # ==============================================================================
  string() { msg_parse_param "$@"; }
  exiterr() {
    msg_parse_param "$@"
    exit 1
  }
  error() { msg_parse_param "$@"; }
  success() { msg_parse_param "$@"; }
  warning() { msg_parse_param "$@"; }
  info() { msg_parse_param "$@"; }
fi
