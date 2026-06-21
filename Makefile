# R001-DEP01：本地开发编排 Makefile
#
# 设计：
# - `up`：启动宿主 adb server（默认 5037 端口），如有 Android 模拟器尝试启动，
#         然后 docker compose up -d（postgres + agent + frontend）
# - `down`：docker compose down（保留 volume）
# - `logs`：实时跟踪三容器日志
# - `migrate`：占位，待 INF05/Alembic 落地后接入
# - `test`：在 agent 容器内运行 pytest
# - `shell`：进入 agent 容器 bash
# - `adb-devices`：验证容器内 adb 能经 host.docker.internal 连到宿主 adb server
#
# 说明：
# - 宿主 adb server 必须监听 TCP（adb start-server 默认就是 TCP 5037）
# - 模拟器启动：仅当环境变量 EMULATOR_NAME 存在时才尝试 emulator 命令
#   （CI 环境可能无 emulator，直接跳过）

.PHONY: up down logs migrate test shell adb-devices ps clean rebuild

# 默认目标
.DEFAULT_GOAL := help

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## 启动 adb server + 模拟器（宿主）+ 三容器
	@echo "==> [host] starting adb server on tcp:5037"
	@adb start-server 2>/dev/null || { \
		echo "WARN: adb not found on host, skip (agent container has its own adb)"; \
	}
	@if [ -n "$$EMULATOR_NAME" ]; then \
		echo "==> [host] launching emulator: $$EMULATOR_NAME"; \
		($$ANDROID_HOME/emulator/emulator -avd $$EMULATOR_NAME -no-audio -no-window &); \
	else \
		echo "==> [host] EMULATOR_NAME not set, skip emulator launch"; \
	fi
	@echo "==> docker compose up -d"
	docker compose up -d
	@echo "==> done. agent: http://localhost:8000/health"

down: ## 停止三容器（保留 volume）
	docker compose down

logs: ## 跟踪三容器日志
	docker compose logs -f

ps: ## 显示容器状态
	docker compose ps

migrate: ## 运行数据库迁移（占位：待 Alembic 接入）
	@echo "TODO: alembic not wired yet (R001-DEP01 placeholder)"
	docker compose exec agent python3 -c "from agent.infra.db import Base, engine, init_vector_extension; init_vector_extension(engine); Base.metadata.create_all(bind=engine); print('DB schema synced')"

test: ## 在 agent 容器内运行单元测试
	docker compose exec agent python3 -m pytest tests/ -q

shell: ## 进入 agent 容器 bash
	docker compose exec agent bash

adb-devices: ## 验证容器内 adb 能连宿主 adb server（D10）
	@echo "==> verifying adb bridge (host.docker.internal:5037)"
	docker compose exec agent adb -H host.docker.internal -P 5037 devices

clean: ## 停止并删除容器 + volume（慎用）
	docker compose down -v

rebuild: ## 重建 agent 镜像（依赖变动后）
	docker compose build --no-cache agent
	docker compose up -d --force-recreate agent
