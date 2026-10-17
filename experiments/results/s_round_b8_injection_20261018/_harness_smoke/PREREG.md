# S-2 harness 冒烟预注册（非主判定；2026-10-18）

性质：**注入 harness 冒烟验证**，不进入主判定。目的：在正式预注册冻结前，
用 2 个 synthetic 任务验证注入机制能稳定产生"多轮失败 + coverage 停滞"并使
ON 臂触发 coverage_stall（off 臂不触发）。主结果见上一级目录 PREREG.md / README.md。

- 臂：on / off 各 1 次（--tasks 2 --seed 42 --profile fast --inject-rounds 3）
- 判据：on 臂出现 coverage_stall 标签、off 臂不出现；两臂均 exit 0。
- 不计入预算/结论；冒烟工件保留在本目录（`_harness_smoke/`）并在主 README 披露。
