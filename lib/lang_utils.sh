#!/bin/bash

# Ensure it is loaded only once
if [[ -z "${LOADED_LANG_UTILS:-}" ]]; then
  LOADED_LANG_UTILS=1

  # Declare global
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry

  declare -A LANGUAGE_MSGS # key=file:hash, value=translated message

  # Test if terminal supports UTF-8 (0=supported, 1=unsupported)
  test_terminal_display() {
    case "$TERM" in
      # Terminals without UTF-8 support
      vt100 | vt102 | vt220 | vt320 | ansi | dumb)
        return 1
        ;;
      # Others
      *)
        return 0
        ;;
    esac
  }

  # ==============================================================================
  # Language Initialize functions
  # ==============================================================================
  # Normalize locale format
  normalize_locale() {
    input="$1"

    # Reassemble language-country part (e.g., zh_CN)
    lang_part=$(echo "$input" | cut -d. -f1) # e.g., en_US
    lang_prefix=$(echo "$lang_part" | cut -d_ -f1 | tr '[:upper:]' '[:lower:]')
    lang_suffix=$(echo "$lang_part" | cut -d_ -f2 | tr '[:lower:]' '[:upper:]')
    norm_lang="${lang_prefix}_${lang_suffix}"

    # Convert charset to lowercase (e.g., utf8 / iso8859-1)
    charset_part=$(echo "$input" | cut -s -d. -f2)
    if [ -n "$charset_part" ]; then
      norm_charset=$(echo "$charset_part" | tr '[:upper:]' '[:lower:]')
      echo "${norm_lang}.${norm_charset}"
    else
      echo "$norm_lang"
    fi
  }

  # get default language(C or POSIX is not allowed)
  get_default_lang() {
    default_lang=""
    for file in /etc/locale.conf /etc/default/locale /etc/sysconfig/i18n; do
      if [ -f "$file" ]; then
        default_lang=$(grep "^LANG=" "$file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"')
        if [ -n "$default_lang" ]; then
          break
        fi
      fi
    done
    echo "$default_lang"
  }

  # reset language(C or POSIX is not allowed)
  reset_language() {
    local lang
    if ! test_terminal_display; then
      lang="en_US.UTF-8" # Terminal does not support UTF-8, use default value
      echo "Terminal does not support UTF-8, set LANG to $lang" >&2
      echo "$lang"
      return 0
    fi

    local curr_lang="$(get_default_lang)"

    local input_lang
    echo "Please set shell language (Enter = ${curr_lang}):"
    while true; do
      read -r input_lang

      # Enter = current language
      if [[ -z "$input_lang" ]]; then
        input_lang="$curr_lang"
      fi

      # check C or POSIX
      if [[ "${curr_lang^^}" == "C" || "${curr_lang^^}" == "POSIX" ]]; then
        echo "($input_lang) is not allowed. Please enter a valid language (e.g., en_US.UTF-8):"
        continue
      fi

      # format input and check UTF-8 support
      local lang=$(check_locale "$(normalize_locale "$input_lang")")
      if [ $? -eq 0 ]; then
        echo "$input_lang does not support UTF-8, change to $lang"
      fi

      # Validate the format (e.g., xx_YY.UTF-8)
      if [[ "$lang" =~ ^[a-z]{2}_[A-Z]{2}(\.[a-z0-9-]+)?$ ]]; then
        # Check if it exists in the locale -a list
        if locale -a | grep -Fxq "$lang"; then
          echo "set LANG to $new_lang" >&2
          echo "$lang"
          return 0
        else
          echo "Language not in the system locale list (locale -a). Please re-enter:"
        fi
      else
        echo "Invalid language format. Please re-enter (e.g., en_US.UTF-8):"
      fi
    done
  }

  # Check UTF-8 support
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
        new_lang="$lang" # already support UTF-8
        need_change=1
        ;;
    esac

    echo "$new_lang"    # return new language
    return $need_change # return 1 if change needed
  }

  # Update or add LANG setting to ~/.profile
  set_user_lang_profile() {
    local lang="$1"

    local profile_file="$HOME/.profile" # prefer ~/.profile
    if [ ! -f "$profile_file" ]; then
      touch "$profile_file"
    fi

    # Update or add LANG setting
    if grep -q "^LANG=" "$profile_file"; then
      sed -i "s|^LANG=.*|LANG=\"$lang\"|" "$profile_file"
    else
      echo "LANG=\"$lang\"" | tee -a "$profile_file" >/dev/null
    fi

    # Generate LANGUAGE, e.g. en_US.UTF-8 -> en_US:en
    local language_value="$LANGUAGE"
    # Update or add LANGUAGE setting
    if grep -q "^LANGUAGE=" "$profile_file"; then
      sed -i "s|^LANGUAGE=.*|LANGUAGE=\"$language_value\"|" "$profile_file"
    else
      echo "LANGUAGE=\"$language_value\"" | tee -a "$profile_file" >/dev/null
    fi
  }

  # Update or add LANG setting
  set_user_lang_sh() {
    local config_file="$1"
    local lang="$2" # 目标语言（如 en_US.UTF-8）

    if [ ! -f "$config_file" ]; then
      touch "$config_file"
    fi

    # LANG setup
    export_line="export LANG=\"$lang\""
    if grep -q "^export LANG=" "$config_file"; then
      sed -i "s|^export LANG=.*|$export_line|" "$config_file"
    else
      echo "$export_line" | tee -a "$config_file" >/dev/null
    fi

    # LANGUAGE setup, e.g. en_US.UTF-8 -> en_US:en
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

  # Attempts to fix the locale settings to ensure UTF-8 compatibility
  fix_shell_locale() {
    local new_lang=$(reset_language) # system default LANG value

    local curr_lang=${LC_ALL:-${LANG:-C}} # Read user language settings
    if [ "${curr_lang,,}" != "${new_lang,,}" ]; then
      if confirm_action "Change $USER language from [$curr_lang] to [$new_lang]?"; then
        update_user_locale "$new_lang" # Permanently change LANG and LANGUAGE
      fi
    fi

    export LANG="$new_lang" # Set LANG
    local base="${new_lang%.*}"
    local short="${base%_*}"
    export LANGUAGE="${base}:${short}" # Set LANGUAGE
  }

  # ==============================================================================
  # Language translation functions
  # ==============================================================================
  # Get the path to the language configuration file
  get_language_prop() {
    local lang_format="${1:-$LANGUAGE}"      # e.g. zh_CN:zh
    local primary_lang="${lang_format%%:*}"  # zh_CN
    local fallback_lang="${lang_format##*:}" # zh

    # First, look for the complete language file
    if [[ -f "$LANG_DIR/${primary_lang}.properties" ]]; then
      echo "$LANG_DIR/${primary_lang}.properties"
      return 0
    fi

    # Next, look for the simplified language file
    if [[ -f "$LANG_DIR/${fallback_lang}.properties" ]]; then
      echo "$LANG_DIR/${fallback_lang}.properties"
      return 0
    fi

    # If neither is found, return an error
    echo "Error: No language file found for '$lang_format'" >&2
    return 1
  }

  # Load message translations
  initial_language() {
    # fix shell language to ensure UTF-8 support
    fix_shell_locale

    # Skip if already loaded
    if [[ -n "${LANGUAGE_MSGS+x}" ]] && [[ ${#LANGUAGE_MSGS[@]} -ne 0 ]]; then
      return 0
    fi

    local properties_file=$(get_language_prop)
    if [[ $? -ne 0 ]]; then
      echo "Using default language 'en_US:en'" >&2
      properties_file=$(get_language_prop 'en_US:en')
    fi

    local current_file=""
    while IFS= read -r line; do
      # Skip empty lines
      [[ -z "$line" ]] && continue

      # Skip comments, but handle file markers
      if [[ "$line" =~ ^[[:space:]]*# ]]; then
        if [[ "$line" =~ ^#[[:space:]]*■=(.+)$ ]]; then
          current_file="${BASH_REMATCH[1]}"
        fi
        continue
      fi

      # Skip separator lines
      [[ "$line" =~ ^[[:space:]]*--- ]] && continue

      # Match key-value pairs KEY=VALUE
      if [[ "$line" =~ ^([A-Za-z0-9_-]+)=(.*)$ ]]; then
        local key="${BASH_REMATCH[1]}"
        local value="${BASH_REMATCH[2]}"

        # Handle multi-line values ending with "\"
        while [[ "$value" =~ \\[[:space:]]*$ ]]; do
          value="${value%\\*}" # Remove trailing \ and spaces
          if IFS= read -r next_line; then
            next_line="${next_line#"${next_line%%[![:space:]]*}"}" # Trim leading spaces
            value="${value}${next_line}"
          else
            break
          fi
        done

        # Store in array with file prefix
        if [[ -n "$current_file" ]]; then
          LANGUAGE_MSGS["${current_file}:${key}"]="$value"
        fi
      fi
    done <"$properties_file"

    echo "Loaded ${#LANGUAGE_MSGS[@]} messages from $properties_file"
  }

  # Translate message
  get_trans_msg() {
    # Retrieve the translated message for the given input
    msg="$1" # Original message

    local current_hash=$(djb2_with_salt_20 "$msg")               # DJB2 hash algorithm
    current_hash=$(padded_number_to_base64 "$current_hash"_6)    # 6-character base64 encoding
    local source_file="${BASH_SOURCE[3]#$(dirname "$LIB_DIR")/}" # Remove root directory
    local key="${source_file}:$current_hash"
    local result=""

    # Check if the key exists
    if [[ -n "${LANGUAGE_MSGS[$key]+x}" ]]; then
      result="${LANGUAGE_MSGS[$key]}"
    fi

    if [[ -z "$result" ]]; then
      # If translation is not found, try again using MD5
      current_hash=$(md5 "$msg")
      key="${source_file}:$current_hash"
      if [[ -n "${LANGUAGE_MSGS[$key]+x}" ]]; then
        result="${LANGUAGE_MSGS[$key]}"
      fi
    fi

    if [[ -z "$result" ]]; then
      # If still not found, use the original message
      result="$msg"
    fi
    echo "$result" # Return the translation result
  }

fi
