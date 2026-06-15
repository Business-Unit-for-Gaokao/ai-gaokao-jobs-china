# gaokao-ai-impact-map

基于高考专业数据和 `AI-jobs-China` 职业数据，生成“大学专业 -> 可能职业路径 -> AI 影响度”的静态可视化页面。

这里的 AI 影响度更接近职业暴露度和重塑程度，不等同于“岗位会消失”或“专业不值得报考”。

把 `data/all.json` 和 `data/data.json` 放进仓库后，GitHub Actions 会自动执行：

1. 规范化专业数据
2. 规范化岗位数据
3. 生成专业到职业路径的映射规则
4. 按证据等级、岗位规模和匹配方式计算专业 AI 影响度
5. 校验输出质量并发布静态页面

## 使用方法

- 把高考专业数据放到 `data/all.json`
- 把招聘数据放到 `data/data.json`
- 根据你的专业代码维护 `config/major_job_rules.json`
- 根据你的口径维护 `config/ai_replace_rules.json`
- push 到 `main` 或手动运行 workflow

## 数据口径

- `direct`：专业就业方向文本直接命中职业
- `inferred`：由专业名称规则推断职业路径
- `fallback`：由专业类或学科门类兜底推断
- `adjusted_impact_rate`：默认展示的调整后 AI 影响度
- `matched_job_contributions`：对专业影响度贡献最高的职业明细

## 输出文件

- `output/majors.normalized.json`
- `output/jobs.normalized.json`
- `output/major_ai_rate.json`
- `output/major_ai_rate.debug.json`

## 可选升级

- 增加专业类批量映射
- 增加 TF-IDF / embedding 相似度
- 增加历史版本 diff
- 自动发布到 GitHub Pages
