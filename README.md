# Switch → Xbox Controller Translator

將 Nintendo Switch Pro Controller / Switch 2 Pro Controller 透過 USB 連接，即時轉譯為虛擬 Xbox 360 手把，讓 Windows Xbox App 和所有 XInput 遊戲直接使用。

**版本：v1.5**（輕量熱路徑：預設 lite UI、報告佇列排空、ViGEm 變更才送出）

## 系統需求

- **Windows 10/11**
- **Python 3.8+**（[下載](https://python.org)）
- **USB-C 傳輸線**（資料線，不是純充電線）
- **ViGEmBus 驅動**（虛擬 Xbox 手把）
- **HidHide 驅動**（建議；隱藏實體手把，避免遊戲偵測到雙手把）

## 支援的控制器

| 控制器 | 支援狀態 |
|--------|----------|
| Switch Pro Controller (原版) | ✅ 完整支援（USB） |
| Switch 2 Pro Controller | ✅ 支援（USB 有線 + WebUSB 自動喚醒） |

## 快速開始

### 一鍵啟動

雙擊 `start.bat`（會請求系統管理員權限，供 HidHide 使用），它會自動：

1. 建立 / 修復 Python 虛擬環境  
2. 安裝依賴  
3. 以管理員身分啟動轉換程式  

### 手動執行

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動（預設：Xbox 佈局 = A→A, B→B）
python main.py

# Nintendo 佈局（位置對應，A/B X/Y 互換）
python main.py --layout nintendo

# 調整搖桿死區（預設 5%，範圍 0.0–0.99）
python main.py --deadzone 0.1

# 不要反轉搖桿 Y 軸（預設會反轉以符合 XInput 上=正）
python main.py --no-invert-y

# 介面：lite=單行（預設，最順） / full=完整儀表板 / off=無狀態列
python main.py --ui lite
python main.py --ui full
python main.py --ui off

# 不隱藏實體手把（不建議；遊戲可能雙手把衝突）
python main.py --no-hide

# 強制解除 HidHide 隱藏（恢復 Steam Input 等）
python main.py --unhide
# 或雙擊 unhide.bat
```

## 按鈕佈局

### Xbox 佈局（預設）— 標籤對應

按鈕標籤直接對應：Switch A → Xbox A（物理位置與 Xbox 手把不同）。

### Nintendo 佈局 — 位置對應

物理位置相同的按鈕對應相同遊戲動作：

```
Switch 控制器：        Xbox 對應：
    X  (top)    →     Y  (top)
Y (left) A (right) → X (left) B (right)
    B  (bottom) →     A  (bottom)
```

未映射的 Switch 專用輸入：`Capture`、Switch 2 背鍵 `GL`/`GZ`（XInput 無對應）。

## 驅動安裝

### ViGEmBus

1. 執行 `install_driver.bat`，或手動安裝專案內的 `ViGEmBus_1.21.442.exe`  
2. 或從 [ViGEmBus Releases](https://github.com/nefarius/ViGEmBus/releases) 下載  
3. 建議安裝後重新開機  

### HidHide（強烈建議）

1. 執行 `install_hidhide.bat`，或安裝 `HidHide_Setup.exe`  
2. **必須重新開機**  
3. 平常用 `start.bat` 即可；程式會自動把 Nintendo 裝置藏起來，並把目前的 Python 加入白名單  
4. 若要恢復實體手把可見性：執行 `unhide.bat` 或 `python main.py --unhide`  

可透過環境變數指定 CLI 路徑：

```bash
set HIDHIDE_CLI=C:\Path\To\HidHideCLI.exe
```

## Switch 2 自動喚醒

Switch 2 Pro Controller 有時需要 USB Bulk 喚醒才會開始送出輸入。程式在偵測到 **PID 0x2069** 且一段時間無輸入時會：

1. 啟動本機 WebUSB 頁面（`http://127.0.0.1:58249`）  
2. 用 Chrome / Edge 開啟並送出喚醒指令  
3. 首次使用需在瀏覽器中 Pair 一次  

原版 Pro Controller **不會**誤觸此流程。

## 疑難排解

### ViGEmBus 驅動未安裝

出現「Failed to create virtual controller」時，請安裝 ViGEmBus（見上方）。

### 找不到控制器

1. 確認是 **USB-C 資料線**  
2. 換 USB 埠  
3. 裝置管理員確認有 Nintendo HID 裝置  

### 遊戲在鍵盤 / 手把之間狂切

通常是實體 + 虛擬雙手把：請用管理員執行並安裝 HidHide，不要加 `--no-hide`。

### Steam 抓不到手把

執行 `unhide.bat` 解除隱藏。

### 按鈕 / 搖桿方向不對

```bash
python main.py --layout nintendo
python main.py --no-invert-y
```

## 測試

不需接上手把即可跑單元測試：

```bash
python -m unittest discover -s tests -v
```

## 技術細節

- `hidapi` 讀取 Switch Pro USB HID 報告  
- Nintendo USB 握手：`80 01 → 02 → 03 → 02 → 04`，輸入模式 `0x30` @ ~120Hz  
- Switch 2 使用報告 `0x09` 位元配置 + WebUSB Bulk 喚醒  
- `vgamepad`（ViGEmBus）建立虛擬 Xbox 360  
- HidHide 隱藏實體裝置，避免雙輸入  
- ZL/ZR 數位觸發 → 類比 0 或 255  
- 搖桿 12-bit (0–4095) → 16-bit signed，徑向死區 + 預設 Y 軸反轉  
- 遊戲震動請求會轉發到實體手把  

## 專案結構

```
main.py                 # CLI 進入點與主迴圈
controller_reader.py    # HID 連線、握手、報告解析
mapper.py               # Switch → Xbox 映射
xbox_emulator.py        # 虛擬 Xbox 360
hidhide.py              # 裝置隱藏
auto_wake.py / wake.html # Switch 2 WebUSB 喚醒
start.bat / unhide.bat  # 一鍵啟動 / 解除隱藏
tests/                  # 單元測試
```
