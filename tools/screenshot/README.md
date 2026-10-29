# 无头截图（入口指引）

完整说明在 [docs/screenshot-guide.md](../../docs/screenshot-guide.md)，脚本是同目录的 `shoot.mjs`。

要点：Chrome 必须带 `--no-crashpad --disable-breakpad --disable-crash-reporter` 起，并且需要一次放宽沙箱权限；
参数全走环境变量（`SP_TOKEN` / `SP_PAGES` / `SP_WIDTH` / `SP_HEIGHT` / `SP_CLIP` / `SP_CDP_PORT` / `SP_WAIT`）。
