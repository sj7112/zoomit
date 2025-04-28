## zoomIT

A quick/rapid deployment toolkit for newly installed Linux systems

---
/my_shell_project/
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
