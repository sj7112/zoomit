# zoomit
A quick/rapid deployment toolkit for newly installed Linux systems

bash 4.2+
python 3.10+
UTF-8

---
~/zoomit-main/
│── bin/ # 可执行脚本（主程序）
│ ├── init.sh # 入口脚本（主程序）
│ ├── backup.sh # 备份脚本
│ ├── deploy.sh # 部署脚本
│── lib/ # 功能模块（库文件）
│ ├── err_handler.sh # 错误处理模块
│ ├── utils.sh # 通用工具函数
│ ├── network.sh # 网络相关操作
│── config/ # 配置文件
│ ├── app.conf # 主要应用配置
│ ├── db.conf # 数据库配置
│── logs/ # 日志目录
│ ├── error.log # 错误日志
│ ├── access.log # 访问日志
│── tmp/ # 临时文件
│── README.md # 说明文档


(1) Precondition:

new installation of linux server
debian
ubuntu
centos
rhel
opensuse
arch


(2) Users requirement:

root
user with sudo authority


(3) Deployment:

cd ~
wget -O main.tar.gz https://github.com/sj7112/zoomit/archive/refs/heads/main.tar.gz
   (or manully copy to home directory!)
tar -zxf main.tar.gz
zoomit-main/bin/init_main.sh


(4) Features:
  fix_shell_locale - reset language if needed
  install_py_venv  - create venv (if there's no python env. auto install standalone version)
  install_pip      - choose the fastest mirror, configure pip
  update_source    - choose the fastest mirror, configure package management



Still under development!!!
