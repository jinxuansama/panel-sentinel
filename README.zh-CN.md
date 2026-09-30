# Panel Sentinel：面板数据体检

在回归或效率分析之前检查 CSV：重复的企业—年份记录、缺失值、缺少年份、
非有限数、范围异常、声明的单位混用，以及企业内部没有变化的变量。
负利润可明确允许，百分比和金额单位由配置声明，不靠猜测。

```sh
python -m pip install .
panel-sentinel examples/clean.csv --schema examples/schema.json
panel-sentinel examples/broken.csv --schema examples/schema.json
python -m unittest discover -s tests -v
```

Python 3.10 以上，无运行时第三方依赖。两个示例均为模拟数据，分别演示通过和失败。
`--strict` 将缺少年份、无组内变化等警告也作为失败；`--output report.json` 保存报告。

工具不自动填补、删行或修改原始数据，也不计算 DEA、MSBM 或因果效应。
无组内变化只是检查提示，不等于论文结论或统计检验。完全没出现在 CSV 里的企业
无法被识别。报告记录数据和配置摘要，方便追踪版本。

MIT 开源。详细字段见 [设计文档](docs/design.md)。
