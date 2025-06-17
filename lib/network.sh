#!/bin/bash

# Load once only
if [[ -z "${LOADED_NETWORK:-}" ]]; then
  LOADED_NETWORK=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry

  LOG_FILE="/var/log/sj_install.log"

  # ==============================================================================
  # 是否需要固定IP
  # 参数：
  #   $1 - 包含多个镜像URL的字符串（空格/换行分隔）
  # 返回值：
  #   通过标准输出返回延迟最低的10个HTTP镜像URL，每行一个
  # ==============================================================================
  need_fix_ip() {
    # 初始化全局变量
    init_env_py "$(sh_check_ip)" "network" # 调用 sh_check_ip 函数

    # 云服务器无需设置固定IP
    if [[ -n ${ENV_NETWORK["IS_CLOUD"]} ]]; then
      info "${ENV_NETWORK["IS_CLOUD"]} 云服务器无需设置固定IP"
      return 1
    fi

    # 根据不同情况设置提示信息
    if [[ -n ${ENV_NETWORK["STATIC_IP"]} ]]; then
      prompt="检测到服务器已配置静态IP，是否调整IP？"
    elif [[ ${ENV_NETWORK["DHCP_CLIENT"]} == true ]]; then
      prompt="检测到服务器使用动态IP，是否改为静态IP？"
    else
      prompt="检测到服务器可能使用静态IP，是否调整IP？"
    fi

    # 提示用户是否要改IP配置
    if ! confirm_action "$prompt"; then
      info "用户选择不修改网络配置"
      return 1
    fi

    # 提示用户输入静态IP地址的最后一段
    local default_last_octet=$(echo "${ENV_NETWORK["CURR_IP"]}" | awk -F. '{print $NF}')
    local new_last_octet=""

    while true; do
      echo -n "请输入静态IP地址的最后一段 (1-255) [默认: $default_last_octet]: "
      read -r new_last_octet

      # 如果用户直接按回车，使用默认值
      if [[ -z "$new_last_octet" ]]; then
        new_last_octet="$default_last_octet"
      fi

      # 检查输入是否为有效数字且在范围内
      if ! [[ "$new_last_octet" =~ ^[0-9]+$ ]] || ((new_last_octet < 1 || new_last_octet > 255)); then
        echo "输入无效，请重写输入"
        continue
      fi

      # 检查是否与网关冲突
      gateway_last_octet=$(echo "${ENV_NETWORK["GATEWAY"]}" | awk -F. '{print $NF}')
      if [[ "$new_last_octet" == "$gateway_last_octet" ]]; then
        echo "输入的静态IP地址不能与网关相同，请重新输入"
        continue
      fi

      # 构造新的静态IP地址
      ENV_NETWORK[STATIC_IP]="$(awk -F. '{print $1"."$2"."$3}' <<<"${ENV_NETWORK["CURR_IP"]}").${new_last_octet}"
      ENV_NETWORK[HAS_STATIC]="pending" # 待生效

      return 0
    done

  }

  # ==============================================================================
  # 计数器函数
  # ==============================================================================
  count_down() {
    # 设置环境变量
    local duration=5
    local IFACE="${ENV_NETWORK["MAIN_IFACE"]}"
    local IP_ADDR="${ENV_NETWORK["STATIC_IP"]}"

    # ANSI 颜色
    local BG_BLUE="\033[44m"
    local NC="\033[0m" # 重置颜色

    info "${duration}秒后修改网络配置：$IP_ADDR (接口 $IFACE)，请准备好重连。按 Ctrl+C 取消"

    for i in $(seq "$duration" -1 1); do
      echo -ne "${BG_BLUE}  $i 秒 ${NC}\r"
      sleep 0.5
    done
    echo -e "${BG_BLUE}  0 秒 ${NC}"
  }

  # ==============================================================================
  # 配置静态IP（NetworkManager）
  # ==============================================================================
  config_nmcli() {
    # 检查 nmcli 是否存在
    if ! command -v nmcli &>/dev/null; then
      exiterr "错误：nmcli 未安装或不可用，请先安装 NetworkManager 命令行工具"
    fi

    # 设置环境变量
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # 网络接口名
    CON_NAME="static-$IFACE"              # 连接名称，NetworkManager 中标识配置的名字
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP 地址（不含掩码）
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # 子网掩码长度，默认24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # 网关
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS 服务器，多个用空格隔开

    # 1. 查看连接是否存在，不存在则创建
    if ! $SUDO_CMD nmcli connection show "$CON_NAME" &>/dev/null; then
      $SUDO_CMD nmcli connection add type ethernet ifname "$IFACE" con-name "$CON_NAME"
    fi

    # 2. 修改连接为静态 IP
    $SUDO_CMD nmcli connection modify "$CON_NAME" \
      ipv4.addresses "$IP_ADDR/$PREFIX" \
      ipv4.gateway "$GATEWAY" \
      ipv4.dns "$DNS" \
      ipv4.method manual \
      connection.autoconnect yes

    # 3. 激活连接
    count_down # 倒计时提醒
    $SUDO_CMD nmcli connection up "$CON_NAME" || exiterr "连接激活失败，请检查网络并尝试重新连接"

  }

  # ==============================================================================
  # 配置静态IP（例如：/etc/systemd/network/10-ens192.network）
  # ==============================================================================
  setup_systemd_networkd() {
    # 设置环境变量
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # 网络接口名
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP 地址（不含掩码）
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # 子网掩码长度，默认24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # 网关
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS，多个用空格分隔

    # 1. 检查配置文件
    NETDIR="/etc/systemd/network"
    NETFILE="$NETDIR/10-$IFACE.network"
    if [ -f "$NETFILE" ]; then
      $SUDO_CMD cp "$NETFILE" "$NETFILE.$(date +%Y%m%d%H%M%S)"
    else
      $SUDO_CMD mkdir -p "$NETDIR" # 创建目录
    fi

    # 2. 生成配置文件
    $SUDO_CMD cat >"$NETFILE" <<EOF
[Match]
Name=$IFACE

[Network]
Address=$IP_ADDR/$PREFIX
Gateway=$GATEWAY
DNS=$DNS
EOF

  }

  # ==============================================================================
  # 配置切换脚本代码（networking -> systemd-networkd）
  # ==============================================================================
  setup_switch_network() {
    # 创建切换脚本并在后台执行
    $SUDO_CMD cat >/tmp/switch_network.sh <<EOF
#!/bin/bash
exec >> "$LOG_FILE" 2>&1  # add to log data

set -x  # show all commands
echo "=== Switch Network start - \$(date) ==="
$SUDO_CMD systemctl stop networking
$SUDO_CMD systemctl disable networking
$SUDO_CMD systemctl enable systemd-networkd
$SUDO_CMD systemctl start systemd-networkd
echo "=== Switch Network end - \$(date) ==="

# clean up
$SUDO_CMD rm -f /tmp/switch_network.sh
EOF
    $SUDO_CMD chmod +x /tmp/switch_network.sh

  }

  # ==============================================================================
  # 配置静态IP（ifupdown -> systemd_networkd）
  # ==============================================================================
  ifupdown_to_systemd_networkd() {
    # 安装systemd-networkd
    install_base_pkg "systemd" # 安装systemd-networkd

    setup_systemd_networkd # 生成配置文件
    setup_switch_network   # 创建切换脚本

    count_down # 倒计时提醒
    $SUDO_CMD setsid /tmp/switch_network.sh </dev/null &

  }

  # ==============================================================================
  # 配置静态IP（systemd_networkd）
  # ==============================================================================
  config_default() {
    # 检查必要工具和目录
    if ! command -v networkctl &>/dev/null; then
      exiterr "错误：systemd-networkd 未安装或不可用"
    fi

    setup_systemd_networkd # 生成配置文件

    # 重载配置并重启 networkd
    count_down # 倒计时提醒
    if ! $SUDO_CMD systemctl restart systemd-networkd; then
      exiterr "重启 systemd-networkd 失败，请检查配置文件后再试"
    fi

  }

fi
