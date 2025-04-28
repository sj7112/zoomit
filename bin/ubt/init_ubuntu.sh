#!/bin/bash
#
# 一键配置Linux（One-click Configure Ubuntu）
# 自动操作：
#   1）换默认语言、自动升级安装包
#   3）安装ssh
#   4）安装网络、配置DNS
#   5）安装docker-ce
# docker选装：
#   1）redis
#   2）postgres
#   3）mariadb
#   4）minio
#   5）nginx
# 使用示例:
# sudo ./init_main.sh

# 引入消息处理脚本
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)" # bin directory
source "$BIN_DIR/init_main.sh"

set -euo pipefail # 启用严格模式

# 获取sources的配置路径
get_ubt_source_file() {
  if check_root_file "/etc/apt/sources.list.d/ubuntu.sources"; then
    echo "/etc/apt/sources.list.d/ubuntu.sources"
  else
    echo "/etc/apt/sources.list"
  fi
}

# Ubuntu (apt)
init_sources_list() {
  # 1. 动态决定使用旧版还是新版文件
  local sources_file=$(get_ubt_source_file)

  # 2. 检查是否需要初始化（存在 cdrom 或文件为空）
  if grep -q "^deb cdrom:" "$sources_file" || [ ! -s "$sources_file" ]; then
    info "$1" "$DISTRO_OSTYPE"
    file_backup_sj "$sources_file"

    # 3. 根据文件类型生成不同内容
    if [[ "$sources_file" == *.sources ]]; then
      # 新版 .sources 格式
      cat >/tmp/apt_source <<'EOF'
Types: deb
URIs: http://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://security.ubuntu.com/ubuntu
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
    else
      # 旧版 sources.list 格式
      cat >/tmp/apt_source <<'EOF'
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse
EOF
    fi

    # 4. 统一移动文件并设置权限
    $SUDO_CMD mv /tmp/apt_source "$sources_file"
    $SUDO_CMD chmod 644 "$sources_file"
  fi
}

# 检查国家是否在列表之中
check_country_in_list() {
  if [[ -n "$COUNTRY_CODE" && "$1" =~ (^| )"$COUNTRY_CODE"($| ) ]]; then
    return 0
  else
    return 1
  fi
}

# ==============================================================================
# calc_fast_mirrors - 包管理器镜像测速
# 适用：ubuntu
# 参数：
#   $1 - 存镜像URL的临时文件
# 返回值：
#   通过标准输出返回延迟最低的10个HTTP镜像URL，每行一个
# ==============================================================================
calc_fast_mirrors() {
  # 获取所有国家/地区的镜像列表
  local MIRRORS_INDEX=$(curl -s http://mirrors.ubuntu.com/)
  local COUNTRIES=$(echo "$MIRRORS_INDEX" | grep -oP '<a href="\K[A-Z]{2}\.txt' | cut -d. -f1 | sort -u)

  # 交互式选择国家
  local MIRRORS
  while true; do
    read -p "请选择国家/地区代码（回车使用默认值 '$COUNTRY_CODE'）：" USER_INPUT
    USER_INPUT=$(echo "${USER_INPUT}" | tr '[:lower:]' '[:upper:]') # 转为大写
    COUNTRY_CODE=${USER_INPUT:-$COUNTRY_CODE}

    if ! grep -qxF "$COUNTRY_CODE" <<<"$COUNTRIES"; then
      echo "国家代码 $COUNTRY_CODE 不存在于列表中！"
      continue
    fi
    MIRRORS=$(curl -s "http://mirrors.ubuntu.com/${COUNTRY_CODE}.txt" | grep '^http://')
    if [ -z "$MIRRORS" ]; then
      echo "无法获取 ${COUNTRY_CODE} 的镜像列表！"
      continue
    fi
    break # 找到了镜像列表，退出
  done

  # 测速并返回最快的（最多10个）
  echo -e "\n正在测试镜像速度（可能需要几分钟）..."
  local FAST_MIRRORS=$(ping_fastest_mirrors "$MIRRORS")
  echo "$FAST_MIRRORS" >"$1"
}

pick_sources_list() {
  local MAIN_SOURCE=".ubuntu.com/ubuntu"
  local NEW_SOURCE="deb $1 $DISTRO_CODENAME main contrib non-free non-free-firmware"
  # 1. 动态决定使用旧版还是新版文件
  local sources_file=$(get_ubt_source_file)
  warning $sources_file
  if [[ "$sources_file" == *.sources ]]; then
    # 新版本
    local APT_SOURCE_LIST="/etc/apt/sources.list.d/00custom-mirrors.list"
    # echo "$NEW_SOURCE" >"$APT_SOURCE_LIST"
    echo "$NEW_SOURCE" | $SUDO_CMD tee "$APT_SOURCE_LIST" >/dev/null
  else
    # 旧版本
    local APT_SOURCE_LIST="/etc/apt/sources.list"
    # 检查第一行是否匹配主仓库
    if head -n 1 "$APT_SOURCE_LIST" | grep -q "$MAIN_SOURCE"; then
      $SUDO_CMD sed -i "1i $NEW_SOURCE" "$APT_SOURCE_LIST"
    else
      # 不匹配：直接覆盖第一行
      $SUDO_CMD sed -i "1s|^.*|$NEW_SOURCE|" "$APT_SOURCE_LIST"
    fi
  fi
}

# --------------------------
# 主执行流程
# --------------------------
echo "=== sj init $DISTRO_OSTYPE system start ==="
check_env
check_dvd
# update_sys
# config_sshd
# configure_ip
# install_software
# system_config
echo "=== sj init $DISTRO_OSTYPE system end ==="
