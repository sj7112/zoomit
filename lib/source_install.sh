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
    local distro=""
    local has_cdrom=0
    local cdrom_sources=()

    # 检测发行版
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      case "$ID" in
        debian | ubuntu)
          distro="debian"
          ;;
        centos | rhel | fedora)
          distro="rhel"
          ;;
        opensuse* | suse)
          distro="opensuse"
          ;;
        arch)
          distro="arch"
          ;;
        *)
          echo "不支持的发行版: $ID"
          return 1
          ;;
      esac
    else
      echo "无法检测发行版"
      return 1
    fi

    echo "检测到发行版: $distro ($PRETTY_NAME)"
    echo "----------------------------------------"

    case "$DISTRO_OSTYPE" in
      "debian")
        # 检查 Debian/Ubuntu 的 sources.list
        local sources_files=(
          "/etc/apt/sources.list"
          "/etc/apt/sources.list.d/*.list"
        )

        echo "检查 APT 源配置..."
        for file_pattern in "${sources_files[@]}"; do
          for file in $file_pattern; do
            if [ -f "$file" ]; then
              echo "检查文件: $file"
              # 查找包含 cdrom 的行
              local cdrom_lines=$(grep -n "cdrom\|cd-rom\|file:///media" "$file" 2>/dev/null | grep -v "^#")
              if [ -n "$cdrom_lines" ]; then
                has_cdrom=1
                cdrom_sources+=("$file")
                echo "  发现CD-ROM源:"
                echo "$cdrom_lines" | sed 's/^/    /'
              fi
            fi
          done
        done
        ;;

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
      case "$distro" in
        "debian")
          echo "修复命令示例:"
          echo "  sudo sed -i 's/^deb cdrom/#&/' /etc/apt/sources.list"
          echo "  sudo apt update"
          ;;
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

  # 检测系统架构和发行版
  detect_system() {
    local arch=$(uname -m) # 检测架构
    case "$arch" in
      x86_64) arch="x86_64" ;;
      aarch64 | arm64) arch="aarch64" ;;
      armv7l) arch="armv7" ;;
      *) exiterr "不支持的架构: $arch" ;;
    esac

    echo "$arch-linux" # 不考虑linux-musl
  }

  # 获取 Python standalone 下载 URL
  get_python_url() {
    local system_type="$1"

    # 根据系统类型选择合适的构建
    case "$system_type" in
      x86_64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-x86_64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      aarch64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-aarch64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      *)
        exiterr "不支持的系统类型: $system_type"
        ;;
    esac
  }

  # 下载并安装 Python standalone
  install_python_standalone() {
    local system_type=$(detect_system)
    local python_url=$(get_python_url "$system_type")

    info "下载 Python $PY_VERSION standalone..."
    info "下载地址: $python_url"

    # 下载文件（支持断点续传）
    echo "wget -c -q --show-progress -O $PY_GZ_FILE $python_url"
    wget -c -q --show-progress -O "$PY_GZ_FILE" "$python_url"

    # 解压到安装目录
    info "安装 Python 到 $PY_INST_DIR..."
    mkdir -p "$PY_INST_DIR" # 确保安装目录存在
    if ! tar -xf "$PY_GZ_FILE" -C "$PY_INST_DIR" --strip-components=1; then
      exiterr "解压安装失败"
    fi

    # 清理临时文件
    PY_BIN="$PY_INST_DIR/bin/python3"
    info "Python $PY_VERSION 安装完成！"
  }

  # 验证 Python 安装
  verify_python() {
    local python_bin="$PY_INST_DIR/bin/python3"

    if [[ ! -x "$python_bin" ]]; then
      exiterr "Python 安装验证失败: $python_bin 不存在或不可执行"
    fi

    local inst_version=$("$python_bin" --version 2>&1 | awk '{print $2}')
    if [[ "$inst_version" != "$PY_VERSION" ]]; then
      exiterr "版本不匹配: 期望 $PY_VERSION, 实际 $inst_version"
    fi

    info "Python 验证成功: $inst_version"
  }

  # 创建虚拟环境并安装常用包
  create_venv_with_packages() {
    info "创建虚拟环境 $VENV_DIR..."

    # 删除已存在的虚拟环境
    if [[ -d "$VENV_DIR" ]]; then
      if confirm_action "虚拟环境 $VENV_DIR 已存在，是否删除重建？"; then
        rm -rf "$VENV_DIR"
      else
        warning "跳过虚拟环境创建"
        return
      fi
    fi

    # 创建虚拟环境
    if "$PY_BIN" -m venv "$VENV_DIR"; then
      sh_install_pip # 激活虚拟环境并安装所需的基础包
      success "虚拟环境创建成功！"
    else
      exiterr "创建虚拟环境失败"
    fi
  }

  # 安装 Python 并创建虚拟环境
  install_py_venv() {
    # 检查是否需要重新安装 Python
    if ! check_existing_python; then
      install_python_standalone
      verify_python
    fi

    # 创建虚拟环境并安装包
    create_venv_with_packages
  }

  # ==============================================================================
  # 主程序（用于测试）
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    if [[ "$DEBUG" == "1" ]]; then
      # set -x          # 启用命令追踪
      set -e          # 启用脚本错误即退出
      set -u          # 启用未定义变量报错
      set -o pipefail # 启用管道失败时退出
    else
      set +x          # 关闭命令追踪
      set -e          # 确保遇到错误退出
      set -u          # 确保未定义变量时报错
      set -o pipefail # 确保管道中的命令失败会导致脚本退出
    fi

    # 主函数
    main() {
      info "Python $PY_VERSION Standalone 自动安装脚本"
      install_py_venv
    }

    # 执行主函数
    main "$@"
  fi

fi
