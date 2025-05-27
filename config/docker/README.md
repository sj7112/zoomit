# docker filepath
file structure for docker related files

---
/opt/docker/
├── infra/                  # 基础设施
│   ├── compose.yml
│   └── .env
── apps/                     # 应用系统
│   ├── compose.yml
│   └── .env
├── monitoring/              # 监控栈
│   ├── compose.yml
│   └── .env
├── volumes/                 # 持久化数据
│   ├── mysql-data/
│   ├── redis-data/
│   ├── affine-data/
│   ├── nextcloud-data/
│   ├── nginx-logs/
│   ├── prometheus-logs/
│   ├── grafana-logs/
│   ├── alertmanager-logs/
│   └── ....../
├── logs/                 # 日志数据
│   ├── mysql/
│   ├── redis/
│   ├── affine/
│   ├── nextcloud/
│   ├── nginx/
│   └── ....../
├── configs/                 # 配置文件集中管理
│   ├── nginx/
│   │   ├── nginx.conf
│   │   ├── sites-enabled/
│   │   └── ssl/
│   ├── mysql/
│   │   ├── my.cnf
│   │   └── init-scripts/
│   └── shared/
│       ├── ssl-certs/
│       └── secrets/
├── scripts/                 # 运维脚本
│   ├── deploy.sh
│   ├── backup.sh
│   ├── health-check.sh
│   └── log-rotate.sh
└── docs/                   # 文档和映射关系
    ├── README.md
    ├── service-mapping.md
    └── troubleshooting.md
