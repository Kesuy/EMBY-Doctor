# Emby Media Library Batch Processor

**Emby 媒体库批处理** 是一个面向 Emby 的 Windows 桌面批处理工具，用于对指定媒体库执行常见的元数据清理与检查操作。

首个版本集成三个功能：

1. **删除指定媒体库涉及演员的 Primary 头像**
2. **扫描指定媒体库中没有 Actor 信息的影片**
3. **删除指定媒体库所有影片的 Director 信息**

> 删除类操作都必须先扫描预览，再由用户二次确认后执行。

## UI 设计

窗口顶部是三个功能共用的 Emby 连接信息：

- Emby 地址
- API Key
- HTTPS 证书校验
- HTTP 超时
- 测试连接

三个子功能拥有各自独立的 **媒体库 ID** 设置，互不覆盖。每个功能都有独立的输出表格。

## 设置保存位置

Windows EXE 运行时，所有设置保存在 **EXE 同目录**：

```text
EmbyMediaLibraryBatchProcessor.exe
settings.json
backups/
reports/
```

- `settings.json`：Emby 通用连接信息、三个功能各自的媒体库 ID 等设置。
- `backups/`：删除导演前生成的完整影片元数据 JSON 备份。
- `reports/`：无演员影片扫描结果导出的 CSV。

`settings.json` 中的 API Key 为明文保存，仅供本机使用，请勿上传、提交或分享该文件。

## 三个功能

### 1. 删除演员头像

先扫描指定媒体库中存在 Primary 头像的演员，在输出列表确认后再执行删除。

需要特别注意：Emby 的 Person/演员对象是全局共享的。如果某演员同时存在于其他媒体库，删除该 Person 的 Primary 图片后，其他媒体库中的同一演员头像也会消失。

### 2. 扫描无演员影片

扫描指定媒体库中的 Movie；可选同时扫描 Video。判定逻辑为影片 `People` 中不存在 `Type=Actor` 的人物。

结果直接显示在 UI 表格中，并可导出 UTF-8 BOM CSV，方便 Excel 打开。

### 3. 删除导演信息

先列出包含 `Type=Director` 的影片。执行删除时：

1. 获取影片完整元数据；
2. 在 EXE 同目录的 `backups/` 下保存 JSON 备份；
3. 仅移除 `Director`；
4. 保留 Actor、Writer、Producer 等其他人物信息；
5. 更新回 Emby。

如果影片旁的 NFO 仍包含 `<director>`，以后刷新元数据时导演信息可能再次被导入。

## 开发运行

要求 Python 3.10+。

启动桌面 UI：

```bash
python emby_gui.py
```

CLI 仍保留：

```bash
python emby_batch.py --help
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 打包

Windows EXE 使用 PyInstaller：

```powershell
python -m pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --windowed `
  --name EmbyMediaLibraryBatchProcessor `
  emby_gui.py
```

项目的 GitHub Actions 会在 PR / main 上自动运行测试并构建 Windows EXE artifact；推送 `v*` tag 时自动生成 GitHub Release。

## License

MIT
