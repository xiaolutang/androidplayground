# Android 蓝牙开发面试指南

> 核心框架：**系统层一套实现，应用层两个角色**。
> 站在"我在哪一层、当什么角色"的视角，讲清楚蓝牙全链路。
> 结合三篇车机实践文章 + AOSP 源码，体现"能写 API，也懂原理"。

---

## 一、协议栈全貌（面试第一问：讲讲你对蓝牙的理解）

### 1.1 分层架构

```
┌─────────────────────────────────────────────────┐
│              Application Layer                   │  ← 我们写的 App
├─────────────────────────────────────────────────┤
│       Framework Layer (android.bluetooth.*)      │  ← 应用直接调用的 API
│   BluetoothAdapter / BluetoothDevice / Profile   │
├─────────────────────────────────────────────────┤
│   Bluetooth System Service (System Process)      │  ← 系统进程
│   BluetoothManagerService / AdapterService       │
│   + 各 Profile Service (A2dpService / Avrcp...)  │
├─────────────────────────────────────────────────┤
│            JNI Layer (libbluetooth)              │
├─────────────────────────────────────────────────┤
│         Bluetooth Stack (Fluoride/GD)            │  ← C/C++ 协议栈
│   L2CAP / RFCOMM / SDP / SMP / GATT ...          │
├─────────────────────────────────────────────────┤
│         Vendor / HAL / Controller (芯片)         │
│              HCI → 蓝牙芯片固件                   │
└─────────────────────────────────────────────────┘
```

**一句话**：App → Framework API → 系统服务(Binder IPC) → JNI → 协议栈 → HCI → 芯片。

### 1.2 关键 Profile（必背清单）

| Profile | 作用 | 应用场景 |
|---------|------|----------|
| **A2DP** | 高质量单向音频流 | 蓝牙耳机/车机听歌 |
| **AVRCP** | 远程控制 + 元数据传输 | 车机显示歌名/控制播放 |
| **HFP** | 双向语音通话 | 车载免提 |
| **GATT** | 低功耗数据传输 | 手环、IoT 传感器 |
| **SPP** | 串口数据流 | 经典蓝牙自定义数据传输 |
| **HID** | 键盘/鼠标 | 蓝牙外设 |

> **金句**：Profile 本质是一种**能力约定**，定义设备之间如何交互。系统是否支持取决于有没有实现对应的 Profile Service。

---

## 二、核心框架：系统层一套 + 应用层两角色

这是本文档的主线。讲蓝牙，先定位"你在哪一层、当什么角色"：

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层（两个对称角色）                     │
│  ┌─────────────────────┐      ┌─────────────────────┐       │
│  │ 角色1：内容提供方     │      │ 角色2：内容消费/      │       │
│  │   (手机音乐App)      │      │  控制方(车机播放器)   │       │
│  │ A2DP Source/AVRCP TG │      │ A2DP Sink/AVRCP CT  │       │
│  └──────────┬──────────┘      └──────────┬──────────┘       │
└─────────────┼──────────────────────────────┼─────────────────┘
              │         Binder / 广播         │
┌─────────────▼──────────────────────────────▼─────────────────┐
│              系统层（一套实现，服务两端）                       │
│   BluetoothManagerService · AdapterService · Profile Service  │
│   MediaSessionService · Fluoride 协议栈 · 芯片                 │
└───────────────────────────────────────────────────────────────┘
```

**三句话记住框架**：
1. **系统层**是一套实现，跑在三个进程里，对两端透明——它是"邮局"，负责打包、寻址、投递
2. **角色1（手机）**是内容提供方，主力 API 是公开的 MediaSession，几乎不碰蓝牙类——解耦
3. **角色2（车机）**是消费/控制方，主力 API 是 @SystemApi 的 BluetoothAvrcpController——强耦合

---

## 三、系统层 — "中间件，对两端透明"

开发者不写这层，但必须懂，因为所有跨层 bug 都要在这定位。

### 3.1 进程边界（三个进程协作）

```
┌─────────────── 应用进程 (App) ────────────────┐
│  BluetoothAdapter (Binder 客户端)              │
│  MediaSession (Binder 客户端)                  │
│  BroadcastReceiver                             │
└───────────────┬───────────────────────────────┘
                │ Binder IPC
┌───────────────▼───────────────────────────────┐
│         系统进程 (system_server)               │
│  BluetoothManagerService (Binder Service)      │
│  MediaSessionService (Binder Service)          │
└───────────────┬───────────────────────────────┘
                │ bind Service
┌───────────────▼───────────────────────────────┐
│      蓝牙独立进程 (com.android.bluetooth)      │
│  AdapterService (IBluetooth Binder)            │
│    ├─ A2dpService                              │
│    ├─ Avrcp(Controller/Target)Service          │
│    ├─ HeadsetService                           │
│    └─ GattService → JNI → libbluetooth.so      │
└───────────────┬───────────────────────────────┘
                │ HCI
                ▼
            蓝牙芯片
```

### 3.2 系统层职责

| 职责 | 组件 | 说明 |
|------|------|------|
| 生命周期(开关/状态机) | BluetoothManagerService | 两端共用 |
| Profile Service 运行 | A2dpService/Avrcp*Service | 每个能力一个 Service |
| 协议栈托管 | Fluoride/GD (C++) + JNI | 两端共用 |
| 音频自动路由 | AudioFlinger + A2DP | 车机收音，App 无感 |
| **MediaSession↔AVRCP 桥接** | Avrcp 注册成 MediaController | **关键中间人** |
| 配对/加密/重连 | SMP + link key 存储 | 两端共用 |

### 3.3 三个必懂的关键机制

**① Profile 代理机制**：`getProfileProxy()` 异步返回代理，系统按需启动对应 Profile Service。

**② MediaSession 自动桥接**（核心）：
```
Avrcp.start()
  → MediaSessionManager.addOnActiveSessionsChangedListener()  // 启动时就注册
  → App 调 MediaSession.setActive(true)
  → onActiveSessionsChanged 触发
  → Avrcp 拿到 MediaController.registerCallback()  // 自动接管
```

**③ 广播总线**：跨进程通知全靠广播（`ACTION_TRACK_EVENT` / `ACTION_STATE_CHANGED`）。

### 3.4 蓝牙启动全链路时序

```
App            BluetoothAdapter      BluetoothManagerService      AdapterService        芯片
 │ enable()          │                      │                        │                 │
 │──────────────────▶│ mManagerService      │                        │                 │
 │                   │   .enable(pkg)       │                        │                 │
 │                   │─────────────────────▶│ 权限/前台检查           │                 │
 │                   │                      │ MESSAGE_ENABLE         │                 │
 │                   │                      │ handleEnable()         │                 │
 │                   │                      │  doBind(IBluetooth)    │                 │
 │                   │                      │───────────────────────▶│                 │
 │                   │                      │ onServiceConnected()   │                 │
 │                   │                      │ mBluetooth.enable()    │                 │
 │                   │                      │───────────────────────▶│ JNI → HCI ─────▶│
 │                   │                      │◀─── onBluetoothStateChange(STATE_ON) ─────│
 │ sendBroadcast(ACTION_STATE_CHANGED)      │                        │                 │
 │◀─────────────────────────────────────────│                        │                 │
```

**要点**：`enable()` 不是直接开芯片，是经 Binder → 系统服务 → bind 底层服务 → JNI → HCI。状态异步广播回来——**所以不能调完 enable 立刻用**。

---

## 四、系统层镜像：AvrcpTargetService vs AvrcpControllerService

车机蓝牙最核心的两个系统服务，**镜像设计**——一个监听 App 发给车机，一个监听车机发给手机。

### 4.1 角色对照

```
AVRCP 协议角色          AOSP 实现                  跑在哪        干嘛
─────────────────────────────────────────────────────────────────────
CT (Controller)    → AvrcpControllerService   → 车机侧    主动控制 + 收元数据
TG (Target)        → AvrcpTargetService       → 手机侧    被控 + 发元数据
```

> Controller（车机）发命令，Target（手机）接命令。名字和"被动/主动"对应。

### 4.2 镜像关系

```
        手机侧                                       车机侧
┌────────────────────────┐              ┌────────────────────────┐
│  AvrcpTargetService    │              │ AvrcpControllerService │
│  (AVRCP TG 角色)        │              │ (AVRCP CT 角色)        │
│                        │              │                        │
│  对上：伪装成            │              │  对上：伪装成           │
│  MediaController       │              │  广播发送者             │
│  (监听 App)            │              │  (通知车机 App)         │
│                        │              │                        │
│  对下：AVRCP TG 协议    │  ◀─蓝牙链路▶ │  对下：AVRCP CT 协议   │
│  (响应车机命令)         │              │  (向手机发命令)         │
└────────────────────────┘              └────────────────────────┘
        ▲                                        ▲
        │ 监听                                    │ 广播
   手机音乐App                              车机播放器App
   (MediaSession)                          (BroadcastReceiver)
```

**核心洞察**：手机侧 TargetService **向上**伪装成 MediaController（监听 App）；车机侧 ControllerService **向上**伪装成广播源（通知车机 App）。两者**向下**都对接 AVRCP 协议栈。

### 4.3 AvrcpTargetService（手机侧）

**两件反向的事**：① 把 App 的 MediaSession 变化翻译成 AVRCP 通知发给车机；② 把车机的控制命令翻译成 MediaButton 派发给 App。

```
AvrcpTargetService
├─ 向上（对接 App）
│   ├─ MediaSessionManager.addOnActiveSessionsChangedListener  ★ 启动时注册
│   ├─ MediaController mMediaController（当前 addressed player）
│   └─ MediaController.Callback mMediaControllerCb
│         ├─ onMetadataChanged()      → App 改了歌名
│         ├─ onPlaybackStateChanged() → App 改了播放状态
│         └─ onQueueChanged()         → 播放列表变化
├─ 中间（决策）
│   ├─ updateCurrentController()  → 切换 addressed player
│   └─ updateCurrentMediaState()  → 打包当前媒体状态
└─ 向下（协议栈）
    ├─ JNI → AVRCP TG 协议
    │   ├─ 发 NOTIFICATION（元数据/状态变化）
    │   ├─ 响应 GetElementAttributes（车机查歌名）
    │   └─ 收 PASSTHROUGH（车机按键）→ 转 MediaButton
    └─ → MediaSessionService.dispatchMediaButton() → App Callback
```

**为什么 App 只调 MediaSession 就能联动？** 因为 AvrcpTargetService 启动时（`Avrcp.start()`）就 `addOnActiveSessionsChangedListener` 注册了全局监听，App 一激活 session，它自动 `registerCallback` 接管。

### 4.4 AvrcpControllerService（车机侧）

**两件反向的事**：① 把手机发来的 AVRCP 通知翻译成广播给车机 App；② 把车机 App 的控制命令翻译成 AVRCP PASSTHROUGH 发给手机。

```
AvrcpControllerService
├─ 向上（对接车机 App）
│   ├─ BluetoothAvrcpController (Binder, @SystemApi)
│   │   ├─ sendGroupNavigationCmd(device, keyCode, state)
│   │   └─ getConnectedDevices()
│   └─ 广播发送
│         ├─ ACTION_TRACK_EVENT + EXTRA_METADATA + EXTRA_PLAYBACK
│         └─ ACTION_CONNECTION_STATE_CHANGED
├─ 中间（状态管理）
│   └─ AvrcpControllerStateMachine（每连接设备一个）
└─ 向下（协议栈）
    ├─ JNI → AVRCP CT 协议
    │   ├─ 发 PASSTHROUGH（按键命令）★
    │   ├─ 发 GetElementAttributes（查歌名）
    │   ├─ 发 GetPlayStatus（查进度）
    │   ├─ RegisterNotification（订阅变化）
    │   └─ 收 NOTIFICATION（手机推的元数据）
    └─ Browse 协议（AVRCP 1.4+，浏览媒体库）
```

### 4.5 AVRCP 协议命令（体现深度）

**CT → TG（车机发给手机）**：

| 命令 | 作用 | 触发时机 |
|------|------|----------|
| PASSTHROUGH | 按键命令(PLAY/PAUSE/NEXT) | 用户点车机按键 |
| GetElementAttributes | 查歌曲属性 | 连接时/切歌时 |
| GetPlayStatus | 查进度(position/duration) | 定期轮询 |
| RegisterNotification | 订阅变化通知 | 连接建立时 |
| Browse | 浏览媒体库(1.4+) | 用户浏览列表 |

**TG → CT（手机发给车机）**：

| 命令 | 作用 | 触发时机 |
|------|------|----------|
| NOTIFICATION | 主动推变化 | 状态变化时 |
| - TRACK_CHANGED | 歌曲变化 | setMetadata 后 |
| - PLAY_STATUS_CHANGED | 播放状态变化 | play/pause 后 |

**关键细节**：NOTIFICATION 是**注册-推送模式**——车机连接时先 `RegisterNotification` 订阅，手机变化时才推送。

### 4.6 数据流镜像对照

**元数据下行（手机 → 车机）**：
```
App.setMetadata → MediaSessionService → AvrcpTargetService(MediaController.Callback)
  → onMetadataChanged → JNI 发 NOTIFICATION ──蓝牙链路──▶
  → AvrcpControllerService JNI 回调 → sendBroadcast(ACTION_TRACK_EVENT) → 车机 App onReceive
```

**控制上行（车机 → 手机）**：
```
车机 App.sendGroupNavigationCmd → BluetoothAvrcpController(Binder)
  → AvrcpControllerService → JNI 发 PASSTHROUGH ──蓝牙链路──▶
  → AvrcpTargetService JNI 回调 → 转 ACTION_MEDIA_BUTTON
  → MediaSessionService.dispatchMediaButton() → App Callback.onMediaButtonEvent
```

**两条链路完全镜像**——这是两个 Service 设计的对称美。

### 4.7 版本演进

| 版本 | 实现 |
|------|------|
| Android 8-9 | 单一 `Avrcp.java`（数千行，职责混杂，实际是 TG 角色） |
| Android 10+ | 拆分：`AvrcpTargetService`（手机）+ `AvrcpControllerService`（车机） |

拆分原因：手机和车机跑不同 Profile Service，按角色拆符合"一个 Profile 一个 Service"原则。

### 4.8 面试金句

> "两个 Service 是镜像设计。手机侧 TargetService 向上伪装成 MediaController 监听 App，向下经 NOTIFICATION 发给车机，反向接收 PASSTHROUGH 转 MediaButton 派发；车机侧 ControllerService 向上伪装成广播源通知车机 App，向下收手机元数据、发控制命令。两端通过 AVRCP 协议帧通信，数据流完全对称——这让手机 App 只关心 MediaSession、车机 App 只关心广播，谁都不用知道对端存在。"

---

## 五、应用层 · 角色1 — 内容提供方（手机音乐App）

**身份**：A2DP Source + AVRCP Target。**最大特点：几乎不碰蓝牙 API**。

### 5.1 核心类（清一色媒体框架，非蓝牙）

```
MediaSession          // 会话本体
MediaMetadata         // 歌名/歌手/封面/时长
PlaybackState         // 播放/暂停/进度
MediaSession.Callback // 接收反向控制
BluetoothAdapter      // 可选，仅查状态
```

### 5.2 要做的四件事

```java
// 1. 创建并激活会话（不激活系统桥接不到）
session = new MediaSession(this, "music");
session.setActive(true);

// 2. 报元数据 → 系统自动经 AVRCP 发给车机
session.setMetadata(new MediaMetadata.Builder()
    .putString(METADATA_KEY_TITLE, "歌名")
    .putString(METADATA_KEY_ARTIST, "歌手")
    .putLong(METADATA_KEY_DURATION, duration)
    .build());

// 3. 报播放状态
session.setPlaybackState(new PlaybackState.Builder()
    .setState(STATE_PLAYING, position, 1.0f).build());

// 4. 设回调，接车机按键
session.setCallback(new MediaSession.Callback() {
    public boolean onMediaButtonEvent(Intent i) { /* 切歌 */ }
});
```

**音频流本身不用管**：App 正常用 MediaPlayer 播放，系统通过 A2DP 自动路由到已连接的蓝牙设备。

### 5.3 设计哲学

> **解耦**：音乐 App 根本不知道连的是蓝牙车机还是有线耳机。只要正确用 MediaSession，蓝牙联动"免费"获得。这是 Android 媒体框架最优雅的设计。

---

## 六、应用层 · 角色2 — 内容消费/控制方（车机播放器）

**身份**：A2DP Sink + AVRCP Controller。**特点：全靠系统 API**（需 platform 签名）。

### 6.1 核心类（大量蓝牙 SystemApi）

```
BluetoothAdapter              // 入口：状态 + getProfileProxy + 配对管理
BluetoothAvrcpController      // @SystemApi：收元数据 + 发控制命令
BluetoothA2dpSink             // @SystemApi：音频连接状态
BluetoothHeadsetClient        // @SystemApi：通话（HFP HF 端）
BroadcastReceiver             // 收 ACTION_TRACK_EVENT 等广播
```

### 6.2 要做的六件事

```java
// 1. 管蓝牙开关
if (!adapter.isEnabled()) { /* 提示/开启 */ }

// 2. 拿 Profile 代理（命脉！没有这步什么 Profile 操作都做不了）
adapter.getProfileProxy(ctx, serviceListener, BluetoothProfile.AVRCP_CONTROLLER);

// 3. 注册广播收元数据（手机 setMetadata → 这里收到）
registerReceiver(rx, new IntentFilter(ACTION_TRACK_EVENT));
// onReceive 里取 EXTRA_METADATA / EXTRA_PLAYBACK 显示

// 4. 反向控制手机（系统应用用 SystemApi 直接调，非反射）
avrcpController.sendGroupNavigationCmd(device, FORWARD, PRESS);

// 5. 配对/连接管理（车机自动重连靠这个）
Set<BluetoothDevice> bonded = adapter.getBondedDevices();

// 6. 可发现性（让手机能搜到车机配对）
adapter.setName("我的车");
```

### 6.3 SystemApi vs 反射（面试加分点）

车机应用是**系统应用**（platform 签名），应直接用 `@SystemApi`：

```java
// ✅ 正确：系统应用直接调
BluetoothAvrcpController controller = (BluetoothAvrcpController) proxy;
controller.sendGroupNavigationCmd(device, keyCode, keyState);
```

博客 demo 用反射（`AvrcpControllerHelper.fixSystemHideApi`）是**为了读者能复现**，生产代码**禁止**：
- 不稳定（每版本 hidden API 名单在变）
- 无编译期检查
- 性能差
- 安全审计过不了

### 6.4 常用控制码

| 操作 | 常量 | 值 |
|------|------|----|
| 播放 | PASSTHROUGH_ID_PLAY | 0x44 |
| 暂停 | PASSTHROUGH_ID_PAUSE | 0x46 |
| 上一首 | PASSTHROUGH_ID_BACKWARD | 0x4C |
| 下一首 | PASSTHROUGH_ID_FORWARD | 0x4B |

---

## 七、两角色对照（面试核心表）

| 维度 | 角色1：手机（提供方） | 角色2：车机（消费/控制方） |
|------|---------------------|------------------------|
| A2DP | Source（发音频） | Sink（收音频） |
| AVRCP | Target（被控+发元数据） | Controller（控制+收元数据） |
| 主力 API | **MediaSession**（非蓝牙） | **BluetoothAvrcpController**（蓝牙 SystemApi） |
| API 可见性 | 公开 SDK | @SystemApi / @Hide |
| 元数据 | 主动 `setMetadata` | 被动注册广播收 |
| 控制 | 被动 `Callback` 接收 | 主动 `sendCmd` 发送 |
| BluetoothAdapter 用途 | 可选（查状态） | **核心**（getProfileProxy + 配对 + 可发现） |
| 签名 | 普通 | **platform 签名** |
| 开发难度 | ★（简单，解耦） | ★★★★（系统签名+SystemApi+兼容） |

> **金句**：手机侧 BluetoothAdapter 是"发起者"入口，车机侧是"**Profile 代理工厂 + 状态观察站**"——同一把钥匙，开不同的门。

---

## 八、数据流闭环（车载音乐完整链路）

```
        ┌──────────────── 手机侧 ────────────────┐
        │  音乐App ──▶ MediaSession              │
        │                  │ metadata/state       │
        │                  ▼                      │
        │           MediaSessionService           │
        │                  │ 通知                 │
        │                  ▼                      │
        │   Avrcp(作为MediaController)            │
        └──────────────────┬─────────────────────┘
                           │ AVRCP 协议 (蓝牙链路)
        ┌──────────────────▼─────────────────────┐
        │            车机侧                       │
        │  AvrcpControllerService                │
        │       │ 广播 ACTION_TRACK_EVENT        │
        │       ▼                                │
        │  车机App(BroadcastReceiver) 显示歌名    │
        │       │ 用户点"下一首"                   │
        │       ▼                                │
        │  sendGroupNavigationCmd                │
        └──────────────────┬─────────────────────┘
                           │ PASSTHROUGH 命令 (反向)
        ┌──────────────────▼─────────────────────┐
        │           手机侧                        │
        │  Avrcp 收到 → 转 MediaButton            │
        │       ▼                                 │
        │  MediaSession.Callback.onMediaButtonEvent│
        │       ▼                                 │
        │  音乐App 执行切歌 → setMetadata(新歌)    │
        └────────────────────────────────────────┘
```

**三条独立数据路径**（面试分开讲）：
1. **音频流(A2DP)**：手机播放器 → 系统路由 → 蓝牙链路 → 车机喇叭（App 无感）
2. **元数据(AVRCP)**：MediaSession.setMetadata → Avrcp 自动桥接 → 车机广播（App 主动发）
3. **反向控制**：车机 sendCmd → PASSTHROUGH → 手机 Callback（车机主动发）

---

## 九、应用开发实战要点

### 9.1 权限演进（必问）

| Android 版本 | 扫描所需权限 |
|--------------|-------------|
| < 9 (API 28) | `ACCESS_COARSE_LOCATION` |
| 10-11 (29-30) | `ACCESS_FINE_LOCATION` |
| 12+ (31+) | `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT`（无需位置权限） |

### 9.2 经典蓝牙 vs BLE

| 维度 | 经典蓝牙 (BR/EDR) | 低功耗蓝牙 (BLE) |
|------|------------------|-----------------|
| 连接 | RFCOMM/Socket | GATT |
| 传输 | 大数据、音频流 | 小数据、传感器 |
| 耗电 | 高 | 低 |
| Profile | A2DP/HFP/AVRCP | GATT 自定义 Service |
| 典型 | 耳机/车机/文件传输 | 手环/beacon |

### 9.3 常见坑点

1. **扫描与连接冲突**：连上 A2DP 后必须 `cancelDiscovery()`，否则音乐会卡（天线争用）
2. **主线程禁止 IO**：蓝牙 socket I/O 要放子线程
3. **配对 ≠ 连接**：配对=持有 link key，连接=建立 RFCOMM 通道可传数据
4. **状态异步**：`enable()` 后不能立即用，要等 `ACTION_STATE_CHANGED` 为 `STATE_ON`
5. **隐藏 API**：生产用 SystemApi + platform 签名，反射只用于 demo

### 9.4 BluetoothManager 什么时候用

| 场景 | 入口 |
|------|------|
| 经典蓝牙(车机/耳机/SPP) | `BluetoothAdapter` 够用，不用 BluetoothManager |
| BLE GATT Client（连手环） | 建议从 `BluetoothManager.getAdapter()` 入口 |
| BLE GATT Server（手机当外设/beacon） | **必须** `BluetoothManager.openGattServer()` |

> 经典蓝牙用 Adapter，BLE 用 Manager。系统服务 `BluetoothManagerService` 应用层不直接接触，通过 Binder 间接访问。

---

## 十、面试自测题

**Q1: 蓝牙涉及哪几个进程？为什么这么设计？**
> 三个：应用进程（Binder 客户端）、system_server（BluetoothManagerService + MediaSessionService）、com.android.bluetooth（AdapterService + 各 Profile + JNI 协议栈）。隔离设计保证蓝牙栈崩溃不影响系统主进程，权限收敛由系统统一鉴权。

**Q2: 车机怎么显示手机正在播放的歌曲？**
> 手机 App 用公开的 MediaSession.setMetadata 发元数据 → MediaSessionService 通知 → 系统蓝牙 Avrcp 作为 MediaController 收到 → 经 AVRCP 协议发给车机 → 车机注册广播 ACTION_TRACK_EVENT 接收。手机侧完全不用蓝牙 API。

**Q3: 为什么车机要用 SystemApi 而不是普通 API？**
> 车机是 Controller 角色，BluetoothAvrcpController 是 @SystemApi/@Hide 的。车机应用本身是系统应用带 platform 签名，应直接用 SystemApi。反射只是博客 demo 为了读者复现，生产禁止（不稳定、无编译检查、过不了安全审计）。

**Q4: 手机侧和车机侧的开发难度为什么差这么多？**
> 角色不对称。手机是 Target/Source，用公开 MediaSession 主动推送，系统自动桥接，解耦设计；车机是 Controller/Sink，要用隐藏 BluetoothAvrcpController 被动接收 + 反射/SystemApi 主动控制，强耦合。这也是车载蓝牙开发门槛高的原因。

**Q5: 配对和连接的区别？**
> 配对=交换 link key（可认证加密），连接=建立 RFCOMM/GATT 通道可传数据。Android 要求先配对才能建 RFCOMM 连接。

**Q6: 蓝牙开启为什么是异步的？**
> enable() 经 Binder → BluetoothManagerService → bind AdapterService → JNI → HCI → 芯片，跨三个进程+硬件。状态通过广播 ACTION_STATE_CHANGED 异步回来，不能调完立即用。

**Q7: 经典蓝牙和 BLE 怎么选？**
> 看数据量与功耗。音频流、大文件选经典蓝牙（A2DP/SPP）；周期性小数据、纽扣电池选 BLE（GATT）。车机蓝牙音乐是经典蓝牙的 A2DP+AVRCP。

**Q8: 三条数据路径分别是什么？**
> ①音频流(A2DP)系统自动路由，App 无感；②元数据(AVRCP)App 主动 setMetadata，系统桥接；③反向控制车机主动 sendCmd，手机 Callback 接收。App 只在 MediaSession 这一个点参与。

**Q9: AvrcpTargetService 和 AvrcpControllerService 是什么关系？**
> 镜像设计。手机侧 TargetService 向上伪装成 MediaController 监听 App 的 MediaSession 变化，向下经 AVRCP NOTIFICATION 发给车机；反向接收车机 PASSTHROUGH 转 MediaButton 派发。车机侧 ControllerService 向上伪装成广播源通知车机 App，向下收手机元数据发控制命令。两端通过 AVRCP 协议帧（PASSTHROUGH/NOTIFICATION）通信，数据流完全对称。这让手机 App 只关心 MediaSession、车机 App 只关心广播，谁都不用知道对端存在。

**Q10: 为什么手机 App 只调 MediaSession 就能联动车机？**
> AvrcpTargetService 启动时就 addOnActiveSessionsChangedListener 注册了全局监听。App 一调 setActive(true)，系统自动拿到 MediaController 并 registerCallback。之后 App 的 setMetadata/onPlaybackState 变化都由 TargetService 的 Callback 捕获，打包成 AVRCP NOTIFICATION 发给车机。App 完全无感知蓝牙存在。

**Q11: 两台手机同时连车机 / 一台手机两个音乐 App，怎么寻址？**
> 两级寻址。多设备：每个 AVRCP 命令带 BluetoothDevice 参数，A2DP 同一时刻通常单活跃音频源。多 App：靠 MediaSessionService 优先级栈，按"正在播放 > 最近活跃"自动选 addressed player，Avrcp 监听 onActiveSessionsChanged 自动切换 registerCallback。用户切 App 播放，系统自动寻址。

---

## 附：源码定位速查（cs.android.com）

| 关注点 | 路径 |
|--------|------|
| 蓝牙服务启动 | `frameworks/base/services/java/com/android/server/SystemServer.java` |
| 蓝牙管理服务 | `packages/apps/Bluetooth/src/com/android/bluetooth/btservice/BluetoothManagerService.java` |
| 适配核心服务 | `packages/apps/Bluetooth/src/com/android/bluetooth/btservice/AdapterService.java` |
| 应用层入口 | `frameworks/base/core/java/android/bluetooth/BluetoothAdapter.java` |
| AVRCP 老版(Android 8-9) | `packages/apps/Bluetooth/src/com/android/bluetooth/avrcp/Avrcp.java` |
| AvrcpTargetService(手机,10+) | `packages/apps/Bluetooth/src/com/android/bluetooth/avrcp/AvrcpTargetService.java` |
| AvrcpControllerService(车机) | `packages/apps/Bluetooth/src/com/android/bluetooth/avrcpcontroller/AvrcpControllerService.java` |
| MediaSession | `frameworks/base/media/java/android/media/session/MediaSession.java` |
| MediaSessionService | `frameworks/base/services/core/java/com/android/server/media/MediaSessionService.java` |

> 源码以 Android 8-9 为主线（车机开发时期），高版本 Avrcp 拆分为 `AvrcpTargetService`/`AvrcpControllerService`，MediaSession 机制基本不变。

---

## 电梯陈述（面试开场可用）

> "蓝牙开发要分**两个层面**看。**系统层**是一套实现，跑在三个进程里，负责协议栈、Profile Service、音频路由，还有最关键的 MediaSession↔AVRCP 自动桥接，它是两端共享的中间件。
>
> **应用层有两个对称角色**：手机侧是内容提供方（Source/Target），主力 API 是公开的 MediaSession，几乎不碰蓝牙类，体现解耦设计；车机侧是消费/控制方（Sink/Controller），主力 API 是 @SystemApi 的 BluetoothAvrcpController，需要 platform 签名。
>
> 我做车机蓝牙音乐时主要在角色2，但要懂角色1和系统层，因为联调时要知道对端在干什么、bug 在哪一层。这种全链路理解让我能快速定位跨进程问题，而不是只会调 API。"