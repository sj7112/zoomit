#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_SOURCE_INSTALL:-}" ]]; then
  LOADED_SOURCE_INSTALL=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/python_bridge.sh"

  PY_BASE_URL="https://github.com/astral-sh/python-build-standalone/releases/download"
  PY_VERSION="3.10.17"
  PY_REL_DATE="20250517" # 使用稳定的发布版本

  PY_INST_DIR="$HOME/.local/python-$PY_VERSION"
  PY_GZ_FILE="/tmp/cpython-${PY_VERSION}-standalone.tar.gz"
  PY_BIN=""
  VENV_DIR="$HOME/.venv"

  # ==============================================================================
  # 选择包管理器
  # ==============================================================================
  # 检查包管理器是否已安装（非 cdrom 安装）
  check_cdrom() {
    local has_cdrom=0
    local cdrom_sources=()

    echo "----------------------------------------"

    case "$DISTRO_OSTYPE" in
      "rhel")
        # 检查 CentOS/RHEL 的 yum/dnf 配置
        echo "检查 YUM/DNF 源配置..."
        local repo_dirs=(
          "/etc/yum.repos.d"
          "/etc/dnf/repos.d"
        )

        for repo_dir in "${repo_dirs[@]}"; do
          if [ -d "$repo_dir" ]; then
            echo "检查目录: $repo_dir"
            for repo_file in "$repo_dir"/*.repo; do
              if [ -f "$repo_file" ]; then
                # 查找包含 file:// 或 cdrom 的配置
                local cdrom_lines=$(grep -n "file://\|cdrom\|media" "$repo_file" 2>/dev/null | grep -v "^#")
                if [ -n "$cdrom_lines" ]; then
                  has_cdrom=1
                  cdrom_sources+=("$repo_file")
                  echo "  在 $repo_file 中发现CD-ROM源:"
                  echo "$cdrom_lines" | sed 's/^/    /'
                fi
              fi
            done
          fi
        done
        ;;

      "opensuse")
        # 检查 openSUSE 的 zypper 配置
        echo "检查 Zypper 源配置..."

        # 使用 zypper 命令检查源
        if command -v zypper >/dev/null 2>&1; then
          local zypper_output=$(zypper lr -u 2>/dev/null | grep -i "cd\|dvd\|file://")
          if [ -n "$zypper_output" ]; then
            has_cdrom=1
            echo "  发现CD/DVD源:"
            echo "$zypper_output" | sed 's/^/    /'
          fi
        fi

        # 检查配置文件
        if [ -d "/etc/zypp/repos.d" ]; then
          for repo_file in /etc/zypp/repos.d/*.repo; do
            if [ -f "$repo_file" ]; then
              local cdrom_lines=$(grep -n "file://\|cd:\|dvd:" "$repo_file" 2>/dev/null | grep -v "^#")
              if [ -n "$cdrom_lines" ]; then
                has_cdrom=1
                cdrom_sources+=("$repo_file")
                echo "  在 $repo_file 中发现CD-ROM源:"
                echo "$cdrom_lines" | sed 's/^/    /'
              fi
            fi
          done
        fi
        ;;

      "arch")
        # 检查 Arch Linux 的 pacman 配置
        echo "检查 Pacman 源配置..."
        local pacman_conf="/etc/pacman.conf"
        local mirrorlist="/etc/pacman.d/mirrorlist"

        for conf_file in "$pacman_conf" "$mirrorlist"; do
          if [ -f "$conf_file" ]; then
            echo "检查文件: $conf_file"
            local cdrom_lines=$(grep -n "file://\|/media\|/mnt/cdrom" "$conf_file" 2>/dev/null | grep -v "^#")
            if [ -n "$cdrom_lines" ]; then
              has_cdrom=1
              cdrom_sources+=("$conf_file")
              echo "  发现本地/CD-ROM源:"
              echo "$cdrom_lines" | sed 's/^/    /'
            fi
          fi
        done
        ;;
    esac

    echo "----------------------------------------"

    # 输出结果
    if [ $has_cdrom -eq 1 ]; then
      echo "结果: 发现CD-ROM/本地源配置 ❌"
      echo "包含CD-ROM源的文件:"
      printf '%s\n' "${cdrom_sources[@]}" | sed 's/^/  - /'
      echo ""
      echo "建议: 请更新包管理器配置，移除CD-ROM源并添加网络源"

      # 提供修复建议
      case "$DISTRO_OSTYPE" in
        "rhel")
          echo "修复建议:"
          echo "  禁用或删除包含file://的仓库配置"
          echo "  使用官方网络仓库"
          ;;
        "opensuse")
          echo "修复命令示例:"
          echo "  sudo zypper rr <cdrom-repo-name>"
          echo "  sudo zypper ar <network-repo-url> <repo-name>"
          ;;
        "arch")
          echo "修复建议:"
          echo "  编辑 /etc/pacman.d/mirrorlist 使用网络镜像"
          echo "  sudo pacman -Sy"
          ;;
      esac

      return 1
    else
      echo "结果: 未发现CD-ROM/本地源配置 ✅"
      echo "包管理器配置正常，使用网络源"
      return 0
    fi
  }

  # 改cdrom为标准包管理器
  init_sources_list() {
    local sources_file="/etc/apt/sources.list"
    if grep -q "^deb cdrom:" "$sources_file"; then
      info "$1" "$DISTRO_OSTYPE"
      file_backup_sj "$sources_file"
      cat >/tmp/sources.list <<EOF
deb http://deb.debian.org/debian $DISTRO_CODENAME main contrib non-free non-free-firmware
deb http://deb.debian.org/debian $DISTRO_CODENAME-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security $DISTRO_CODENAME-security main contrib non-free non-free-firmware
EOF
      $SUDO_CMD mv /tmp/sources.list "$sources_file"
      $SUDO_CMD chmod 644 "$sources_file"
    fi
  }

fi
