# 03. 自动同步与仪表板

> 可选增强：不完成本章，也不影响手动下载录像。

完成本章后，Home Assistant 每 6 小时执行一次增量同步，仪表板提供同步、停止和最近六条录像。开始前应已完成 [02. 安装下载器并取得第一条 MP4](02-install-downloader.md)，且 `sensor.cw700s_sync_status` 已出现。

## 配置每 6 小时增量同步

标准 Home Assistant 配置使用 `automation: !include automations.yaml`；这种拆分方式见官方 [Splitting the configuration](https://www.home-assistant.io/docs/configuration/splitting_configuration)。先备份 `/config/automations.yaml`：

```bash
test ! -e /config/automations.yaml.before_github_tutorial || { echo '备份已存在，请改用 .before_github_tutorial.2'; exit 1; }
cp /config/automations.yaml /config/automations.yaml.before_github_tutorial
```

如果备份名已经存在，不要覆盖；把命令中的后缀改为 `.before_github_tutorial.2` 等未使用名称，并记下它供回滚使用。

把下面这个不带 `automation:` 包装的列表项追加到 `/config/automations.yaml`，并把 `camera.your_cw700s` 替换为开发者工具 → 状态中查到的 CW700S 实体：

```yaml
- id: cw700s_sync_every_6_hours
  alias: CW700S 每 6 小时同步告警录像
  triggers:
    - trigger: time_pattern
      hours: "/6"
      minutes: "15"
  conditions: []
  actions:
    - action: cw700s_downloader.sync
      data:
        entity_id: camera.your_cw700s
        full_scan: false
  mode: single
```

`full_scan: false` 使用已有状态做增量扫描。开发者工具 → 操作中的手动同步仍然可用；组件会拒绝重叠运行，不会同时启动第二个下载任务。

字段格式参考 Home Assistant 官方文档：[Automation trigger](https://www.home-assistant.io/docs/automation/trigger/) 和 [Automation action](https://www.home-assistant.io/docs/automation/action/)。保存后运行：

```bash
ha core check && ha core restart
```

`ha core check` 失败时，`&&` 会阻止重启。

## 安装最近录像卡片 JavaScript

在 Home Assistant Terminal & SSH 中执行。若目标文件原本存在，先保存为 `.cw700s.bak`：

```bash
mkdir -p /config/www
test ! -e /config/www/cw700s-recent-card.js.cw700s.bak || { echo '备份已存在，请改用 .cw700s.bak.2'; exit 1; }
[ ! -e /config/www/cw700s-recent-card.js ] || cp /config/www/cw700s-recent-card.js /config/www/cw700s-recent-card.js.cw700s.bak
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/www/cw700s-recent-card.js \
  /config/www/cw700s-recent-card.js
```

如果 `.cw700s.bak` 已存在，不要覆盖；改用 `.cw700s.bak.2` 等未使用名称，并在回滚时使用同一名称。正常结果是 `/config/www/cw700s-recent-card.js` 存在。

## 注册前端资源

打开设置 → 仪表板 → 右上角菜单 → 资源，添加：

```text
/local/cw700s-recent-card.js
```

资源类型选择 JavaScript 模块。`/local/` 对应 Home Assistant 的 `/config/www/`。

## 添加主仪表板卡片

打开目标仪表板，新增手动卡片，把仓库中的 `home-assistant/dashboard/cw700s_dashboard_card.yaml` 完整粘贴进去。保存前把其中的 `camera.your_cw700s` 换成自己的摄像头实体。

卡片读取 `sensor.cw700s_sync_status`，并调用 `cw700s_downloader.sync` 与 `cw700s_downloader.stop`。不要改成其他服务名。

## 验证同步、停止和最近六条录像

1. 点击“立即同步”，确认状态和进度开始变化。
2. 同步期间再次触发同步，确认组件拒绝重叠运行。
3. 点击“停止同步”并确认，检查当前任务停止；之后仍可重新手动同步。
4. 完成一次有录像的同步后，确认最近告警区域最多渲染六条记录。
5. 在已登录 Home Assistant 的浏览器中确认缩略图可见；缩略图需要 Home Assistant 身份验证。
6. 点击缩略图，确认浏览器打开签名视频端点。该地址是临时访问地址，不要复制到公开日志或帖子。

## 常见错误

- 显示“自定义元素不存在”：确认文件路径和资源 URL 完全一致，然后清除前端缓存并重新加载页面。
- 按钮报实体不存在：再次替换卡片和自动化中的 `camera.your_cw700s`。
- 最近录像为空：先确认同步已产生 MP4，并检查 `sensor.cw700s_sync_status` 的最近录像属性。
- 自动化没有按时运行：检查自动化是否已启用，并按官方 trigger/action 文档核对 YAML 层级。

## 回滚

<details>
<summary>展开回滚步骤</summary>

从仪表板删除主卡片和 `/local/cw700s-recent-card.js` 资源。然后恢复安装前的文件：

```bash
# 仅当 JavaScript 文件在安装前存在且已备份时执行
cp /config/www/cw700s-recent-card.js.cw700s.bak /config/www/cw700s-recent-card.js

# 仅当 JavaScript 文件在安装前不存在时执行；不要同时执行上一条
rm -f /config/www/cw700s-recent-card.js
```

如果使用了 `.cw700s.bak.2`，把恢复命令改为该实际备份名。自动化没有后续编辑时，可恢复完整备份：

```bash
cp /config/automations.yaml.before_github_tutorial /config/automations.yaml
ha core check && ha core restart
```

如果安装时使用了 `.before_github_tutorial.2`，把恢复命令改为该实际备份名。如果备份后又添加了其他自动化，只删除 `id: cw700s_sync_every_6_hours` 对应的列表项，再运行同一条检查与重启命令；不要恢复整个旧文件。上述操作不会删除已下载录像，也不会移除手动同步服务。

</details>
