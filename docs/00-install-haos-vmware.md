# 00. 在 VMware 中安装 Home Assistant OS

完成本章后，你能从 Windows 浏览器打开 Home Assistant，并能在 **Terminal & SSH** 中看到 `/config` 和 `/media`。本教程以一台持续开机的 Windows 11 电脑为宿主机：VMware 运行 Home Assistant OS，`D:\CW700S` 保存录像，本地 AI 也在 Windows 上运行。

> 本章界面名称按 VMware Workstation Pro 17.6 编写。Home Assistant 官方的 [Windows 虚拟机安装页](https://www.home-assistant.io/installation/windows/) 是版本变化时的最终依据。

## 准备 Windows 宿主机

**操作位置：Windows 宿主机**

需要以下条件：

- 64 位 Windows 11；
- BIOS/UEFI 中已启用 Intel VT-x 或 AMD-V；
- 至少为虚拟机分配 2 个 CPU 核心和 2 GB 内存，本教程建议 4 GB；
- Windows 电脑与 CW700S 连接同一个家庭网络；
- 建议使用有线网络，桥接网络排错更简单。

按 Broadcom 的 [VMware Workstation Pro 安装说明](https://knowledge.broadcom.com/external/article/387947/installing-vmware-workstation-pro.html) 下载并安装 VMware Workstation Pro。首次启动后能看到 **Create a New Virtual Machine** 即可。

## 下载 Home Assistant OS 虚拟磁盘

**操作位置：Windows 浏览器和文件资源管理器**

打开 Home Assistant 官方的 [Windows 安装页](https://www.home-assistant.io/installation/windows/)，在 **VMware Workstation (.vmdk)** 下下载压缩包，然后在 Windows 中完整解压。

正常结果：解压目录中存在名称类似 `haos_ova_18.1.vmdk` 的文件。版本号可能更新，文件扩展名必须是 `.vmdk`。

不要下载通用 x86-64 裸机镜像；虚拟机必须使用官方标为 VMware Workstation 的镜像。

## 创建 VMware 虚拟机

**操作位置：VMware Workstation Pro**

在 VMware Workstation Pro 中执行：

1. 选择 **Create a New Virtual Machine**。
2. 选择 **I will install the operating system later**。
3. 客户机系统选择 **Linux**，版本选择 **Other Linux 5.x kernel 64-bit**。
4. 名称填写 `home-assistant`，位置使用容易找到的目录，例如 `C:\home-assistant`。
5. 虚拟磁盘保持默认容量并选择 **Store virtual disk as a single file**。这一步创建的是占位磁盘，稍后会替换。
6. 选择 **Customize Hardware**，把内存设为 4 GB、处理器设为 2 个核心。
7. 删除不使用的 **New CD/DVD**。
8. 将 **Network Adapter** 设为 **Bridged**，取消 **Replicate physical network connection state**。
9. 在 **Configure Adapters** 中只保留 Windows 实际联网的有线或 Wi-Fi 适配器，不选择 VMware 虚拟网卡和蓝牙适配器。
10. 完成向导，但先不要启动虚拟机。

正常结果：VMware 左侧列表出现 `home-assistant`，状态为关闭。看不到 64 位 Linux 时，跳到 [VMware 中没有 64 位 Linux](06-troubleshooting.md#vmware-中没有-64-位-linux)。

## 用 HAOS 磁盘替换占位磁盘

**操作位置：Windows 文件资源管理器和记事本**

确认虚拟机处于关闭状态，然后在 Windows 文件资源管理器中打开刚才选择的虚拟机目录，例如 `C:\home-assistant`：

1. 删除向导生成的 `home-assistant.vmdk`。
2. 把下载并解压得到的 HAOS `.vmdk` 文件复制到这个目录。
3. 将复制后的文件重命名为 `home-assistant.vmdk`。
4. 右键目录中的 `.vmx` 文件，用记事本打开。
5. 在 `.encoding` 行下新增：

```text
firmware = "efi"
```

保存 `.vmx`。如果 VMware 启动时报找不到磁盘，先确认复制的是 `.vmdk` 文件本身，而不是包含它的文件夹。

仍然失败时，跳到 [VMware 报找不到 VMDK](06-troubleshooting.md#vmware-报找不到-vmdk)。

## 首次启动与初始化

**操作位置：VMware Workstation Pro 和 Windows 浏览器**

在 VMware 中启动 `home-assistant`。控制台完成启动后，在 Windows 浏览器访问：

```text
http://homeassistant.local:8123
```

如果该地址打不开，查看 VMware 控制台显示的 Home Assistant IP，并访问：

```text
http://<Home Assistant IP>:8123
```

按 Home Assistant 的 [首次初始化向导](https://www.home-assistant.io/getting-started/onboarding/) 创建管理员账号、设置家庭位置和时区。管理员密码只保存在自己的密码管理器中，不要写入本仓库、截图或 Issue。

正常结果：浏览器进入 Home Assistant 首页。页面打不开时，跳到 [Home Assistant 页面打不开](06-troubleshooting.md#home-assistant-页面打不开)。

## 安装 Terminal & SSH 和 File editor

**操作位置：Home Assistant 界面**

在 Home Assistant 中打开“设置 → 应用 → 安装应用”，完成两项安装：

1. 安装并启动 **Terminal & SSH**；
2. 安装 **File editor**，后续用它安全编辑 `/config/configuration.yaml`。

旧版界面可能把“应用”称为“加载项”。Terminal & SSH 默认只对启用“高级模式”的用户显示；看不到时，打开个人资料并启用高级模式。

打开 Terminal & SSH 的 Web 界面，执行：

```bash
ls -ld /config /media
```

正常结果是显示两个目录。如果没有 `/config`，当前终端不是 Home Assistant OS 的应用终端，不要继续复制文件。

## 本章验收

- Windows 浏览器能打开 Home Assistant；
- “设置 → 系统 → 关于”能看到 Home Assistant OS 与 Core 版本；
- Terminal & SSH 中能列出 `/config` 和 `/media`。
- File editor 已安装并能打开 `/config/configuration.yaml`。

全部满足后，继续 [01. 连接 CW700S、Windows 存储与教程仓库](01-environment.md)。

## 常见阻塞

- VMware 不提供 64 位客户机：进入主板 BIOS/UEFI 启用硬件虚拟化。
- Home Assistant 没有网络：确认网卡是 **Bridged**，并只桥接 Windows 实际联网的物理网卡。
- `homeassistant.local` 打不开：改用 VMware 控制台显示的 IP 地址。
- Windows 休眠后 Home Assistant 离线：完成首次 MP4 验证前保持宿主机唤醒；配置自动同步时再调整电源策略。

更完整的恢复方法见 [06. 排错与回滚](06-troubleshooting.md)。
