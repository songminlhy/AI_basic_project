#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
最终版架构 REV 2026-08-24 验收 smoke test（对齐用户决策迁移图-阶段2：Shared = 默认生产主链 + 删除自动 fallback 单轨 + Legacy 仅手动退路）：
  - TestA: 默认配置（NOTIFY_USE_SHARED 未设置 + config use_shared=true）→ shared_wecom 主链
  - TestB: Legacy 手动退路（显式 env NOTIFY_USE_SHARED=false）→ legacy_wecom 退路
  - TestC: 旧代码布尔判断仍可用（if notify.push_message(...) 等价于 result.success）
  - TestD: logger 里能 grep 到 [BACKTEST-SUMMARY] notify_run_id=xxx

执行：
  cd C:\Users\宋敏\Documents\trae_projects\AI_basic_project
  py -3 -m unittest tests.test_notify_smoke -v
"""
import os
import sys
import json
import logging
import unittest
from copy import deepcopy

# 确保 cwd = project root，import notify 正确
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)


class CapturingHandler(logging.Handler):
    """把 NOTIFY logger 所有行抓进 list，供 grep 用"""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level=level)
        self.records = []

    def emit(self, record):
        try:
            self.records.append(self.format(record))
        except Exception:
            pass


def _push_env(envvars):
    import contextlib

    @contextlib.contextmanager
    def ctx():
        saved = {}
        for k, v in envvars.items():
            saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # 强制重建 notify 单例
        import notify as _notify_mod
        _notify_mod._notifier_instance = None
        get_notifier = _notify_mod.get_notifier
        # 把实例置 None 后再取一次 → 重新读 config+env
        _notify_mod._notifier_instance = None
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            _notify_mod._notifier_instance = None
    return ctx()


class TestNotifySmoke(unittest.TestCase):

    def _capture_notify_logger(self, level=logging.INFO):
        cap = CapturingHandler(level=level)
        cap.setFormatter(logging.Formatter("%(levelname)s|%(name)s|%(message)s"))
        notify_logger = logging.getLogger("NOTIFY")
        notify_logger.setLevel(level)
        notify_logger.addHandler(cap)
        # SharedQuantData.scripts.wecom_notifier 用 WECOM logger，顺手也抓
        shared_logger = logging.getLogger("WECOM")
        shared_logger.setLevel(level)
        shared_logger.addHandler(cap)
        return cap, notify_logger, shared_logger

    # ------ 工具：检查 run_id 格式 (8 hex) ------
    @staticmethod
    def _looks_like_run_id(s):
        return isinstance(s, str) and len(s) == 8 and all(c in "0123456789abcdef" for c in s)

    # ======================================================================
    # TEST A — 生产默认（env NOTIFY_USE_SHARED 未设置 + config use_shared=true）
    #          → SharedQuantData【默认生产主链】
    # ======================================================================
    def test_A_shared_wecom_DEFAULT(self):
        # 最终架构：NOTIFY_USE_SHARED 不设置 → 直接走 Shared 默认主链（config=true 已生效）
        with _push_env({"NOTIFY_USE_SHARED": None}):
            import notify as n
            cap, nl, sl = self._capture_notify_logger()
            try:
                res = n.push_message(
                    "[最终架构20260824] Shared默认生产主链冒烟",
                    "默认配置（env NOTIFY_USE_SHARED 未设置 + notify_config.json use_shared=true）→ 唯一生产主链 SharedQuantData WeComNotifier；自动 Shared→Legacy fallback 已删除。",
                    "INFO",
                )
            finally:
                nl.removeHandler(cap)
                sl.removeHandler(cap)
            self.assertTrue(isinstance(res, dict), f"返回值必须是dict，实际 {type(res).__name__}")
            self.assertTrue(self._looks_like_run_id(res.get("run_id")),
                            f"run_id 格式不对: {res.get('run_id')}")
            self.assertTrue(res.success, f"shared 主链发送失败: {res.get('hint')} errcode={res.get('errcode')}")
            self.assertEqual(res.get("channel"), "shared_wecom",
                             f"【默认生产主链】必须严格等于 shared_wecom，实际={res.get('channel')}")
            joined = "\n".join(cap.records)
            self.assertIn("[BACKTEST-SUMMARY] notify_run_id=" + res.run_id, joined,
                          f"summary 日志里没出现 run_id，实际 log: {joined}")
            print(f"[A-PASS] shared(默认生产主链)  ok  run_id={res.run_id}  channel={res.channel}  "
                  f"attempts={res.attempts}  errcode={res.errcode}")

    # ======================================================================
    # TEST B — Legacy 手动退路（显式 env NOTIFY_USE_SHARED=false → Legacy）
    #          注意：自动 fallback 已删除，这里是【主动显式切换退路】
    # ======================================================================
    def test_B_legacy_manual_fallback_env_FALSE(self):
        with _push_env({"NOTIFY_USE_SHARED": "false"}):
            import notify as n
            cap, nl, sl = self._capture_notify_logger()
            try:
                res = n.push_message(
                    "[最终架构20260824] Legacy手动退路冒烟(env=false)",
                    "显式 env NOTIFY_USE_SHARED=false → 走 Legacy urllib 手动退路（Legacy 代码完整保留不删，用户决策暂不删 Legacy，退路稳）。",
                    "P2",
                )
            finally:
                nl.removeHandler(cap)
                sl.removeHandler(cap)
            self.assertTrue(isinstance(res, dict))
            self.assertTrue(self._looks_like_run_id(res.get("run_id")))
            self.assertTrue(res.success, f"legacy 退路发送失败: {res.get('hint')} errcode={res.get('errcode')}")
            # 严格 legacy_wecom：不能出现 fallback 后缀（退路是主动切的，不是"降级"）
            self.assertEqual(res.get("channel"), "legacy_wecom",
                             f"Legacy 手动退路【env=false】必须严格等于 legacy_wecom，实际={res.get('channel')}（不能有 fallback 后缀）")
            joined = "\n".join(cap.records)
            self.assertIn("[BACKTEST-SUMMARY] notify_run_id=" + res.run_id, joined)
            print(f"[B-PASS] legacy(手动退路env=false)  ok  run_id={res.run_id}  channel={res.channel}  "
                  f"attempts={res.attempts}  errcode={res.errcode}")

    # ======================================================================
    # TEST C — 旧代码 bool 判断语义未破坏
    # ======================================================================
    def test_C_bool_semantics_backward_compat(self):
        with _push_env({"NOTIFY_USE_SHARED": None}):
            import notify as n
            ok_success = n.push_message("[最终架构20260824] bool语义测试", "内容A", "INFO")
            self.assertTrue(isinstance(ok_success, dict))
            if ok_success.success:
                self.assertTrue(bool(ok_success), "成功的返回对象 bool(...) 必须为 True")
        with _push_env({"NOTIFY_USE_SHARED": None, "NOTIFY_ENABLED": "false"}):
            import notify as n
            r_disabled = n.push_message("[最终架构20260824] 不应发送", "内容B", "INFO")
            self.assertFalse(bool(r_disabled), "未启用时 bool(...) 必须为 False")
            self.assertEqual(r_disabled.channel, "disabled")
            self.assertTrue(self._looks_like_run_id(r_disabled.run_id), "未启用也应该分配 run_id")
            print(f"[C-PASS] bool语义 ok  disabled_run_id={r_disabled.run_id}")

    # ======================================================================
    # TEST D — push_backtest_result 能输出 run_id，且 summary 行可 grep
    # ======================================================================
    def test_D_push_backtest_result_run_id(self):
        with _push_env({"NOTIFY_USE_SHARED": None}):
            import notify as n
            cap, nl, sl = self._capture_notify_logger()
            try:
                res = n.push_backtest_result({
                    "strategy": "最终架构20260824验收假回测",
                    "period": "2023-01-01~2024-01-01(1.0年)",
                    "final_nav": 1.85,
                    "ann_ret": 85.0,
                    "mdd": 12.3,
                    "sharpe": 2.1,
                    "n_trades": 100,
                    "win_rate": 62.0,
                    "avg_win": 1.35,
                    "extra": {"信号日": 50, "无成本年化": "90.0%", "标准成本年化": "85.0%"},
                })
            finally:
                nl.removeHandler(cap)
                sl.removeHandler(cap)
            self.assertTrue(self._looks_like_run_id(res.get("run_id")))
            self.assertTrue(res.success, f"假回测推送失败: {res.get('hint')}")
            self.assertEqual(res.get("channel"), "shared_wecom",
                             f"默认生产主链必须 shared_wecom，实际={res.get('channel')}")
            joined = "\n".join(cap.records)
            self.assertIn("[BACKTEST-SUMMARY] notify_run_id=" + res.run_id, joined)
            print(f"[D-PASS] backtest_result  ok  run_id={res.run_id}  channel={res.channel}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
