# zoomit
A quick/rapid deployment toolkit for newly installed Linux systems

- bash 4.2+
- python 3.10+
- UTF-8

---
~/zoomit-main/
│── bin/ # Executable scripts (main program)
│ ├── init.sh # Entry script (main program)
│ ├── backup.sh # Backup script
│ ├── deploy.sh # Deployment script
│── lib/ # Functional modules (library files)
│ ├── err_handler.sh # Error handling module
│ ├── utils.sh # General utility functions
│ ├── network.sh # Network-related operations
│── config/ # Configuration files
│ ├── app.conf # Main application configuration
│ ├── db.conf # Database configuration
│── logs/ # Log directory
│ ├── error.log # Error log
│ ├── access.log # Access log
│── tmp/ # Temporary files
│── README.md # Documentation


(1) Precondition:

new installation of linux server
- debian
- ubuntu
- centos
- rhel
- opensuse
- arch


(2) Users requirement:

root

user with sudo authority


(3) Deployment:

- cd ~
- wget -O main.tar.gz https://github.com/sj7112/zoomit/archive/refs/heads/main.tar.gz
   (or manully copy to home directory!)
- tar -zxf main.tar.gz
- zoomit-main/bin/init_main.sh


(4) Features:
- fix_shell_locale - reset language if needed
- install_py_venv  - create venv (if there's no python env. auto install standalone version)
- install_pip      - choose the fastest mirror, configure pip
- update_source    - choose the fastest mirror, configure package management



Still under development!!!
