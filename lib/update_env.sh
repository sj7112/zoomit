#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_UPDATE_ENV:-}" ]]; then
  LOADED_UPDATE_ENV=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry

  CONF_DIR="$(dirname "$BIN_DIR")/config"          # system config direcotry
  DOCKER_DIR="$(dirname "$BIN_DIR")/config/docker" # docker config direcotry
  source "$LIB_DIR/debug_tool.sh"
  ENV_SYSTEM="$CONF_DIR/.env"
  ENV_DOCKER="$DOCKER_DIR/.env"

  # 声明有序数组和关联数组
  declare -A ENV_NETWORK ENV_INFRASTRUCTURE
  declare -a keys_network keys_infrastructure

  # 初始化函数：从.env文件读取并初始化
  init_env() {
    local env_file="$1"

    # 确保 env_file 存在
    if [[ ! -f "$env_file" ]]; then
      exiterr -i "$env_file not found!"
    fi

    local section=""
    while IFS='=' read -r key value; do
      # 跳过空行
      if [[ -z "$key" ]]; then
        continue
      fi

      # 去除首尾空格和换行符
      key=$(echo "$key" | xargs | tr -d '\r\n')
      value=$(echo "$value" | xargs | tr -d '\r\n')

      # 检测标题行(#=xxx)
      if [[ "$key" == "#" ]]; then
        # 判断section类型
        if [[ "$value" == "network" ]]; then
          section="network"
        elif [[ "$value" == "infrastructure" ]]; then
          section="infrastructure"
        fi
        continue
      fi

      # 根据section存入不同数组
      if [[ "$section" == "network" ]]; then
        ENV_NETWORK["$key"]="$value"
        keys_network+=("$key")
      elif [[ "$section" == "infrastructure" ]]; then
        ENV_INFRASTRUCTURE["$key"]="$value"
        keys_infrastructure+=("$key")
      fi
    done <"$env_file"
  }

  # 显示环境变量函数
  show_env() {
    echo "#=network"
    for key in "${keys_network[@]}"; do
      echo "$key=${ENV_NETWORK[$key]}"
    done

    echo "#=infrastructure"
    for key in "${keys_infrastructure[@]}"; do
      echo "$key=${ENV_INFRASTRUCTURE[$key]}"
    done
  }

  # 修改环境变量值
  set_env() {
    local section="$1"
    local key="$2"
    local value="$3"

    if [[ "$section" == "network" ]]; then
      ENV_NETWORK["$key"]="$value"
    elif [[ "$section" == "infrastructure" ]]; then
      ENV_INFRASTRUCTURE["$key"]="$value"
    fi
  }

  # 保存函数：按项目匹配更新文件
  save_env() {
    local env_file="$1"
    local -n env_array="$2"
    local -n keys_array="$3"
    local flag="${4:-0}" # 备份标志，默认为0（备份）

    # 备份原文件
    if [[ "$flag" -eq 0 ]]; then
      cp "$env_file" "$env_file.bak"
    fi

    # 临时文件
    local temp_file
    temp_file=$(mktemp)

    # 逐行读取文件，按项目匹配更新
    while IFS= read -r line; do
      # 保留空行和注释行
      if [[ -z "$line" || "$line" == \#* ]]; then
        echo "$line" >>"$temp_file"
        continue
      fi

      # 拆分键值对
      local key=$(echo "$line" | cut -d '=' -f 1 | xargs)
      local value=$(echo "$line" | cut -d '=' -f 2- | xargs)

      # 检查是否需要更新
      if string_array_contain keys_array "$key"; then
        echo "$key=${env_array[$key]}" >>"$temp_file" # 更新值
      else
        echo "$line" >>"$temp_file" # 保持原值
      fi
    done <"$env_file"

    # 将更新内容写回文件
    mv "$temp_file" "$env_file"
  }

  # 初始化函数：读取python传入的.env对象并初始化
  init_env_py() {
    local env_json="$1"
    local section="$2"

    # 调用Python解析JSON并输出键值对
    while IFS='=' read -r key value; do
      # 根据section存入不同数组
      if [[ "$section" == "network" ]]; then
        ENV_NETWORK["$key"]="$value"
        keys_network+=("$key")
      elif [[ "$section" == "infrastructure" ]]; then
        ENV_INFRASTRUCTURE["$key"]="$value"
        keys_infrastructure+=("$key")
      fi
    done < <(echo "$env_json" | jq -r 'to_entries[] | "\(.key)=\(.value)"')
  }

  # 保存函数：按项目匹配更新文件
  save_env_docker() {
    local -n env_array="$1"
    local flag="${2:-0}" # 备份标志，默认为0（备份）

    # 备份原文件
    if [[ "$flag" -eq 0 ]]; then
      cp "$ENV_DOCKER" "$ENV_DOCKER.bak"
    fi

    # 临时文件
    local temp_file
    temp_file=$(mktemp)

    # 逐行读取文件，按项目匹配更新
    while IFS= read -r line; do
      # 保留空行和注释行
      if [[ -z "$line" || "$line" == \#* ]]; then
        echo "$line" >>"$temp_file"
        continue
      fi

      # 拆分键值对
      local key=$(echo "$line" | cut -d '=' -f 1 | xargs)
      local value=$(echo "$line" | cut -d '=' -f 2- | xargs)

      # 检查是否需要更新
      if [[ -v env_array[$key] ]]; then
        echo "$key=${env_array[$key]}" >>"$temp_file"
      else
        echo "$key=" >>"$temp_file" # 无需设置
      fi
    done <"$ENV_DOCKER"

    # 将更新内容写回文件
    mv "$temp_file" "$ENV_DOCKER"
  }

  # ==============================================================================
  # 主程序（用于测试）
  # 修改、显示、写入配置文件
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    main() {
      # 初始化环境变量
      init_env "$ENV_SYSTEM"

      # 修改示例，保存到文件
      local old_curr_ip="${ENV_NETWORK["CURR_IP"]}"
      set_env "network" "CURR_IP" "192.168.1.100"
      save_env "$ENV_SYSTEM" ENV_NETWORK keys_network

      # 改回原始值
      ENV_NETWORK["CURR_IP"]="$old_curr_ip"
      save_env "$ENV_SYSTEM" ENV_NETWORK keys_network "1" # 1表示不备份

      # 比较.env和.bak文件
      test_assertion "cmp -s '$ENV_SYSTEM' '$ENV_SYSTEM.bak'" "CURR_IP: $old_curr_ip"
    }

    main "$@"
  fi

fi
