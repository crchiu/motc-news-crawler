# MOTC 交通部新聞稿下載器（motc_press_downloader）

本專案用於下載交通部網站「交通新聞稿」所有新聞內容，並將每則新聞存成一個 Markdown 檔案於 `data/` 目錄下。

- 新聞稿首頁（列表）：https://www.motc.gov.tw/ch/app/news_list?lang=ch&folderName=ch&id=14
- 輸出格式：每篇一個 `.md`
- 檔名規則：`發布單位_日期_標題.md`
- 續抓/停止機制：每篇下載前先檢查 `data/` 是否已存在同名檔案；若已存在，視為該日期以前新聞已下載完成，立即停止整體下載流程。

---

## 1. 環境需求

- 作業系統：Windows / macOS / Linux 皆可
- Python：建議 3.10 以上
- 使用 Miniconda
- Conda 環境名稱：`motc-crawler`

---

## 2. 建立與啟用 Conda 環境

### 2.1 建立環境（首次）
```bash
conda create -n motc-crawler python=3.11 -y
```

### 2.2 啟用環境
```bash
conda activate motc-crawler
```

---

## 3. 安裝套件

專案使用 `requirements.txt` 管理 Python 依賴。

```bash
pip install -r requirements.txt
```

`requirements.txt` 內容應包含：
- requests
- beautifulsoup4
- lxml

---

## 4. 執行方式

### 4.1 下載所有新聞（從最新一路往舊）
```bash
python main.py
```

執行完成後，新聞稿 Markdown 檔會輸出在：
- `./data/`

### 4.2 測試用：限制最多抓取頁數（建議先跑 1~2 頁驗證）
```bash
python main.py --max-pages 2
```

### 4.3 調整抓取間隔（避免對站台造成壓力）
預設每次請求間隔 `0.5` 秒，可自行調整：

```bash
python main.py --sleep 1.0
```

---

## 5. 續抓 / 停止邏輯說明（重要）

本專案的策略是「增量下載」：

1. 程式會從列表第一頁（最新）開始逐頁往後抓。
2. 每篇新聞在下載前，會先依規則產生目標檔名：  
   `發布單位_日期_標題.md`
3. 若 `data/` 目錄下已存在該檔案，代表你曾下載過該篇，且依列表排序推定 **該日期以前的新聞已下載完成**，因此程式會：
   - 立即停止下載流程（不再抓更舊的頁面與新聞）

注意：此機制假設「列表排序為由新到舊」且你之前下載是連續完整的。若你曾刪除部分舊檔或中間漏抓，可能會提早停止；此情境建議改成「存在就跳過、不停止」的策略（可再調整程式）。

---

## 6. 產出檔案格式

每篇新聞輸出為 Markdown，結構大致如下：

- 標題（H1）
- 發布日期、發布單位、新聞類別（若能解析）、業務分類（若能解析）
- 原文連結
- 正文

---

## 7. 常見問題排除

### 7.1 解析到的新聞數量為 0
- 可能網站 HTML 結構更動或被導向至不同語系頁面
- 建議先用瀏覽器開啟列表頁確認可正常瀏覽，再回報終端機輸出與網址

### 7.2 無法自動偵測分頁
- 若網站分頁不是透過 GET 參數（可能改成表單 POST），程式會提示無法偵測
- 請將「列表頁 HTML（含 pagination 區塊）」或瀏覽器開發者工具看到的分頁請求資訊貼出，以便調整抓取方式

---

## 8. 退出環境

```bash
conda deactivate
```
