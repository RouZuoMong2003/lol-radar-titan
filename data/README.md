# data/

源数据目录（**不纳入版本库**，仅放说明）。

## 需要的文件

Oracle's Elixir 全年职业赛事比赛数据 CSV，例如：

```
2026_LoL_esports_match_data_from_OraclesElixir.csv
```

## 获取方式

从 Oracle's Elixir 下载页获取对应年份的 match data CSV：
<https://oracleselixir.com/tools/downloads>

把下载到的 CSV 放到本目录，或用环境变量指定路径。

## ETL 如何找到 CSV

`scripts/_common.py` 按以下优先级解析（见 `_resolve_csv()`）：

1. 环境变量 `OE_CSV`（推荐）：
   ```bash
   export OE_CSV=/absolute/path/to/your.csv
   ```
2. 本目录下的 `2026_LoL_esports_match_data_from_OraclesElixir.csv`
3. 本目录下任意匹配 `*OraclesElixir*.csv` 的文件
4. 兜底的本地开发路径（一般用不到）

## 说明

- 本项目与 Oracle's Elixir / Riot Games 无隶属关系，仅作非商业数据分析。
- 数据版权归原始来源所有，请遵循其使用条款。
