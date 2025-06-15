#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_LANG_UTILS:-}" ]]; then
  LOADED_LANG_UTILS=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry

  declare -A LANGUAGE_MSGS # 二维语言关联数组

  # 测试终端是否支持UTF-8字符
  # 返回 0 表示支持，1 表示不支持
  test_terminal_display() {
    local temp_file=$(mktemp)
    local test_strings=(
      "café résumé € ¥"
      "→ ← ↑ ↓"
      "± × ÷ ≈"
      "😊 🌟 ❤️"
      "⚡ 🔥 💻"
      "你好世界"
      "こんにちは"
      "안녕하세요"
    )

    local total_expected_bytes=0
    local actual_bytes=0

    # 计算预期字节数并测试输出
    for test_str in "${test_strings[@]}"; do
      if printf "%s\n" "$test_str" >>"$temp_file" 2>/dev/null; then
        # 计算这个字符串的UTF-8字节长度
        local str_bytes=$(printf "%s" "$test_str" | wc -c 2>/dev/null || echo 0)
        total_expected_bytes=$((total_expected_bytes + str_bytes + 1)) # +1 for newline
      else
        # 如果无法输出，说明不支持
        rm -f "$temp_file"
        return 1
      fi
    done

    # 检查实际文件大小
    actual_bytes=$(wc -c <"$temp_file" 2>/dev/null || echo 0)
    rm -f "$temp_file"

    # 如果实际字节数明显小于预期，说明UTF-8字符被截断或转换
    if [[ $actual_bytes -lt $((total_expected_bytes - 10)) ]]; then
      return 1
    fi

    # 额外检查：locale是否支持UTF-8
    if command -v locale >/dev/null 2>&1; then
      if ! locale charmap 2>/dev/null | grep -qi "utf"; then
        return 1
      fi
    fi

    return 0
  }

  # ==============================================================================
  # 初始化语言相关函数
  # ==============================================================================
  # 格式化语言代码
  normalize_locale() {
    input="$1"

    # 提取语言部分和编码部分
    lang_part=$(echo "$input" | cut -d. -f1)
    charset_part=$(echo "$input" | cut -s -d. -f2)

    # 分别处理语言国家部分（如 zh_CN）
    # 小写语言码 + 大写国家码
    lang_prefix=$(echo "$lang_part" | cut -d_ -f1 | tr '[:upper:]' '[:lower:]')
    lang_suffix=$(echo "$lang_part" | cut -d_ -f2 | tr '[:lower:]' '[:upper:]')

    # 重组语言部分
    norm_lang="${lang_prefix}_${lang_suffix}"

    # 编码部分统一成小写，如 utf8 / iso8859-1
    if [ -n "$charset_part" ]; then
      norm_charset=$(echo "$charset_part" | tr '[:upper:]' '[:lower:]')
      echo "${norm_lang}.${norm_charset}"
    else
      echo "$norm_lang"
    fi
  }

  # 获取默认语言(不允许使用 C 或 POSIX)
  get_default_lang() {
    default_lang=""
    for file in /etc/locale.conf /etc/default/locale /etc/sysconfig/i18n; do
      if [ -f "$file" ]; then
        default_lang=$(grep "^LANG=" "$file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"')
        if [ -n "$default_lang" ]; then
          if [[ "$LANG" == "C" || "$LANG" == "POSIX" ]]; then
            break # 必须重新选择语言
          fi
          local base="${default_lang%.*}"    # 移除 .utf8 / .UTF-8
          local short="${base%_*}"           # 语言代码
          export LANGUAGE="${base}:${short}" # 获取语言代码（如 en_US.UTF-8 -> en_US:en）
          echo "$default_lang"
          return
        fi
      fi
    done

    # Check if the system default language was retrieved
    echo "Please set shell language (e.g., en_US.UTF-8):"
    while true; do
      read -r input_lang
      if [[ "$LANG" == "C" || "$LANG" == "POSIX" ]]; then
        echo "Invalid language format. Please re-enter (e.g., en_US.UTF-8):"
      fi
      # Validate the format (e.g., xx_YY.UTF-8)
      normalized=$(normalize_locale "$input_lang")
      if [[ "$normalized" =~ ^[a-z]{2}_[A-Z]{2}(\.[a-z0-9-]+)?$ ]]; then
        # Check if it exists in the locale -a list
        if locale -a | grep -Fxq "$normalized"; then
          default_lang="$normalized"
          break
        else
          echo "Language not in the system locale list (locale -a). Please re-enter:"
        fi
      else
        echo "Invalid language format. Please re-enter (e.g., en_US.UTF-8):"
      fi
    done
    echo "$default_lang"
  }

  # 检查当前语言设置是否支持UTF-8
  check_locale() {
    lang=$1
    need_change=0

    case "$lang" in
      *GB2312* | *GBK* | *Big5*)
        new_lang=$(echo "$lang" | sed 's/\.[^.]*$/.UTF-8/')
        ;;
      *EUC-JP* | *SHIFT_JIS*)
        new_lang=$(echo "$lang" | sed 's/\.[^.]*$/.UTF-8/')
        ;;
      *EUC-KR*)
        new_lang=$(echo "$lang" | sed 's/\.[^.]*$/.UTF-8/')
        ;;
      *KOI8-R* | *CP1251*)
        new_lang=$(echo "$lang" | sed 's/\.[^.]*$/.UTF-8/')
        ;;
      *ISO8859-6* | *TIS-620*)
        new_lang=$(echo "$lang" | sed 's/\.[^.]*$/.UTF-8/')
        ;;
      *)
        new_lang="$lang" # 其他语言或UTF-8，无需修改
        need_change=1
        ;;
    esac

    echo "$new_lang"    # 返回新的语言设置
    return $need_change # 返回是否需要修改
  }

  # 更新或添加 LANG 设置到 ~/.profile
  set_user_lang_profile() {
    local lang="$1" # 目标语言（如 zh_CN.UTF-8）

    local profile_file="$HOME/.profile" # 优先修改 ~/.profile
    if [ ! -f "$profile_file" ]; then
      touch "$profile_file"
    fi

    # 更新或添加 LANG 设置
    if grep -q "^LANG=" "$profile_file"; then
      sed -i "s|^LANG=.*|LANG=\"$lang\"|" "$profile_file"
    else
      echo "LANG=\"$lang\"" | tee -a "$profile_file" >/dev/null
    fi

    # 从 lang 生成 LANGUAGE 值，例如 en_US.UTF-8 -> en_US:en
    local language_value="$LANGUAGE"
    # 更新或添加 LANGUAGE 设置
    if grep -q "^LANGUAGE=" "$profile_file"; then
      sed -i "s|^LANGUAGE=.*|LANGUAGE=\"$language_value\"|" "$profile_file"
    else
      echo "LANGUAGE=\"$language_value\"" | tee -a "$profile_file" >/dev/null
    fi
  }

  # 更新或添加 LANG 设置
  set_user_lang_sh() {
    local config_file="$1"
    local lang="$2" # 目标语言（如 en_US.UTF-8）

    if [ ! -f "$config_file" ]; then
      touch "$config_file"
    fi

    # 更新或添加 LANG 设置
    export_line="export LANG=\"$lang\""
    if grep -q "^export LANG=" "$config_file"; then
      sed -i "s|^export LANG=.*|$export_line|" "$config_file"
    else
      echo "$export_line" | tee -a "$config_file" >/dev/null
    fi

    # 从 lang 生成 LANGUAGE 值，例如 en_US.UTF-8 -> en_US:en
    local base="${lang%.*}"  # 移除 .utf8 / .UTF-8
    local short="${base%_*}" # 语言代码
    local language_value="${base}:${short}"
    # 更新或添加 LANGUAGE 设置
    local export_line="export LANGUAGE=\"$language_value\""
    if grep -q "^export LANGUAGE=" "$config_file"; then
      sed -i "s|^export LANGUAGE=.*|$export_line|" "$config_file"
    else
      echo "$export_line" | tee -a "$config_file" >/dev/null
    fi
  }

  # 更新或添加 LANG 设置
  update_user_locale() {
    local profile_file="$HOME/.profile"
    if [ -n "$profile_file" ]; then
      set_user_lang_profile "$1" # 优先设置 ~/.profile
    elif [[ "$SHELL" =~ "bash" ]]; then
      set_user_lang_sh "$HOME/.bashrc" "$1" # 设置 ~/.bashrc
    elif [[ "$SHELL" =~ "zsh" ]]; then
      set_user_lang_sh "$HOME/.zshrc" "$1" # 设置 ~/.zshrc
    else
      set_user_lang_profile "$1" # 非bash或zsh，设置 ~/.profile
    fi
  }

  # 如果当前语言设置不支持UTF-8，尝试修复
  fix_shell_locale() {
    local lang=$(get_default_lang)         # 返回 LANG 系统默认值
    local new_lang=$(check_locale "$lang") # UTF-8修复
    if [ $? -ne 0 ]; then
      echo "Need UTF-8, try to fix LANG: $lang..."
    fi

    if ! test_terminal_display; then
      new_lang="en_US.UTF-8" # 终端不支持UTF-8，强制设置为 en_US.UTF-8
      echo "Terminal does not support UTF-8, set LANG to $new_lang"
    else
      echo "set LANG to $new_lang"
      local curr_lang=${LC_ALL:-${LANG:-C}} # 读取用户语言设置
      if [ "${curr_lang,,}" != "${new_lang,,}" ]; then
        if confirm_action "Change $USER language from [$curr_lang] to [$new_lang]?"; then
          update_user_locale "$new_lang" # 永久改变 LANG 和 LANGUAGE
        fi
      fi
    fi

    export LANG="$new_lang"            # 设置 LANG
    local base="${new_lang%.*}"        # 移除 .utf8 / .UTF-8
    local short="${base%_*}"           # 语言代码
    export LANGUAGE="${base}:${short}" # 设置 LANGUAGE
  }

  # ==============================================================================
  # 翻译语言相关函数
  # ==============================================================================
  # 获取语言配置文件路径
  get_language_prop() {
    local lang_format="${1:-$LANGUAGE}"
    # 解析语言格式 zh_CN:zh -> zh_CN 和 zh
    local primary_lang="${lang_format%%:*}"  # zh_CN
    local fallback_lang="${lang_format##*:}" # zh

    # 优先查找完整语言文件
    if [[ -f "$LANG_DIR/${primary_lang}.properties" ]]; then
      echo "$LANG_DIR/${primary_lang}.properties"
      return 0
    fi

    # 其次查找简化语言文件
    if [[ -f "$LANG_DIR/${fallback_lang}.properties" ]]; then
      echo "$LANG_DIR/${fallback_lang}.properties"
      return 0
    fi

    # 都没找到返回错误
    echo "Error: No language file found for '$lang_format'" >&2
    return 1
  }

  # 加载语言消息(手动 key 拼接模拟子 map)
  load_trans_msgs() {
    # 设置 shell 语言
    fix_shell_locale

    # 判断是否已经加载过
    if [[ -v LANGUAGE_MSGS ]] && [[ ${#LANGUAGE_MSGS[@]} -ne 0 ]]; then
      return 0 # 已加载，直接返回
    fi

    local properties_file=$(get_language_prop)
    if [[ $? -ne 0 ]]; then
      echo "Use default language 'en_US:en'" >&2
      properties_file=$(get_language_prop 'en_US:en')
    fi

    local current_file=""
    while IFS= read -r line; do
      # 跳过空行
      [[ -z "$line" ]] && continue

      # 跳过普通注释行，但保留文件标记
      if [[ "$line" =~ ^[[:space:]]*# ]]; then
        # 匹配文件标记 ■=filename
        if [[ "$line" =~ ^#[[:space:]]*■=(.+)$ ]]; then
          current_file="${BASH_REMATCH[1]}"
        fi
        continue
      fi

      # 跳过分隔行
      [[ "$line" =~ ^[[:space:]]*--- ]] && continue

      # 匹配键值对 KEY=VALUE
      if [[ "$line" =~ ^([A-Za-z0-9_-]+)=(.*)$ ]]; then
        local key="${BASH_REMATCH[1]}"
        local value="${BASH_REMATCH[2]}"

        # 处理多行值（以 \ 结尾的行）
        while [[ "$value" =~ \\[[:space:]]*$ ]]; do
          # 移除末尾的反斜杠和空白
          value="${value%\\*}"
          # 读取下一行并追加
          if IFS= read -r next_line; then
            # 移除前导空白
            next_line="${next_line#"${next_line%%[![:space:]]*}"}"
            value="${value}${next_line}"
          else
            break
          fi
        done

        # 存储到数组中，使用文件名作为key前缀
        if [[ -n "$current_file" ]]; then
          LANGUAGE_MSGS["${current_file}:${key}"]="$value"
        fi
      fi
    done <"$properties_file"

    echo "Loaded ${#LANGUAGE_MSGS[@]} messages from $properties_file"
  }

  # 加载语言消息(手动 key 拼接模拟子 map)
  get_trans_msg() {
    msg="$1" # 原始消息

    local current_hash=$(djb2_with_salt_20 "$msg")               # 使用DJB2哈希算法生成消息ID
    current_hash=$(padded_number_to_base64 "$current_hash"_6)    # 转换为6位base64编码
    local source_file="${BASH_SOURCE[3]#$(dirname "$LIB_DIR")/}" # 去掉根目录
    local key="${source_file}:$current_hash"
    local result=""

    # 检查键是否存在
    if [[ -v "LANGUAGE_MSGS[$key]" ]]; then
      result="${LANGUAGE_MSGS[$key]}"
    fi

    if [[ -z "$result" ]]; then
      # 如果没有找到翻译，使用MD5再试一次
      current_hash=$(md5 "$msg")
      key="${source_file}:$current_hash"
      if [[ -v "LANGUAGE_MSGS[$key]" ]]; then
        result="${LANGUAGE_MSGS[$key]}"
      fi
    fi

    if [[ -z "$result" ]]; then
      # 如果还是没有找到翻译，使用原始消息
      result="$msg"
    fi
    echo "$result" # 返回翻译结果
  }

fi
