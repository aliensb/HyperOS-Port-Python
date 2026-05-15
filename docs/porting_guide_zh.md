# HyperOS ROM 移植完全指南

> 本文从零基础出发，讲解安卓系统包的构成、移植原理、以及本项目的完整工作流程。

---

## 术语表

在开始之前，先了解本文和项目中频繁出现的关键术语：

### 核心概念

| 术语 | 含义 |
|------|------|
| **Stock** | "原厂"的意思。在本项目中指**目标设备的官方 ROM**（通常是国行 CN 版）。它提供 firmware 和 vendor 分区，因为这些必须与你的硬件匹配。可以理解为"底包"。 |
| **Port** | "移植源"的意思。指你想要移植过来的 ROM（通常是 xiaomi.eu 版）。它提供 system/product 等软件分区。可以理解为"供体包"。 |
| **ROM** | Read-Only Memory 的缩写，但在刷机语境中泛指"系统固件包"，即一个完整的操作系统安装包。 |
| **移植（Porting）** | 将一个 ROM 的软件部分"嫁接"到另一个设备的硬件驱动上，使其能在目标设备上运行。 |
| **刷机（Flash）** | 将 ROM 写入手机存储分区的过程，类似于给电脑重装系统。 |

### 分区与镜像

| 术语 | 含义 |
|------|------|
| **分区（Partition）** | 手机存储的一个独立区域，类似电脑硬盘的 C 盘、D 盘。每个分区有特定用途。 |
| **镜像（Image / .img）** | 分区内容的完整副本文件。`system.img` 就是 system 分区的镜像，可以理解为"分区的快照"。 |
| **super.img** | 动态分区容器，把多个逻辑分区（system、vendor、product 等）打包在一起的大文件。 |
| **payload.bin** | OTA 更新包格式，所有分区镜像的打包容器，需要专用工具解包。 |
| **Firmware** | 固件，直接控制硬件的底层软件（基带、引导程序、安全芯片等）。设备专属，不可跨设备使用。 |
| **Vendor** | 硬件抽象层（HAL），是连接安卓框架和底层硬件驱动的"翻译层"。设备专属。 |
| **System** | 安卓操作系统的核心框架，包含 Java 层服务、系统 app、UI 框架等。可跨设备移植。 |

### 文件系统与启动

| 术语 | 含义 |
|------|------|
| **erofs** | Enhanced Read-Only File System，增强只读文件系统。压缩率高、读取快，现代安卓默认使用。 |
| **ext4** | 传统 Linux 文件系统，支持读写，但体积较大。 |
| **Ramdisk** | 启动时加载到内存的临时文件系统，包含 `init`（系统启动的第一个进程）。 |
| **AVB / Verified Boot** | Android Verified Boot，启动验证机制。确保系统分区未被篡改。移植包必须禁用它，否则无法启动。 |
| **vbmeta** | 存储 AVB 验证信息的分区。通过修改其 flag 字节来禁用验证。 |
| **dm-verity** | 运行时分区完整性验证机制。如果启用，修改过的分区会导致启动失败。 |

### 修改相关

| 术语 | 含义 |
|------|------|
| **Smali** | Android 字节码的人类可读形式（类似汇编语言）。修改系统 JAR 包时需要反编译为 smali，修改后再编译回去。 |
| **JAR** | Java Archive，Java 程序的打包格式。安卓框架的核心代码（services.jar、framework.jar）都是 JAR 文件。 |
| **Prop / Build.prop** | 系统属性文件，存储设备信息和功能开关（如设备型号、是否国际版等）。类似 Windows 注册表。 |
| **Overlay** | 覆盖层，不修改原始文件，而是在其上叠加修改。安卓用 overlay 机制定制 UI 和配置。 |
| **SELinux** | Security-Enhanced Linux，安卓的强制访问控制系统。每个文件和进程都有安全标签（context）。 |
| **file_contexts** | SELinux 标签映射文件，定义每个路径应该有什么安全标签。打包时必须正确设置。 |
| **fs_config** | 文件系统配置，定义每个文件的 UID/GID（所有者）和权限。打包时必须正确设置。 |

### 工具与操作

| 术语 | 含义 |
|------|------|
| **Fastboot** | 安卓设备的底层刷写模式，可以直接写入任意分区。通过 USB 连接电脑操作。 |
| **Recovery** | 安卓的恢复模式，可以刷入 OTA 包、清除数据等。 |
| **双清（Wipe）** | 清除 userdata + metadata 分区，即删除所有用户数据和加密密钥。切换 firmware 时通常需要。 |
| **A/B 分区** | 现代安卓的双分区方案，有 `_a` 和 `_b` 两套分区，支持无缝更新。刷机时两套都要刷。 |
| **KernelSU (KSU)** | 基于内核的 root 方案，通过修改 init_boot 注入内核模块实现 root 权限。 |
| **Magiskboot** | Magisk 项目的 boot 镜像操作工具，用于解包/重打包 boot.img 和 ramdisk。 |

### 项目特有术语

| 术语 | 含义 |
|------|------|
| **EU Bundle** | 从国行 ROM 中提取的 app 集合（钱包、通讯录等），用于补充 EU 系统缺失的国行功能。 |
| **EU Localization** | EU 本地化，将 EU 系统适配为中国用户使用的过程（注入国行 app、修改属性等）。 |
| **Prophook** | 属性伪装机制，让特定 app 读取到伪造的设备信息，用于解锁高端机型专属功能。 |
| **Feature Unlock** | 通过修改设备特性 XML 文件来启用/禁用系统功能（如 AI 显示增强、AOD 等）。 |
| **Official Modification** | 不做移植，只对单个 ROM 进行修改（不传 `--port` 参数时的模式）。 |
| **Wild Boost** | 性能增强功能，通过修改系统配置提升游戏/应用性能。 |

---

## 第一章：安卓系统包的构成

### 1.1 什么是"刷机包"

一个安卓刷机包本质上是一组**分区镜像文件**的集合。你可以把手机的存储想象成一块硬盘，被划分成了很多"分区"，每个分区存放不同的内容。

### 1.2 分区分类

安卓设备的分区分为两大类：

#### Firmware 分区（硬件相关，设备专属）

| 分区名 | 作用 |
|--------|------|
| `modem` | 基带固件，负责手机信号、通话、数据网络 |
| `abl` | Android Bootloader，引导启动 |
| `tz` | TrustZone，安全环境（指纹、支付、加密） |
| `keymaster` | 密钥管理（锁屏密码、文件加密） |
| `dsp` | 数字信号处理器固件（音频、传感器） |
| `bluetooth` | 蓝牙固件 |
| `vbmeta` | Verified Boot 元数据（启动验证链） |
| `boot` / `init_boot` | Linux 内核 + ramdisk（启动第一阶段） |

这些分区与**具体硬件绑定**，不同设备的 firmware 不能互换。

#### Logical 分区（系统软件，可移植）

这些分区打包在一个叫 `super.img` 的大容器里：

| 分区名 | 作用 |
|--------|------|
| `system` | 安卓框架核心（framework.jar、services.jar、SystemUI 等） |
| `system_ext` | 系统扩展（厂商定制的框架层代码） |
| `product` | 产品层（预装 app、overlay、字体） |
| `vendor` | 硬件抽象层 HAL（连接 framework 和硬件驱动） |
| `odm` | 设备制造商定制（传感器配置、相机参数） |
| `mi_ext` | 小米扩展分区 |

### 1.3 刷机包的两种格式

#### OTA 包（payload.bin 格式）
```
ROM.zip
├── payload.bin          ← 所有分区镜像打包在一起（需要 payload_dumper 解包）
├── payload_properties.txt
└── META-INF/
```

#### Fastboot 包（images/ 格式）
```
ROM.zip
├── images/
│   ├── boot.img
│   ├── modem.img
│   ├── super.img       ← 包含 system/vendor/product 等逻辑分区
│   └── ...
└── flash_all.sh
```

### 1.4 super.img 的结构

`super.img` 是一个**动态分区容器**，里面包含多个逻辑分区。可以理解为"硬盘里的硬盘"：

```
super.img (约 12.5GB)
├── system (erofs 文件系统镜像)
├── system_ext (erofs)
├── product (erofs)
├── vendor (erofs)
├── odm (erofs)
├── vendor_dlkm (erofs)
├── odm_dlkm (erofs)
└── mi_ext (erofs)
```

### 1.5 文件系统类型

- **erofs**：只读压缩文件系统，体积小、读取快，现代安卓默认使用
- **ext4**：传统读写文件系统，体积大但可修改

---

## 第二章：什么是 ROM 移植

### 2.1 为什么要移植

以小米 15 Ultra（代号 xuanyuan）为例：
- 国行 ROM：功能全（小爱、钱包），但有广告、臃肿 app
- xiaomi.eu ROM：基于国行精简，去广告，加 Google 服务，但缺少部分国行功能

**移植的目标**：取两者之长——用 EU 的干净系统 + 国行的硬件驱动 + 选择性保留国行 app。

### 2.2 移植的核心思路

```
国行 ROM (stock)  ──提取──→  firmware + vendor + odm（硬件相关）
                                    ↓
                              ┌─────────────┐
                              │  组装目标 ROM │
                              └─────────────┘
                                    ↑
EU ROM (port)     ──提取──→  system + product + system_ext（系统软件）
```

简单说：**硬件层用国行的，软件层用 EU 的**。

### 2.3 为什么不能直接刷 EU 包

因为 EU 包里的 vendor/odm 是为其他设备编译的（或者是通用版本），与你设备的硬件驱动不匹配。直接刷会导致：
- 相机不工作
- 指纹失效
- 信号异常
- 无法开机

---

## 第三章：本项目的完整工作流程

### 3.1 总览

```
输入                    处理                         输出
─────────────────────────────────────────────────────────────
CN stock ROM ─┐                                    
              ├──→ 提取 → 组装 → 修改 → 打包 ──→ 可刷入的 ROM
EU port ROM ──┘                                    (out/eu/)
```

### 3.2 阶段一：提取（Extraction）

#### 从 CN stock ROM 提取

CN ROM 是 payload.bin 格式，使用 `payload_dumper` 工具解包：

```
payload.bin → payload_dumper → 
├── boot.img
├── modem.img
├── vendor.img        ← 需要这些
├── odm.img           ← 
├── system.img        ← 不用（用 EU 的）
└── ...（几十个分区）
```

然后将 `.img` 文件解包为目录树：
```
vendor.img (erofs) → extract → vendor/
├── bin/
├── etc/
├── lib/
├── firmware/
└── ...
```

#### 从 EU port ROM 提取

EU ROM 是 images/ 格式（已经是独立 .img 文件），只需解包逻辑分区：

```
images/system.img → extract → system/
images/product.img → extract → product/
images/system_ext.img → extract → system_ext/
```

### 3.3 阶段二：组装目标工作区（Workspace）

将提取出的目录按照以下规则组装到 `build/target/` 目录：

| 分区 | 来源 | 原因 |
|------|------|------|
| `vendor` | CN stock | 硬件驱动必须匹配设备 |
| `odm` | CN stock | 设备制造商配置 |
| `vendor_dlkm` | CN stock | vendor 内核模块 |
| `odm_dlkm` | CN stock | odm 内核模块 |
| `system_dlkm` | CN stock | 系统内核模块 |
| `system` | EU port | 干净的系统框架 |
| `system_ext` | EU port | 系统扩展 |
| `product` | EU port | 预装 app |
| `mi_ext` | EU port | 小米扩展 |
| `product_dlkm` | EU port | product 内核模块 |

同时，将 CN stock 的所有 firmware 镜像（boot.img、modem.img 等）复制到 `repack_images/` 目录。

### 3.4 阶段三：修改（Modification）

这是最复杂的阶段，分为多个子步骤：

#### 3.4.1 系统修改（System Plugins）

**去除臃肿 app（Debloat）：**
```python
debloat_list = ["MSA", "AnalyticsCore", "MiuiDaemon", "MiuiBugReport", ...]
# 从 target 目录中删除这些 app 的文件夹
```

**EU 本地化 app 注入（eu_bundle_config.json）：**
从 CN stock 中提取指定 app，覆盖到 EU 系统中：
```
CN stock/product/app/MINextpay → target/product/app/MINextpay
CN stock/product/priv-app/MIUIContactsT → target/product/priv-app/MIUIContactsT
```

**特性解锁（Feature Unlock）：**
修改 `product/etc/device_features/xuanyuan.xml`：
```xml
<bool name="support_AI_display">true</bool>
<bool name="support_SR_for_image_display">true</bool>
```

**属性修改（Props）：**
修改各分区的 `build.prop` 文件，注入/修改系统属性：
```
ro.product.spoofed.name=xuanyuan
persist.sys.miui.unfairMemory.enable=false
```

#### 3.4.2 框架修改（Framework Modifier）

这是最底层的修改——直接修改系统 JAR 包中的字节码（smali）。

**工作流程：**
```
system/framework/services.jar
    → APKEditor 反编译 → smali 代码
    → 修改特定方法（签名验证绕过、国际版标识等）
    → APKEditor 重新编译 → 修改后的 services.jar
```

**主要 patch：**
- `PackageManagerServiceImpl`：绕过签名验证（允许安装修改过的 app）
- `SystemServerImpl`：清空构造函数（移除国行特有的服务初始化）
- `IS_INTERNATIONAL_BUILD`：强制设为 true（让系统认为是国际版）

#### 3.4.3 Firmware 修改

**vbmeta 补丁：**
```
vbmeta.img 偏移 123 字节处写入 0x03
→ 禁用 dm-verity（不验证分区完整性）
→ 禁用 verification（不验证签名）
```
这是移植包必须的，因为修改过的分区无法通过原始签名验证。

**KernelSU 注入（可选）：**
```
init_boot.img → 解包 ramdisk
    → 将 init 重命名为 init.real
    → 注入 ksuinit 作为新的 init
    → 注入 kernelsu.ko 内核模块
    → 重新打包 init_boot.img
```

#### 3.4.4 物理覆盖（Overrides）

将 `devices/xuanyuan/override/` 目录下的文件直接覆盖到目标：
```
devices/xuanyuan/override/eu/product/etc/device_info.json
    → target/product/etc/device_info.json
```

### 3.5 阶段四：打包（Repacking）

#### 4.1 构建文件系统镜像

将修改后的目录树重新打包为 erofs 镜像：

```bash
# 对每个逻辑分区执行
mkfs.erofs \
  --mount-point=/vendor \           # 挂载点
  --fs-config-file=vendor_fs_config \  # 文件权限/所有者
  --file-contexts=vendor_file_contexts \ # SELinux 标签
  -zlz4hc \                         # 压缩算法
  vendor.img \                      # 输出文件
  target/vendor/                    # 输入目录
```

#### 4.2 组装 super.img

将所有逻辑分区镜像打包进一个 super.img：

```bash
lpmake \
  --metadata-size 65536 \
  --super-name super \
  --metadata-slots 3 \
  --device super:13421772800 \      # super 分区总大小
  --group qti_dynamic_partitions_a:13421772800 \
  --partition system_a:readonly:SIZE \
  --image system_a=system.img \
  --partition vendor_a:readonly:SIZE \
  --image vendor_a=vendor.img \
  ... # 所有分区
  --output super.img
```

#### 4.3 生成刷机脚本

生成 `mac_linux_flash_script.sh`，内容大致为：

```bash
#!/bin/bash
# 1. 验证设备代号
fastboot getvar product  # 确认是 xuanyuan

# 2. 刷入 firmware（逐个分区）
fastboot flash abl_a firmware-update/abl.img
fastboot flash modem_a firmware-update/modem.img
fastboot flash tz_a firmware-update/tz.img
... # 约 37 个 firmware 分区，a/b 双槽位

# 3. 刷入 super（系统分区容器）
fastboot flash super super.img

# 4. 刷入 boot（内核）
fastboot flash boot_a boot.img
fastboot flash init_boot_a init_boot.img

# 5. 设置活动槽位并重启
fastboot set_active a
fastboot reboot
```

### 3.6 最终输出

```
out/eu/
├── mac_linux_flash_script.sh    ← 刷机脚本
├── super.img.zst                ← 压缩后的 super 镜像（~5GB）
├── boot.img                     ← 内核
├── init_boot.img                ← init（含 KSU）
├── vbmeta.img                   ← 已 patch 的验证元数据
└── firmware-update/             ← 所有 firmware 分区镜像
    ├── modem.img
    ├── abl.img
    ├── tz.img
    └── ...（约 37 个文件）
```

---

## 第四章：关键概念详解

### 4.1 为什么需要 vbmeta patch

安卓的 Verified Boot（AVB）机制会在启动时验证每个分区的签名：
```
vbmeta → 验证 boot → 验证 system → 验证 vendor → ...
```

移植包修改了 system/product 等分区，原始签名已失效。如果不禁用验证，手机会拒绝启动（显示红色警告或直接 bootloop）。

### 4.2 A/B 分区机制

现代安卓设备有两套分区槽位（slot_a 和 slot_b）：
- 正常使用时运行 slot_a
- OTA 更新写入 slot_b
- 重启后切换到 slot_b

所以刷机时需要同时刷 `_a` 和 `_b`（或只刷 `_a` 然后 `set_active a`）。

### 4.3 vendor 兼容性

vendor 分区包含硬件抽象层（HAL），它是 framework 和内核驱动之间的桥梁：

```
App → Framework (system) → HAL (vendor) → Kernel Driver → Hardware
```

如果 vendor 和 system 版本不匹配（比如 vendor 期望 API 35 但 system 提供 API 34），会导致各种功能异常。这就是为什么移植时 vendor 必须来自同一 build 版本的 stock ROM。

### 4.4 erofs 与 ext4 的选择

| | erofs | ext4 |
|---|---|---|
| 可写 | 否（只读） | 是 |
| 体积 | 小（压缩） | 大 |
| 性能 | 读取快 | 读写均可 |
| 用途 | 正式刷机包 | 开发调试 |

生产环境一律用 erofs。

### 4.5 SELinux 和 fs_config

每个文件都有两个元数据：
- **fs_config**：Unix 权限（uid/gid/mode），如 `system/bin/sh 0 2000 0755`
- **file_contexts**：SELinux 安全标签，如 `system/bin/sh u:object_r:shell_exec:s0`

打包时必须正确设置这些，否则系统启动后会因为权限问题崩溃。本项目在提取分区时同时提取这两个配置文件，打包时原样写回。

---

## 第五章：配置文件说明

### 5.1 devices/xuanyuan/config.json
```json
{
    "pack": {
        "type": "payload",      // 输出格式
        "fs_type": "erofs",     // 文件系统类型
        "super_size": 13421772800  // super 分区大小（必须精确匹配设备）
    },
    "ksu": { "enable": false }  // 是否默认注入 KernelSU
}
```

### 5.2 devices/xuanyuan/features.json
```json
{
    "xml_features": {
        "support_AI_display": true  // 写入设备特性 XML
    },
    "build_props": {
        "product": {
            "ro.product.spoofed.name": "xuanyuan"  // 写入 build.prop
        }
    }
}
```

### 5.3 devices/common/eu_bundle_config.json
```json
{
    "apps": [
        "product/app/MINextpay",           // 从 CN stock 提取到 EU 系统
        "product/priv-app/MIUIContactsT",  // 路径格式：分区/类型/app名
        "system/fonts/MiSansL3.otf"        // 也可以是非 app 文件
    ]
}
```

---

## 第六章：实际操作命令

### 6.1 标准移植（CN stock + EU port）

```bash
sudo python3 main.py \
  --stock /path/to/CN_ROM.zip \     # 国行 ROM（提供 firmware + vendor）
  --port /path/to/EU_ROM.zip \      # EU ROM（提供 system + product）
  --fs-type erofs \                 # 文件系统类型
  --pack-type super \               # 输出为 fastboot 刷机包
  --ksu \                           # 注入 KernelSU
  --clean                           # 清除上次构建
```

### 6.2 刷入

```bash
# 手机进入 fastboot 模式（关机后长按 电源+音量下）
cd out/eu/
sudo bash mac_linux_flash_script.sh
```

### 6.3 仅修改 EU ROM（Official Modification 模式）

不传 `--port` 参数时，stock ROM 同时作为 firmware 和 system 的来源：

```bash
sudo python3 main.py \
  --stock /path/to/EU_ROM.zip \
  --fs-type erofs \
  --pack-type super \
  --clean
```

---

## 第七章：常见问题原理

### 7.1 信号闪断

**原因**：EU 本地化注入了 `ro.miui.mcc=9460`（假 MCC），让系统误以为在国际网络环境。CN vendor 的电信 HAL 收到矛盾信号后触发 carrier config 重载。

**解决**：不注入影响电信的属性。

### 7.2 无法设置锁屏密码

**原因**：vbmeta flag 设置不当，verified boot 状态异常导致 keymaster 拒绝存储凭证。

**解决**：vbmeta flag 设为 `0x03`（同时禁用 dm-verity 和 verification）。

### 7.3 某些 app 闪退

**原因**：签名验证未绕过，或 SELinux 标签错误。

**解决**：framework smali patch 绕过签名验证 + 正确的 file_contexts。

---

## 附录：项目目录结构

```
HyperOS-Port-Python/
├── main.py                          # 入口
├── src/
│   ├── app/
│   │   ├── cli.py                   # 命令行参数定义
│   │   └── workflow.py              # 工作流编排
│   ├── core/
│   │   ├── rom/package.py           # ROM 解包类
│   │   ├── workspace.py             # 分区映射 + 目标组装
│   │   ├── packer.py                # 打包（erofs/super/flash script）
│   │   ├── context.py               # 全局上下文
│   │   └── modifiers/
│   │       ├── rom_modifier.py      # 去臃肿 + 覆盖
│   │       ├── firmware_modifier.py # vbmeta + KSU
│   │       ├── props.py             # build.prop 修改
│   │       ├── framework/tasks.py   # smali 字节码 patch
│   │       └── plugins/
│   │           ├── feature_unlock.py    # 特性解锁 + 属性注入
│   │           └── eu_localization.py   # EU 本地化 app 注入
│   └── utils/
│       └── sync_engine.py           # 文件同步引擎
├── devices/
│   ├── common/                      # 通用配置
│   │   ├── features.json
│   │   ├── eu_bundle_config.json
│   │   └── eu_localization.json
│   └── xuanyuan/                    # 设备专属配置
│       ├── config.json
│       ├── features.json
│       ├── props.json
│       ├── partition_info.json
│       ├── replacements.json
│       └── override/eu/             # 物理覆盖文件
├── bin/                             # 工具二进制
│   └── linux/x86_64/
│       ├── payload_dumper
│       ├── mkfs.erofs
│       ├── lpmake
│       ├── magiskboot
│       └── ...
├── tools/
│   └── generate_eu_bundle.py        # Bundle 生成工具
├── build/                           # 构建中间产物
│   ├── stockrom/extracted/          # CN stock 解包结果
│   ├── portrom/extracted/           # EU port 解包结果
│   └── target/                      # 组装后的目标目录
└── out/eu/                          # 最终输出
```
