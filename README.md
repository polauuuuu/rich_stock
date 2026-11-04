# rich_stock

互動式美股研究 Dashboard：連跌縮量掃描、價量圖、歷史回測及機器學習排名。

目前狀態：設計階段，尚未實作應用程式。

## 預定架構

- Python API：port 6001
- React 前端：port 6002
- 單一 Docker container，volume 保存研究資料

設計文件：[股票研究 Dashboard](docs/superpowers/specs/2026-11-04-stock-research-design.md)

## 版本管理

每個完成並驗證的階段建立一個 commit，方便檢視差異及回退。
使用 `git log --oneline` 查看紀錄；已提交的變更可用 `git revert <commit>` 建立反向提交。
