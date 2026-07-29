# 教程截图采集清单

文字教程不依赖截图即可完成安装。后续只补下面 6 张关键截图，文件齐备并通过隐私检查后，再把它们链接到对应章节。

| 建议文件名 | 画面内容 | 对应章节 |
|---|---|---|
| `01-vmware-network.png` | VMware 的 Bridged 网络和物理网卡选择 | 第 00 章 |
| `02-haos-ready.png` | HAOS 控制台启动完成，不显示家庭 IP | 第 00 章 |
| `03-hacs-xiaomi-miot.png` | HACS 中正确的 Xiaomi Miot 仓库 | 第 01 章 |
| `04-cw700s-entity.png` | CW700S 实体页面，真实实体 ID 已遮盖 | 第 01 章 |
| `05-network-storage.png` | `Windows_CW700S` 网络存储，服务器和账号已遮盖 | 第 01 章 |
| `06-first-sync-result.png` | 同步状态完成和第一条 MP4，路径及画面已脱敏 | 第 02 章 |

## 发布前检查

每张截图必须遮盖：

- 小米账号、设备 did、设备 token；
- access token、Cookie、完整 M3U8 地址和签名参数；
- GitHub 设备授权码；
- 家庭公网或内网 IP；
- Windows 用户名、SMB 用户名和密码；
- 真实摄像头实体 ID；
- 可识别住址、人员、车辆号牌或邻居的画面。

不要用伪造的 Home Assistant 界面替代真实截图。未通过检查的图片留在仓库外，不要先提交再修改。
