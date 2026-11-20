# 声轨对时台

口述历史音频整理员可用本地工作台处理声轨片段，复查对齐锚段并与独立清单逐笔核对。

按音频样本计数和标准时钟锚点做分段映射，检测时钟回退和漂移超界。

## 启动

```sh
docker compose up --build
```

打开 http://127.0.0.1:18307 并运行随附样例。可以在「导入来源与外部账」上传自己的 CSV，也可以编辑表单中的样例。数据保存于 Compose 卷 `ledger`。使用 `APP_PORT` 可覆盖宿主端口。

## 工作步骤

1. 检查「录音来源」与「锚点字段」，定位导入坏行与字段归一结果。
2. 在「时码异常」区分冲突、业务拒绝、重传与旧版本。
3. 打开「双锚校时」并点击任意记录的「查看依据」。
4. 在「制作勾稽」检查金额或用量差异。通过「片段批次」复算原文件，通过「校时复核」提交意见并下载证据。

接口定义见 `/openapi.json`。字段、允许区间及算例见 [数据字典](docs/DATA-DICTIONARY.md)，模块和回归测试见 [测试登记](docs/DEPTH.md)。

## 验证

```sh
docker compose config --quiet
docker compose exec -T app pytest -q
```

`sample_data/shift.csv` 是班次数据，`sample_data/external.csv` 是独立账样例。`cases.csv` 固定业务反例，`legacy.csv` 和 `truncated.csv` 用于验证历史格式与断行。
