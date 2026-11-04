# rich_stock

互動式美股研究 Dashboard：連跌縮量掃描、價量圖、歷史回測及機器學習排名。

本機美股研究工具，只使用 Alpaca SIP 真實歷史數據，沒有示範模式，不執行交易。

## 啟動（建議 Docker）

需要已啟動的 Docker Desktop（Linux containers）。在專案目錄執行：

```powershell
Copy-Item .env.example .env
# 在 .env 填入你自己的 Alpaca 憑證。
docker compose up --build -d
```

- Dashboard：[http://localhost:6002](http://localhost:6002)
- API 文件：[http://localhost:6001/docs](http://localhost:6001/docs)
- API 健康狀態：[http://localhost:6001/api/health](http://localhost:6001/api/health)

一個 container 內由 Supervisor 管理兩個服務；Nginx 將前端 `/api` 請求代理到 Python。端口僅對本機公開。首次使用需下載真實數據；下載前不會生成或顯示合成數據。

```powershell
docker compose logs -f            # 查看日誌
docker compose ps                 # 查看健康狀態
docker compose down               # 停止；保留研究 volume
docker compose up -d              # 再次啟動
```

`research-data` named volume 保存日線、股票池及工作結果；更新 image 不會刪除數據。`docker compose down -v` 會刪除研究資料，平日不要加 `-v`。

## 使用流程

1. **市場掃描**：選擇截至日期及下跌定義，修改連跌／縮量日數、最低價格、20 日平均成交金額，按「掃描市場」。留空日期會用資料最新日期；非交易日會用之前最後一個有資料的交易日。
2. **檢視個股**：點候選股票；圖表可 hover 查看價量、拖曳底部範圍。欄位可排序，代號可搜尋，CSV 匯出完整候選集。
   個股使用 OHLC K 線及成交量柱：收市高於開市為綠、低於開市為紅、相同為灰。可選 30／60／120 日或全部，以開始／結束滑桿調整範圍；hover 顯示開高低收及成交量。表格回報按標示期間計算，與單支 K 線的開收方向可能不同。頂部太陽／月亮按鈕切換光暗模式，瀏覽器會記住選擇。
3. **策略回測**：輸入日期、持有期、止賺止蝕及每邊成本，執行背景工作。完成後查看資產曲線、回撤、交易及未平倉數目。
4. **ML 實驗室**：選 Logistic Regression 或 Gradient Boosting，執行時間分段實驗。查看正例基準、PR-AUC、Top-K 命中率及相同測試候選池的組合比較。分數未校準，只供排名。
5. **數據管理**：填好後端憑證並重新建立 container 後，股票欄留空會下載完整上市名單；也可指定代號下載子集。多年份、全股票池下載需時，進度／取消／錯誤會顯示於頁面。

若修改 `.env`，用 `docker compose up -d --force-recreate` 重新讀取環境變數；不要將 key 放到前端或提交 Git。真實模式未有數據／出錯時會顯示錯誤，唔會偷偷轉示範數據。
單純 `docker compose restart` 不會重新讀取修改後的 `.env`。「API 已設定」只表示憑證存在；下載工作完成、真實日線記錄增加，先代表實際數據權限已驗證。

## 研究方法與邊界

- 預設「收市連跌＋連續陰燭」：三日收市逐日下跌，而且三日均收市低於開市，圖上最後三支必須紅色。另可選「只計收市逐日下跌」或「只計連續紅色陰燭」。後者不要求低於上日收市。
- 收市逐日下跌定義為 `C[t] < C[t-1] < C[t-2] < C[t-3]`；三日縮量為 `V[t] < V[t-1] < V[t-2]`。按 XNYS 交易日曆驗證連續日期，缺失交易日不會補成訊號。
- 特徵只用訊號當日及之前資料：3／20 日回報、相對 20 日成交量、均線距離、波幅及平均成交金額。API 回傳最近 300 支日線供圖表使用。
- 訊號收市確認，最早下一交易日開市買入；每日候選以縮量比例由低至高排序（ML 以分數排序），最多選 Top-K。持倉等額預算、整數股、受現金及上限限制；不重複持有同一股票。前日淨值決定預算，當日賣出所得不供當日開市買入。
- 每邊成本以 bps 計（10 bps = 0.1%），合併假設差價、滑價及費用；止蝕跳空以開市價成交。同支日線觸及止賺及止蝕時保守先止蝕；持有期包括入場當日。
- 未平倉以最後報價估值，保留在組合回報內，但不計入交易勝率；缺失報價不假設可退出，最後報價可能過時。沒有模擬市場衝擊、成交量限制、股息現金或真實停牌／退市清算，因此不是可直接交易的績效保證。
- 真實 bars 使用 `feed=sip`、`adjustment=split`，價格及成交量保持同一拆股調整單位；回測股數是調整單位下的模擬股數，歷史實際股數／整數股成交可能不同。沒有股息總回報。為避免新增拆股令快取前後單位不一致，更新會重抓該保存期間，並逐隻股票原子寫入，不是單純 append 最近幾日。
- Nasdaq Trader 當前名單排除 ETF、測試證券及名稱可識別的 warrant／preferred／unit 等。分類屬啟發式，並非權威歷史普通股主檔，可能包含 ADR、封閉式基金等；不包含完整 OTC／歷史退市名單。歷史回測存在生存者偏差。
- Alpaca 免費歷史 SIP 查詢避開最近 15 分鐘，只保留已結束交易日，包含美東夏令時間／提早收市處理。API 分頁、限速及網絡暫時失敗有重試；缺數股票列於下載結果。
- ML 標籤為下一交易日開市入場、持有 H 個交易日後收市賣出，扣成本後有冇正回報；缺交易日標籤排除。按候選日期 60%／20%／20% 切分，清除標籤跨分界樣本，預處理只在訓練段擬合。每段至少 30 筆、正負兩類，否則明確拒絕訓練。第一版是單次時間留出驗證，未做完整 walk-forward 或參數搜尋。
- ML 及純規則比較只使用同一批測試期、有完整未來標籤的候選訊號，固定持有期並停用止賺止蝕；獨立回測頁仍按用戶止賺止蝕設定。PR-AUC 應與測試正例比例比較；結果僅根據已下載真實數據計算。
- 同一時間只執行一項重型工作；取消會在當前可中斷步驟停止，模型擬合可能需等當步完成。重啟後未完成工作標記 interrupted；已完成股票檔案保留，下次重新提交下載。工作結果保存於 SQLite，頁面展示最近 40 項。

## 架構

- Python API：port 6001
- React 前端：port 6002
- 單一 Docker container，volume 保存研究資料

設計文件：[股票研究 Dashboard](docs/superpowers/specs/2026-11-04-stock-research-design.md)

```text
backend/research.py    因果特徵、組合回測及時間分段 ML
backend/providers.py  Nasdaq Trader 目錄、Alpaca SIP 分頁下載
backend/store.py      SQLite 及 Parquet 本機保存
backend/jobs.py       單工作背景執行及取消
backend/main.py       FastAPI 路由與輸入驗證
frontend/src/         React dashboard、Recharts 互動圖表
deploy/               Nginx 及 Supervisor 設定
tests/                核心研究、API、下載及工作持久化測試
```

## 不用 Docker 開發

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# 真實模式需先在目前 shell 設定 ALPACA_API_KEY、ALPACA_SECRET_KEY；不自動讀 .env。
.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 6001
```

另一個 terminal：

```powershell
cd frontend
npm ci
npm run dev
```

驗證：

```powershell
.venv/Scripts/python -m pytest -q
cd frontend
npm run build
```

資料來源文件：[Alpaca SIP FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)、[批量 Bars API](https://docs.alpaca.markets/us/reference/stockbars)、[Nasdaq 目錄欄位](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)。

## 版本管理

每個完成並驗證的階段建立一個 commit，方便檢視差異及回退。
使用 `git log --oneline` 查看紀錄；已提交的變更可用 `git revert <commit>` 建立反向提交。
