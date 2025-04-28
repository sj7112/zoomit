# ------ 基础配置 ------
SHELL := /bin/bash   # 指定 Shell 解释器
.DEFAULT_GOAL := help

# ------ 路径定义 ------
BIN_DIR := bin
LIB_DIR := lib
TEST_DIR := tests

# ------ 工具检查 ------
SHFMT := $(shell command -v shfmt 2>/dev/null)
SHELLCHECK := $(shell command -v shellcheck 2>/dev/null)

# ------ 主规则 ------
.PHONY: help
help:  ## 显示帮助信息
	@echo "可用命令:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: test
test: check-tools  ## 运行所有测试
	@echo "运行单元测试..."
	@bats $(TEST_DIR)/unit
	@echo "运行集成测试..."
	@bats $(TEST_DIR)/integration

.PHONY: deploy
deploy: check-env  ## 部署到生产环境
	@$(BIN_DIR)/deploy --env=prod

.PHONY: install
install:  ## 安装到系统路径（需sudo）
	@sudo cp $(BIN_DIR)/* /usr/local/bin/
	@echo "安装完成！"

# ------ 辅助规则 ------
.PHONY: check-tools
check-tools:  ## 检查依赖工具
ifndef SHFMT
	$(error "缺少 shfmt，请运行: brew install shfmt")
endif
ifndef SHELLCHECK
	$(error "缺少 shellcheck，请运行: brew install shellcheck")
endif

.PHONY: check-env
check-env:  ## 检查环境变量
ifndef DEPLOY_KEY
	$(error "需设置 DEPLOY_KEY 环境变量")
endif

.PHONY: clean
clean:  ## 清理临时文件
	@rm -rf ./tmp