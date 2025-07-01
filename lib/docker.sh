#!/bin/bash

# Load once only
if [[ -z "${LOADED_DOCKER:-}" ]]; then
  LOADED_DOCKER=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  : "${CONF_DIR:=$(dirname "$LIB_DIR")/config}"                 # config directory
  DOCKER_DIR="$CONF_DIR/docker"                                 # docker dierctory
  ENV_FILE="$DOCKER_DIR/.env"

  LOG_FILE="/var/log/sj_install.log"

  # ==============================================================================
  # 计数器函数
  # ==============================================================================
  show_notice() {
    # ANSI color
    local BG_BLUE="\033[44m"
    local NC="\033[0m" # reset color

    local str=$(_mf "多选组件：格式如 1 3 4；再次选择相同项目可取消选择，回车结束")
    echo
    echo -e "${BG_BLUE} ${str} ${NC}"
    echo
  }

  # ==============================================================================
  # 提供交互式多选界面，供用户选择要启用的基础设施组件
  # 输出：
  #   SELECTED - 关联数组，存储用户选择的组件状态
  # 使用示例：
  #   用户可输入：1 4 5（空格分隔的编号）
  # ==============================================================================
  multi_select() {
    local -n _options=$1     # 引用：选项数组
    local -n _selected=$2    # 引用：保存选择的关联数组
    local prompt="$3"        # 提示语
    local per_line="${4:-1}" # 每行显示数，默认 1

    echo
    info "$prompt"

    # 计算最大宽度
    local maxlen=0
    for opt in "${_options[@]}"; do
      [[ ${#opt} -gt $maxlen ]] && maxlen=${#opt}
    done

    # 打印选项
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

    # 显示提示信息
    show_notice

    # 显示默认已选项（如果有）
    selected_items=()
    for opt in "${_options[@]}"; do
      [[ -n "${_selected[$opt]+x}" ]] && selected_items+=("$opt")
    done

    if [[ ${#selected_items[@]} -gt 0 ]]; then
      echo -n "当前选择："
      printf "%s " "${selected_items[@]}"
      echo
      echo
    fi

    while true; do
      read -p "> " input
      [[ -z "$input" ]] && break

      read -ra choices <<<"$input"
      valid_selections=()
      canceled_selections=()

      for choice in "${choices[@]}"; do
        [[ -z "$choice" ]] && continue

        if [[ "$choice" =~ ^[0-9]+$ ]]; then
          index=$((choice - 1))
          if [[ $index -ge 0 && $index -lt ${#_options[@]} ]]; then
            name="${_options[$index]}"
          else
            echo "✘ 无效编号：$choice"
            continue
          fi
        else
          echo "✘ 请输入有效编号（1-${#_options[@]}）"
          continue
        fi

        if [[ -n "${_selected[$name]+x}" ]]; then
          unset '_selected[$name]'
          canceled_selections+=("$name")
        else
          _selected[$name]="true"
          valid_selections+=("$name")
        fi
      done

      if [[ ${#valid_selections[@]} -gt 0 ]]; then
        echo -n "✔ 已选择："
        printf "%s " "${valid_selections[@]}"
        echo
      fi

      if [[ ${#canceled_selections[@]} -gt 0 ]]; then
        echo -n "✘ 取消选择："
        printf "%s " "${canceled_selections[@]}"
        echo
      fi

      echo -n "当前选择："
      selected_items=()
      for opt in "${_options[@]}"; do
        [[ -n "${_selected[$opt]+x}" ]] && selected_items+=("$opt")
      done

      if [[ ${#selected_items[@]} -eq 0 ]]; then
        echo "无"
      else
        printf "%s " "${selected_items[@]}"
        echo
      fi
      echo
    done
  }

  # ==============================================================================
  # 选择要启用的基础设施组件
  # shellcheck disable=SC2034
  # ==============================================================================
  infra_setup() {
    local OPTIONS=(NGINX MARIADB POSTGRES REDIS MINIO)
    PROMPT="请选择要启用的基础设施组件（多选）："
    PER_LINE=1

    declare -A SELECTED
    SELECTED=() # 初始化关联数组
    multi_select OPTIONS SELECTED "$PROMPT" "$PER_LINE"
    # 写入 .env 文件
    info "⏎ 选择完成，正在保存配置到 .env 文件..."
    save_env_docker SELECTED

  }

  # ==============================================================================
  # 选择要启用的应用组件
  # shellcheck disable=SC2034
  # ==============================================================================
  apps_setup() {
    local OPTIONS=(VAULTWARDEN NEXTCLOUD)
    PROMPT="请选择要启用的应用组件（多选）："
    PER_LINE=5

    declare -A SELECTED
    SELECTED=() # 初始化关联数组
    multi_select OPTIONS SELECTED "$PROMPT" "$PER_LINE"
    # 写入 .env 文件
    info "⏎ 选择完成，正在保存配置到 .env 文件..."
    save_env_docker SELECTED

  }

fi
