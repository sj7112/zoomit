#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_INIT_MAIN:-}" ]]; then
  LOADED_INIT_MAIN=1

  LIB_DIR="$(dirname "$BIN_DIR")/lib" # lib direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/cmd_handler.sh"
  source "$LIB_DIR/json_handler.sh"
  source "$LIB_DIR/system.sh"
  source "$LIB_DIR/hash_util.sh"
  source "$LIB_DIR/init_base_func.sh"
  source "$LIB_DIR/python_install.sh"
  source "$LIB_DIR/python_bridge.sh"
  source "$LIB_DIR/source_install.sh"
  source "$LIB_DIR/update_env.sh"
  source "$LIB_DIR/network.sh"
  source "$LIB_DIR/docker.sh"

  # 全局变量
  DISTRO_PM=""       # 包管理器
  DISTRO_OSTYPE=""   # 发行版名称
  DISTRO_CODENAME="" # 发行版代号 | 版本号
  SYSTEM_LANG=""     # 语言代码（默认=en）
  SYSTEM_COUNTRY=""  # 国家代码（默认=CN）
  SUDO_CMD=""        # sudo 默认为空字符串

  # ==============================================================================
  # 兼容：debian | ubuntu | centos | rhel | openSUSE | arch Linux
  # 功能1: 检查root权限并自动升级
  # ==============================================================================

  # 检查当前用户是否为 root（非root检测sudo是否可用）
  check_user_sudo() {
    # 1. 校验非root用户：是否已安装sudo；是否有sudo权限
    if [ "$(id -u)" -ne 0 ]; then
      if ! command -v sudo &>/dev/null; then
        exiterr "无法安装 sudo，请使用 root 账号执行本脚本(su -)，或手动安装 sudo"
      elif ! id -nG | grep -qw "sudo"; then
        exiterr "用户非 sudo 组，请使用 root 账号执行本脚本(su -)，或手动加入 sudo"
      fi
    fi

    # 增加 sudo 命令前缀
    if [ "$(id -u)" -ne 0 ]; then
      SUDO_CMD="sudo"
    fi
  }

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

  # 获取默认语言
  get_default_lang() {
    default_lang=""
    for file in /etc/locale.conf /etc/default/locale /etc/sysconfig/i18n; do
      if [ -f "$file" ]; then
        default_lang=$(grep "^LANG=" "$file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"')
        if [ -n "$default_lang" ]; then
          echo "$default_lang"
          return 0
        fi
      fi
    done

    # Check if the system default language was retrieved
    echo "No default language retrieved. Please enter the language (e.g., en_US.utf8):"
    while true; do
      read -r input_lang

      # Validate the format (e.g., xx_YY.utf8)
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
        echo "Invalid language format. Please re-enter (e.g., en_US.utf8):"
      fi
    done
    echo "$default_lang"
  }

  # 更新或添加 LANG 设置到 ~/.profile
  set_user_lang_profile() {
    local lang="$1" # 目标语言（如 zh_CN.utf8）

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

    # 从 lang 生成 LANGUAGE 值，例如 en_US.utf8 -> en_US:en
    local base_lang="${lang%.*}"       # 移除 .utf8 / .UTF-8
    local short_lang="${base_lang%_*}" # 语言代码
    local language_value="${base_lang}:${short_lang}"
    # 更新或添加 LANGUAGE 设置
    if grep -q "^LANGUAGE=" "$profile_file"; then
      sed -i "s|^LANGUAGE=.*|LANGUAGE=\"$language_value\"|" "$profile_file"
    else
      echo "LANGUAGE=\"$language_value\"" | tee -a "$profile_file" >/dev/null
    fi
    # shellcheck disable=SC1090
    source "$profile_file" # 重新加载配置文件
    return 0
  }

  # 更新或添加 LANG 设置
  set_user_lang_sh() {
    local config_file="$1"
    local lang="$2" # 目标语言（如 en_US.utf8）

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

    # 从 lang 生成 LANGUAGE 值，例如 en_US.utf8 -> en_US:en
    local base_lang="${lang%.*}"       # 移除 .utf8 / .UTF-8
    local short_lang="${base_lang%_*}" # 语言代码
    local language_value="${base_lang}:${short_lang}"
    # 更新或添加 LANGUAGE 设置
    local export_line="export LANGUAGE=\"$language_value\""
    if grep -q "^export LANGUAGE=" "$config_file"; then
      sed -i "s|^export LANGUAGE=.*|$export_line|" "$config_file"
    else
      echo "$export_line" | tee -a "$config_file" >/dev/null
    fi
    # shellcheck disable=SC1090
    source "$config_file" # 重新加载配置文件
    return 0
  }

  # 更新或添加 LANG 设置
  set_user_language() {
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

  # 检查当前用户的语言是否为C或POSIX
  check_user_lang() {
    local sys_lang=$(get_default_lang)    # 系统语言设置
    local curr_lang=${LC_ALL:-${LANG:-C}} # 当前用户语言设置
    if [ "${curr_lang,,}" != "${sys_lang,,}" ]; then
      if confirm_action "Set default language as $sys_lang？"; then
        set_user_language "$sys_lang" # 设置用户语言
      else
        export LANG="en_US.utf8"
        export LANGUAGE="en_US:en"
      fi
    fi
    SYSTEM_LANG=${LANG%.*}           # 获取系统语言代码
    SYSTEM_COUNTRY=${SYSTEM_LANG#*_} # 取下划线后的部分，比如 CN
    info "User default language: $sys_lang"
  }

  # ==============================================================================
  # 函数: initial_env 检查root权限和sudo
  # @i18n: This function needs internationalization
  # ==============================================================================
  initial_env() {
    # 1. 检查当前用户是否为 root（非root检测sudo是否可用）
    check_user_sudo

    # 2. 检查并安装 Python3 虚拟环境
    install_py_venv

    # 3. 检查并调整当前用户的语言设置
    check_user_lang

    # 4. 选择包管理器
    sh_update_source # 选择包管理器（内有交互）
    exiterr "请手动修改软件源后再运行" "$DISTRO_OSTYPE" \
      "如果需要，请手动修改软件源列表 /etc/apt/sources.list 或 /etc/yum.repos.d/*.repo"

    # local sources_file=$(get_source_list)
    local prompt
    if check_cdrom; then
      prompt=$(string "检测到 CD-ROM 作为软件源，是否重新选择软件源？")
      if ! confirm_action "$prompt"; then exiterr "请手动修改软件源后再运行"; fi
    else
      prompt=$(string "是否重新选择软件源？")
      if ! confirm_action "$prompt"; then return 1; fi
    fi

    # if [[ "$DISTRO_PM" == "apt" ]]; then
    #   init_sources_list "$prompt"
    # elif [[ "$DISTRO_PM" == "dnf" || "$DISTRO_PM" == "yum" ]]; then
    #   init_sources_list "检测到 CD-ROM 作为软件源，修改为默认 {0} 官方源..." "$DISTRO_OSTYPE"
    #   select_mirror # 选择速度快的镜像(内有交互)
    # elif [[ "$DISTRO_PM" == "zypper" ]]; then
    #   init_sources_list "检测到 CD-ROM 作为软件源，修改为默认 {0} 官方源..." "$DISTRO_OSTYPE"
    #   select_mirror # 选择速度快的镜像(内有交互)
    # elif [[ "$DISTRO_PM" == "pacman" ]]; then
    #   init_sources_list "检测到 CD-ROM 作为软件源，修改为默认 {0} 官方源..." "$DISTRO_OSTYPE"
    #   select_mirror # 选择速度快的镜像(内有交互)
    # fi

    init_sources_list "检测到 CD-ROM 作为软件源，修改为默认 {0} 官方源..."
    select_mirror # 选择速度快的镜像(内有交互)

    info "[1/1] 系统升级开始..."
    clean_pkg_mgr   # 清理缓存
    update_pkg_mgr  # 更新镜像源列表
    upgrade_pkg_mgr # 升级已安装的软件包
    remove_pkg_mgr  # 删除不再需要的依赖包
    success "[1/2] 系统升级完成..."

    # 5. 安装各类基础包
    info "[1/3] 检查系统环境..."
    install_base_pkg "sudo"
    install_base_pkg "curl"
    install_base_pkg "jq"
    install_base_pkg "make"

    # 6. 加载json环境变量；初始化语言和国家代码变量
    META_Command=$(json_load_data "cmd_meta") # 命令解析json

  }

  # ==============================================================================
  # 功能2: 配置SSH（适用于所有发行版本）
  # 函数: config_sshd
  # 作用: 检查并安装 sshd，交互式修改 SSH 端口和 root 登录权限
  # 参数: 无
  # 返回值: 无 (直接修改 /etc/ssh/sshd_config 并重启 sshd)
  # ==============================================================================
  config_sshd() {
    local sshd_config="/etc/ssh/sshd_config"

    # 检查是否安装 sshd
    if ! command -v sshd &>/dev/null; then
      info "sshd 未安装，正在安装..."
      $SUDO_CMD apt-get update && $SUDO_CMD apt-get install -y openssh-server || exiterr "安装 sshd 失败"
    fi

    # 询问 SSH 端口
    curr_ssh_port=$(grep -oP '^Port \K\d+' "$sshd_config" || echo 22)
    read -p "$(string "输入新的SSH端口 (当前: {0}) : " $curr_ssh_port)" ssh_port
    if [[ "$ssh_port" =~ ^[0-9]+$ && "$ssh_port" -le 65535 ]]; then
      $SUDO_CMD sed -i "s/^#*Port .*/Port $ssh_port/" "$sshd_config"
      info "已设置SSH端口: {0}" "$ssh_port"
    else
      info "无效端口，保持默认: $curr_ssh_port" >&2
    fi

    # 询问是否允许 root 登录
    #PermitRootLogin prohibit-password
    read -rp "允许 root 远程登录？[y/N]: " allow_root
    case "$allow_root" in
      [Yy]) fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin yes" && info "已允许 root 登录" ;;
      [Nn] | "") fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin no" && info "已禁止 root 登录" ;;
    esac

    # 重启 SSH 服务
    $SUDO_CMD systemctl restart sshd && info "SSH 配置已应用"
  }

  # --------------------------
  # 功能3: 配置静态IP
  # --------------------------
  configure_ip() {
    # 设置环境配置文件
    if ! need_fix_ip; then
      return 0
    fi
    if [[ ${ENV_NETWORK["CURR_NM"]} == "NetworkManager" ]]; then
      info "NetworkManager 正在运行"
      config_nmcli
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "networking" ]]; then
      info "ifupdown 正在运行"
      ifupdown_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "wicked" ]]; then
      info "wicked 正在运行"
      # wicked_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "network" ]]; then
      info "network-scripts 正在运行"
      # network_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "systemd-networkd" ]]; then
      info "systemd-networkd 正在运行"
      config_default
    else
      exiterr "未知网络管理器，无法配置静态IP"
    fi

  }

  install_docker() {
    info "在 $DISTRO 上安装 Docker 与 Docker Compose..."

    # 安装依赖
    install_base_pkg "ca-certificates"
    install_base_pkg "gnupg"

    apt-get update
    apt-get install -y \
      ca-certificates \
      curl \
      gnupg \
      lsb-release \
      apt-transport-https

    # 添加 Docker 仓库 GPG（可选，但推荐）
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$DISTRO/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # 添加 Docker 仓库源
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$DISTRO \
      $(lsb_release -cs) stable" >/etc/apt/sources.list.d/docker.list

    # 安装 Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # 验证安装
    docker --version
    docker compose version
  }

  # --------------------------
  # 功能2: 安装指定软件
  # --------------------------
  docker_compose() {
    install_docker
    infra_setup
    apps_setup
  }

  # ==============================================================================
  # 公共初始化子函数（兼容：debian | ubuntu | centos | rhel | openSUSE | arch Linux）
  # ==============================================================================
  init_main() {
    # ** 环境变量：包管理器 | 操作系统名称 **
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      case "$ID" in
        debian)
          DISTRO_OSTYPE="debian"
          DISTRO_PM="apt" # Debian | Ubuntu
          ;;
        ubuntu)
          DISTRO_OSTYPE="ubuntu"
          DISTRO_PM="apt" # Debian | Ubuntu
          ;;
        centos)
          DISTRO_OSTYPE="centos"
          DISTRO_PM="yum" # CentOS
          ;;
        rhel)
          DISTRO_OSTYPE="rhel"
          DISTRO_PM="dnf" # RHEL
          ;;
        opensuse* | suse)
          DISTRO_OSTYPE="opensuse"
          DISTRO_PM="zypper" # openSUSE
          ;;
        arch)
          DISTRO_OSTYPE="arch"
          DISTRO_PM="pacman" # Arch
          ;;
        *)
          exiterr "Unsupported distribution: $ID ($PRETTY_NAME)"
          ;;
      esac
    else
      exiterr "Unable to detect Linux distribution, cannot proceed"
    fi

    # ** 环境变量：发行版代号 | 版本号 **
    if [ -f /etc/os-release ]; then
      DISTRO_CODENAME=$(grep "^VERSION_CODENAME=" /etc/os-release | cut -d'=' -f2 || true)

      # 部分发行版如没有VERSION_CODENAME
      if [ -z "$DISTRO_CODENAME" ]; then
        # Rocky Linux、AlmaLinux 等用版本号替代
        DISTRO_CODENAME=$(grep "^VERSION_ID=" /etc/os-release | cut -d= -f2 | tr -d '"' || true)
        case "$DISTRO_OSTYPE" in
          centos)
            # CentOS 6/7 特判
            if [[ "$DISTRO_CODENAME" = "6" || "$DISTRO_CODENAME" = "7" ]]; then
              DISTRO_CODENAME=$(sed 's/.*release \([0-9.]*\) .*/\1/' /etc/centos-release)
            fi
            ;;
          arch)
            # Arch无代号
            DISTRO_CODENAME="arch"
            ;;
        esac
      fi
    elif command -v lsb_release &>/dev/null; then
      DISTRO_CODENAME=$(lsb_release -c | awk '{print $2}' || true)
    else
      DISTRO_CODENAME="unknown"
    fi

    echo "=== init system start ($PRETTY_NAME) ==="
    initial_env # 基础值初始化
    # config_sshd # SSH配置
    configure_ip   # 静态IP配置
    docker_compose # 安装软件
    # system_config
    echo "=== init system end ($PRETTY_NAME) ==="
  }
fi
