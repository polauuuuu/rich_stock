# 驗證紀錄

2026-11-04，本機 Windows / Docker Desktop Linux containers。

- Python：18 個 pytest 測試通過，覆蓋形態連續日、缺失交易日、下一開市成交、跳空及同日雙觸發、成本、資金／持倉上限、標籤跨界清除、API 驗證、SIP 分頁、名單過濾、重啟／取消及拆股快取完整替換。
- Frontend：2 個結果載入測試通過；TypeScript 檢查及 Vite production build 通過。
- Docker image 建置成功；單 container 的 API、Nginx 及健康檢查成功；端口僅綁定 127.0.0.1:6001／6002。重啟後示範數據及完成工作結果仍保存。
- HTTP 端到端：Nginx 代理 health、scan、CSV export、live 無資料錯誤；Logistic Regression 及 Gradient Boosting 均完成背景訓練，結果保存並可重載。合成示範分段樣本數為 665／232／220；此數字僅驗證流程，不代表市場優勢。
- 瀏覽器：候選股搜尋、點選 NVDA 後價量圖連動、提交預設回測、完成資產曲線、讀取已保存 ML 結果；桌面及窄版響應式佈局已檢視。瀏覽器 QA 發現預設數字欄位 step 與 min 不對齊阻擋提交，已修正並重新提交成功。
- 公開 Nasdaq Trader 兩份即時目錄實際抓取及解析成功；當次約 5,891 項保留、7,383 項排除（目錄會更新，分類屬啟發式）。
- 初版沒有 Alpaca API key；用戶其後自行設定憑證，已重新建立 container，實際 SIP 下載 AAPL、MSFT、NVDA 成功，共 633 支日線，2026-01-02 至 2026-11-03，三隻均無缺數；憑證未顯示或提交。沒有執行任何真實交易。

## 光暗模式及 K 線更新

- 19 個後端測試及 4 個前端測試通過，包括元旦假期日期邊界回歸、升跌配色及 OHLC body/wick 幾何。
- 加入記憶光暗選擇、紅綠 K 線、同步成交量顏色、OHLC hover 及日期範圍控制。
- 獨立覆核發現換股時舊圖可能顯示於新代號，已在新請求開始時清空 bars；非同步失效請求不會覆蓋新結果。

## 獨立覆核

獨立 reviewer 檢視後端、前端及容器設定，提出四項重要問題；全部已有回歸驗證：

1. 拆股更新只覆蓋前半歷史會混入舊單位：現在刷新全保存日期範圍，完整替換單股票歷史；缺失已保存日期時拒絕覆蓋。
2. 結果首次載入失敗後無法重試：現在只在成功接受結果後記為載入，並追蹤 in-flight 請求。
3. 取消與完成競爭令狀態卡在 cancelling：現在串行保護取消及完成，拒絕修改終止狀態。
4. 初次示範生成中斷留下部分股票：現在以原子完成標記判斷初始化，重啟可補全，載入只包含完成名單。

## 實作選擇

- 在用戶指定 checkout 建立 feature branch，保留 main 起點；沒有新增 worktree。代價是沒有第二份 checkout 隔離。
- 已獲用戶明確 go ahead，按已確認設計原地實作，沒有再要求計劃批准。
- 以完整刷新已保存歷史取代只 append 新日期，以保證拆股調整一致。代價是更新下載量較大。
- 第一版使用單次 chronological holdout，尚未做 rolling walk-forward；README 及 UI 不聲稱已證明可實際獲利。

已知非阻擋項：Vite 提示 chart bundle 超過 500 kB；API 測試工具有 upstream deprecation warning，測試通過。
