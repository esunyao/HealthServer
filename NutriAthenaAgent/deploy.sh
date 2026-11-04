#!/bin/sh
# Run from any directory; keep .env outside the managed sparse checkout.
set -eu

deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$deploy_dir/.source"
env_file="$deploy_dir/.env"
repo_url=https://github.com/esunyao/HealthServer.git

if [ ! -f "$env_file" ]; then
    printf '%s\n' "请先在 $deploy_dir/.env 配置数据库、OAuth、模型与 HEALTHSERVER_DOCKER_NETWORK。" >&2
    exit 1
fi

if [ ! -e "$source_dir" ]; then
    git clone --filter=blob:none --no-checkout --depth=1 --branch master "$repo_url" "$source_dir"
    git -C "$source_dir" sparse-checkout set --no-cone '/NutriAthenaAgent/'
    git -C "$source_dir" checkout --detach origin/master
else
    if [ ! -d "$source_dir/.git" ] || [ "$(git -C "$source_dir" remote get-url origin)" != "$repo_url" ]; then
        printf '%s\n' "已有 .source 不是本脚本使用的 HealthServer 仓库，请检查后再运行。" >&2
        exit 1
    fi
    if [ -n "$(git -C "$source_dir" status --porcelain --untracked-files=normal)" ]; then
        printf '%s\n' "已有 .source 含未提交的修改，请先处理；脚本不会覆盖这些文件。" >&2
        exit 1
    fi
    git -C "$source_dir" fetch --depth=1 origin master
    git -C "$source_dir" checkout --detach FETCH_HEAD
fi

printf '正在部署 Git 提交：%s\n' "$(git -C "$source_dir" rev-parse HEAD)"
export NUTRIATHENA_ENV_FILE="$env_file"
docker compose --project-name nutriathena-agent --env-file "$env_file" \
    -f "$source_dir/NutriAthenaAgent/docker-compose.yaml" up -d --build
