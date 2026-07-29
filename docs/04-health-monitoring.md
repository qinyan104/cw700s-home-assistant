# 04. 系统健康监控

> 可选增强：不完成本章，也不影响录像下载和仪表板。

完成本章后，Home Assistant 会检查 Windows 共享是否在线且可写、磁盘剩余空间、最近同步时间和失败记录。为验证写权限，脚本会在共享根目录创建一个临时文件并立即删除；它不会修改已有录像。开始前应已完成 [03. 自动同步与仪表板](03-automation-and-dashboard.md)。

## 启用 packages 目录

先备份配置：

```bash
test ! -e /config/configuration.yaml.before_github_tutorial || { echo '备份已存在，请改用 .before_github_tutorial.2'; exit 1; }
cp /config/configuration.yaml /config/configuration.yaml.before_github_tutorial
```

备份名已存在时不要覆盖；改用 `.before_github_tutorial.2` 等未使用名称，并记下它供回滚使用。然后按照官方 [Configuration packages](https://www.home-assistant.io/docs/configuration/packages/) 说明，在 `/config/configuration.yaml` 的现有 `homeassistant:` 键下合并 `packages`。不要创建第二个 `homeassistant:` 键。

```yaml
homeassistant:
  packages: !include_dir_named packages
```

如果已有 `homeassistant:` 配置，最终结构应只有一个顶层键，其中包含原配置和上面的 `packages` 行。

## 复制健康检查脚本和配置包

复制前检查并备份已有的脚本和配置包：

```bash
test ! -e /config/cw700s_health.py.cw700s.bak || { echo '脚本备份已存在，请改用 .cw700s.bak.2'; exit 1; }
test ! -e /config/packages/cw700s_health_package.yaml.cw700s.bak || { echo '配置包备份已存在，请改用 .cw700s.bak.2'; exit 1; }
[ ! -e /config/cw700s_health.py ] || cp /config/cw700s_health.py /config/cw700s_health.py.cw700s.bak
[ ! -e /config/packages/cw700s_health_package.yaml ] || cp /config/packages/cw700s_health_package.yaml /config/packages/cw700s_health_package.yaml.cw700s.bak
```

任何 `.cw700s.bak` 已存在时都不要覆盖；把两处检查、备份和后续回滚使用的后缀改为同一个未使用名称，例如 `.cw700s.bak.2`。完成备份后执行：

```bash
mkdir -p /config/packages
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/scripts/cw700s_health.py \
  /config/cw700s_health.py
cp /media/Windows_CW700S/cw700s-home-assistant/home-assistant/packages/cw700s_health_package.yaml \
  /config/packages/cw700s_health_package.yaml
python3 /config/cw700s_health.py
ha core check && ha core restart
```

`ha core check` 失败时，`&&` 会阻止重启。

## 检查 JSON 输出

单独执行：

```bash
python3 /config/cw700s_health.py
```

脚本应输出一行 JSON，顶层 `status` 必须是 `正常`、`警告` 或 `异常` 之一。输出还应包含共享在线/可写状态、剩余空间、最近同步时间、查询失败数和下载失败事件数。JSON 输出是本机状态，公开求助前先清理路径和日志中的私密信息。

## 检查 Home Assistant 配置并重启

```bash
ha core check && ha core restart
```

重启后在开发者工具 → 状态中查找 `sensor.cw700s_system_health`。配置包每 300 秒运行一次健康脚本；首次出现实体可能需要等到 Home Assistant 完成初始化。

## 添加健康卡片

在目标仪表板新增手动卡片，把 `home-assistant/dashboard/cw700s_health_card.yaml` 完整粘贴进去。卡片应显示共享状态、剩余空间、最近同步时间、查询失败日期数、下载失败记录数和问题摘要。

## 状态与阈值

当前脚本使用以下固定阈值：

- 剩余空间低于 10 GB：`警告`；
- 剩余空间低于 5 GB：`异常`；
- 距离上次同步超过 36 小时：`警告`。

共享目录不存在或不可写会进入 `异常`。上次日期查询失败、状态文件仍有下载失败记录、没有同步时间或同步时间无法解析会进入 `警告`。所有检查均正常时状态为 `正常`。

## 常见错误

- YAML 报重复键：把 `packages` 合并到已有的 `homeassistant:` 下，不要保留两个顶层键。
- JSON 显示共享不可用或不可写：先在设置 → 系统 → 存储中检查 `/media/Windows_CW700S` 的网络存储挂载和权限。
- JSON 没有最近同步时间：先成功运行一次下载同步，确认 `/config/cw700s_sync_state.json` 已更新。
- 实体不出现：确认包文件位于 `/config/packages/`，`ha core check` 已通过，并查看 Home Assistant 日志中的 `command_line` 配置错误。

## 回滚

<details>
<summary>展开回滚步骤</summary>

先从仪表板删除健康卡片。下面的命令会恢复安装前已有的文件；没有备份时，只删除本教程新安装的对应文件：

```bash
if [ -e /config/cw700s_health.py.cw700s.bak ]; then
  cp /config/cw700s_health.py.cw700s.bak /config/cw700s_health.py
else
  rm -f /config/cw700s_health.py
fi

if [ -e /config/packages/cw700s_health_package.yaml.cw700s.bak ]; then
  cp /config/packages/cw700s_health_package.yaml.cw700s.bak /config/packages/cw700s_health_package.yaml
else
  rm -f /config/packages/cw700s_health_package.yaml
fi
```

使用了 `.cw700s.bak.2` 时，把回滚命令中的备份名改为该实际名称。如果启用 packages 后没有其他配置改动，可恢复配置备份；否则只删除本章加入的 `packages: !include_dir_named packages` 行，并保留其他更改：

```bash
cp /config/configuration.yaml.before_github_tutorial /config/configuration.yaml
ha core check && ha core restart
```

如果安装时使用了 `.before_github_tutorial.2`，把恢复命令改为该实际备份名。只有确认没有后续配置更改时才运行上面的完整恢复。已下载录像和同步状态文件不受影响。

</details>
