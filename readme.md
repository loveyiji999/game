#  擬真賽車 Rogue-like 遊戲

這是一款以「回合制＋事件驅動＋真實數值模擬」為核心的文字式賽車遊戲。
玩家將面對隨機氣候、AI 壓迫、燃油輪胎管理等多重挑戰，體驗策略與反應交織的樂趣。

## 模組結構
- `core/`：遊戲引擎與邏輯核心（如車輛狀態、事件系統）
- `data/`：YAML 格式的資料（事件、車輛屬性等）
- `scripts/`：主流程模擬器
- `tests/`：單元測試與驗證

## 執行範例
```bash
python scripts/main.py
```

## 事件觸發優化機制

事件 YAML 新增 `solo` 與 `max_per_segment` 兩欄位，系統會依事件 `category` 及路段類型決定同一回合可堆疊的事件數。若事件設為 `solo: true`，當回合僅會執行該事件。

```yaml
- id: sample_event
  category: fault
  solo: false
  max_per_segment: 1
  priority: 3
```

更完整的規則實作可參考 `core/turn_flow.py`。
