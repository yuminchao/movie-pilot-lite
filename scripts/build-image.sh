#!/usr/bin/env bash
set -euo pipefail

tag="movie-pilot-lite:latest"
platform=""
push=false
no_cache=false

usage() {
  cat <<'EOF'
用法:
  ./scripts/build-image.sh [选项]

选项:
  --tag <name:tag>       镜像标签，默认 movie-pilot-lite:latest
  --platform <platform> 目标平台，例如 linux/amd64 或 linux/amd64,linux/arm64
  --push                 构建后推送镜像；默认将镜像加载到本地 Docker
  --no-cache             禁用 Docker 构建缓存
  -h, --help             显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      [[ $# -ge 2 ]] || { echo "--tag 缺少值" >&2; exit 2; }
      tag="$2"
      shift 2
      ;;
    --platform)
      [[ $# -ge 2 ]] || { echo "--platform 缺少值" >&2; exit 2; }
      platform="$2"
      shift 2
      ;;
    --push)
      push=true
      shift
      ;;
    --no-cache)
      no_cache=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$platform" == *,* && "$push" != true ]]; then
  echo "Multi-platform builds require --push because Docker cannot --load a multi-platform image." >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  echo "未找到 docker 命令，请先安装 Docker Engine 或 Docker Desktop。" >&2
  exit 1
}

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$project_root/Dockerfile" ]] || {
  echo "项目根目录缺少 Dockerfile：$project_root/Dockerfile" >&2
  exit 1
}

args=(buildx build --file "$project_root/Dockerfile" --tag "$tag")
[[ -n "$platform" ]] && args+=(--platform "$platform")
$no_cache && args+=(--no-cache)
$push && args+=(--push) || args+=(--load)
args+=("$project_root")

echo "开始构建镜像：$tag"
[[ -n "$platform" ]] && echo "目标平台：$platform"
$push && echo "构建完成后推送到镜像仓库"
docker "${args[@]}"
echo "镜像构建完成：$tag"
