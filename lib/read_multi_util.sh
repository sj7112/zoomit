#!/bin/bash

# Load once only
if [[ -z "${LOADED_DOCKER:-}" ]]; then
  LOADED_DOCKER=1

  # ==============================================================================
  # 提供交互式多选界面，供用户选择要启用的基础设施组件
  # 输出：
  #   SELECTED - 关联数组，存储用户选择的组件状态
  # 使用示例：
  #   用户可输入：1 4 5（空格分隔的编号）
  # ==============================================================================
  # multi-selection interface to select infrastructure components to enable
  # Output:
  #   SELECTED - the selection status of user-chosen components
  # Usage example:
  #   User input: 1 4 5 (space-separated component numbers)
  # ==============================================================================
  print_options() {
    local options_var="$1"                               # option values
    eval "local -a _options=(\"\${${options_var}[@]}\")" # Get array contents using eval
    local per_line="${2:-1}"                             # Number of items per line, default=1

    # calculate the max width
    local maxlen=0
    for opt in "${_options[@]}"; do
      [[ ${#opt} -gt $maxlen ]] && maxlen=${#opt}
    done

    # print options
    local total=${#_options[@]}
    for ((i = 0; i < total; i++)); do
      local index=$((i + 1))
      local label="${_options[i]}"
      printf "%2d) %-*s" "$index" "$maxlen" "$label"

      if (((i + 1) % per_line == 0)) || ((i + 1 == total)); then
        echo
      else
        printf "   "
      fi
    done
  }

  print_tips() {
    # ANSI color
    local BG_BLUE="\033[44m"
    local NC="\033[0m" # reset color

    local str="多选组件：格式如 1 2 3；再次选择相同项目可取消选择，回车结束"
    echo
    echo -e "${BG_BLUE} ${str} ${NC}"
    echo
  }

  print_current_selection() {
    local curr_opt="$1" # option values
    printf "– 当前选择: %s\n\n" "${curr_opt:-无}" >&2
    echo "$curr_opt"
  }

  toggle_selection() {
    local options_var="$1"                               # option values
    eval "local -a _options=(\"\${${options_var}[@]}\")" # Get array contents using eval
    local _def_opts="$2"                                 # default values
    local add_cut_index="${3:-}"                         # add / cut index of options

    # 将 curr_opt 和 add_cut_index 转为可查集合
    declare -A opt_map
    local opt
    for opt in $_def_opts; do
      opt_map["$opt"]=1
    done

    declare -A idx_map
    local idx
    for idx in $add_cut_index; do
      idx_map["$idx"]=1
    done

    # 处理后的结果
    local -a new_opts=()
    local -a valid_selections=()
    local -a canceled_selections=()
    for ((i = 0; i < ${#_options[@]}; i++)); do
      opt="${_options[$i]}"
      idx=$((i + 1))
      if [[ -n "${idx_map[$idx]+x}" ]]; then
        [[ -z "${opt_map[$opt]+x}" ]] && new_opts+=("$opt") && valid_selections+=("$opt") # add opt
        [[ -n "${opt_map[$opt]+x}" ]] && canceled_selections+=("$opt")                    # remove opt
      else
        [[ -n "${opt_map[$opt]+x}" ]] && new_opts+=("$opt") # add opt
      fi
    done

    if [[ ${#valid_selections[@]} -gt 0 ]]; then
      echo -n "✔ 已选择: " >&2
      printf "%s " "${valid_selections[@]}" >&2
      echo >&2
    fi

    if [[ ${#canceled_selections[@]} -gt 0 ]]; then
      echo -n "✘ 取消选择: " >&2
      printf "%s " "${canceled_selections[@]}" >&2
      echo >&2
    fi

    print_current_selection "${new_opts[*]}"
  }

  multiple_select() {
    local options_var="$1"                                 # 数组变量名
    eval "local -a _options=(\"\${${options_var}[@]}\")"   # 使用 eval 取出数组内容
    local def_opts_var="$2"                                # 数组变量名
    eval "local -a _def_opts=(\"\${${def_opts_var}[@]}\")" # 使用 eval 取出数组内容
    local result_f=$3                                      # Temp file to store result

    print_options "$1" "${4:-1}" # Number of items per line, default=1
    print_tips
    local curr_opts=$(print_current_selection "${_def_opts[*]}")

    valid_selections=()
    while true; do
      read -p "> " input
      [[ -z "$input" ]] && break

      if [[ ! "$input" =~ ^[0-9\ ]+$ ]]; then
        echo "✘ 请输入有效编号 (1-${#_options[@]})"
        continue
      fi

      read -ra choices <<<"$input"
      choice_err=""
      for choice in "${choices[@]}"; do
        if [[ $choice -eq 0 || $choice -gt ${#_options[@]} ]]; then
          choice_err+=" $choice"
        fi
      done
      if [[ -n "$choice_err" ]]; then
        echo "✘ 无效编号：$choice_err"
        continue
      fi

      curr_opts=$(toggle_selection "$1" "$curr_opts" "$input")
    done
    _def_opts=($curr_opts)         # change the result
    echo "$curr_opts" >"$result_f" # add to the file
  }

  # ==============================================================================
  # 选择要启用的基础设施组件
  # shellcheck disable=SC2034
  # ==============================================================================
  infra_setup() {
    local result_f=$(generate_temp_file "${1:-}") # Generate a temp file to store result

    echo
    prompt="请选择要启用的基础设施组件 (多选)："
    echo "$prompt"

    local OPTIONS=("NGINX" "MARIADB" "POSTGRES" "REDIS" "MINIO")
    local DEF_OPTS=("NGINX" "MARIADB")
    PER_LINE=3
    multiple_select OPTIONS DEF_OPTS "$result_f" "$PER_LINE"

    # 写入 .env 文件
    echo "⏎ 选择完成，正在保存配置到 .env 文件..."
    # declare -A SELECTED
    # save_env_docker SELECTED
  }

  # ==============================================================================
  # 选择要启用的应用组件
  # shellcheck disable=SC2034
  # ==============================================================================
  apps_setup() {
    local result_f=$(generate_temp_file "${1:-}") # Generate a temp file to store result

    echo
    prompt="请选择要启用的应用组件 (多选)："
    echo "$prompt"

    local OPTIONS=("VAULTWARDEN" "NEXTCLOUD")
    local DEF_OPTS=() # 初始化关联数组
    PER_LINE=5
    multiple_select OPTIONS DEF_OPTS "$result_f" "$PER_LINE"
    # 写入 .env 文件
    echo "⏎ 选择完成，正在保存配置到 .env 文件..."
    # declare -A SELECTED
    # save_env_docker SELECTED
  }

  # ==============================================================================
  # Main Function       Only for testing purpose
  # ./lib/docker.sh
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
    source "$LIB_DIR/system.sh"
    source "$LIB_DIR/msg_handler.sh"
    source "$LIB_DIR/hash_util.sh"

    result_f=$(generate_temp_file) # Generate a temp file to store result
    infra_setup "$result_f"
    apps_setup "$result_f"
  fi

fi
