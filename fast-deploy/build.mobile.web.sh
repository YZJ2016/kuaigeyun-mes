#!/usr/bin/env bash
# 把本机 HBuilderX 已发行的 uni-app x Web 复制到 Caddy /mobile 的部署目录。
# 不执行 npm run build。uni-app x 不支持用 cli/npm 创建工程，也没有等价的 npm build:h5。
# 发行产物默认在工程下的 unpackage/dist/build/web。官方：
# https://uniapp.dcloud.net.cn/matter.html
# 「在当下项目下的 unpackage/dist/build/web 目录找到出的资源，部署服务器」
# uni-app x 说明见 https://doc.dcloud.net.cn/uni-app-x/project.html 与
# https://doc.dcloud.net.cn/uni-app-x/worktile/
#
# Usage: ./fast-deploy/build.mobile.web.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if [ -f "$MOBILE_H5_PUBLISH_DIR/index.html" ]; then
    copy_mobile_h5_publish_to_web_dir "$MOBILE_H5_PUBLISH_DIR"
    exit $?
fi

log_warn "未找到 $MOBILE_H5_PUBLISH_DIR/index.html"
log_warn "请先在本机用 HBuilderX 打开 $MOBILE_APP_DIR ，用菜单「发行」发布 Web。没有发行产物时只保留 /mobile 占位页。"
write_mobile_web_dist_placeholder
exit 0
