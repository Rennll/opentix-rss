# OPENTIX 全新登場 RSS Feed

每週一 13:00 自動抓取 [OPENTIX 全新登場](https://www.opentix.life/topic/1378018195831590913) 的本週新增節目，產出 RSS feed。已推送過的節目不會重複出現。

## 訂閱網址

部署完成後，訂閱以下網址：

```
https://<你的GitHub帳號>.github.io/<repo名稱>/feed.xml
```

例如帳號為 `alice`、repo 名稱為 `opentix-rss`，則為：

```
https://alice.github.io/opentix-rss/feed.xml
```

---

## 部署步驟

### 1. 建立 GitHub Repository

登入 GitHub，點右上角 **+** → **New repository**。

- Repository name：`opentix-rss`（或任意名稱）
- Visibility：**Public**（GitHub Pages 免費方案需為 Public）
- 不需要勾選任何初始化選項

### 2. 推上專案檔案

在本機將這個專案目錄初始化並推上去：

```bash
cd opentix-rss
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo名稱>.git
git push -u origin main
```

### 3. 開啟 GitHub Pages

到 repo 頁面，進入 **Settings → Pages**。

- Source 選 **Deploy from a branch**
- Branch 選 `main`，Folder 選 `/docs`
- 按 **Save**

等約 1 分鐘後，Pages 網址會顯示在同一頁面上。

### 4. 手動跑一次確認

到 repo 頁面，進入 **Actions → 更新 OPENTIX RSS Feed**，點右側 **Run workflow → Run workflow**。

等執行完畢後，確認：
- `docs/feed.xml` 有被產出
- `docs/seen_ids.json` 有被產出（記錄本次所有節目 ID）
- Actions log 顯示「本週新增：N 筆」

### 5. 訂閱 RSS

將你的 feed 網址加入任何 RSS reader，例如：
- [Reeder](https://reederapp.com/)
- [NetNewsWire](https://netnewswire.com/)
- [Feedly](https://feedly.com/)
- [Inoreader](https://www.inoreader.com/)

之後每週一 13:00 會自動執行，只有新上架的節目會出現在 feed 裡。

---

## 檔案說明

```
.
├── scrape.py                        # 主程式：抓 API、比對新舊、產出 RSS
├── requirements.txt
├── docs/
│   ├── feed.xml                     # RSS feed（由 Actions 自動更新）
│   └── seen_ids.json                # 已推送節目 ID 清單（由 Actions 自動更新）
└── .github/
    └── workflows/
        └── update-feed.yml          # Actions 排程設定（週一 13:00）
```

## 注意事項

- 第一次執行會把當時 API 上的所有節目（約 200+ 筆）全部推送，之後每週只推新增的
- 若 feed 是空的但 log 顯示有抓到節目，代表本週沒有新上架節目，屬正常現象
- OPENTIX 使用官方 API（非 HTML 爬蟲），相對穩定，不易因前端改版而失效