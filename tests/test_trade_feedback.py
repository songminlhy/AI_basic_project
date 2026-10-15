#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_trade_feedback.py — TradeFeedbackOrchestrator 单元测试

执行:
  cd C:\\Users\\宋敏\\Documents\\trae_projects\\AI_basic_project
  python -m unittest tests.test_trade_feedback -v

设计要点:
  - 使用 unittest.mock.MagicMock 替代真实 WeCom 通知器 (零外部依赖, 零生产消息)
  - 只测 trade_feedback.py 自身逻辑, 不触发 chen_live_trading / QMT / xtquant
  - 每个测试方法自包含, 不依赖执行顺序
  - 覆盖: 错误分类 / 生命周期 / 成功推送 / 失败推送 / 幂等 / QMT 回调 / JSONL 归档
"""
import os
import sys
import json
import unittest
import datetime
from unittest.mock import MagicMock, patch, PropertyMock

# ── 确保 import 路径正确 ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from trade_feedback import (  # noqa: E402
    TradeFeedbackOrchestrator,
    classify_error,
    _OrderState,
    _ERROR_CLASSIFY,
)


# ======================================================================
# Fixture: 构造一个"假 notifier" — 有 ready 属性 + push_message 返回成功
# ======================================================================
def _make_mock_notifier(success: bool = True):
    """返回 MagicMock, 模拟 WeChatNotifier 的 ready + push_message 接口"""
    notifier = MagicMock()
    type(notifier).ready = PropertyMock(return_value=True if success else False)
    ret = MagicMock()
    ret.__bool__ = MagicMock(return_value=success)
    ret.success = success
    ret.run_id = "abcdef12"
    notifier.push_message.return_value = ret
    return notifier


def _make_disabled_notifier():
    """ready=False 的 notifier — 应该跳过所有推送"""
    notifier = MagicMock()
    type(notifier).ready = PropertyMock(return_value=False)
    return notifier


class TestClassifyError(unittest.TestCase):
    """错误分类函数 classify_error 的边界覆盖"""

    def test_all_predefined_codes(self):
        """遍历所有 _ERROR_CLASSIFY 预定义 code, 确保返回正确 tuple"""
        for code, expected in _ERROR_CLASSIFY.items():
            level, readable, steps, retryable = classify_error(code, "")
            self.assertEqual(level, expected[0], f"code={code} level mismatch")
            self.assertEqual(readable, expected[1], f"code={code} readable mismatch")
            self.assertIsInstance(steps, list)
            self.assertTrue(len(steps) >= 2, f"code={code} 至少 2 条排查步骤, 实际 {len(steps)}")
            self.assertIsInstance(retryable, bool)

    def test_unknown_code_defaults_to_P1(self):
        """不在预定义表里的 code → 默认 P1 + 通用排查"""
        level, readable, steps, retryable = classify_error("MY_CUSTOM_ERROR", "")
        self.assertEqual(level, "P1")
        self.assertEqual(readable, "MY_CUSTOM_ERROR")
        self.assertIsInstance(steps, list)

    def test_infer_from_raw_error_connect_keyword(self):
        """空 code + raw_error 含 connect/disconnect → 应推断为 P0 QMT_DISCONNECTED"""
        level, readable, steps, retryable = classify_error("", "connection lost")
        self.assertEqual(level, "P0")
        self.assertEqual(readable, "QMT连接断开")

    def test_infer_from_raw_error_session_keyword(self):
        """raw_error 含 session/conflict → SESSION_CONFLICT"""
        level, readable, steps, retryable = classify_error("", "session already in use")
        self.assertEqual(readable, "IPC会话冲突")

    def test_infer_from_raw_error_price_keyword(self):
        """raw_error 含 price/cage → PRICE_CAGE_BLOCKED"""
        level, readable, steps, retryable = classify_error("", "price limit exceeded")
        self.assertEqual(readable, "价格笼子拦截")

    def test_empty_error_empty_code(self):
        """code='' + raw_error='' → UNKNOWN_ERROR"""
        level, readable, steps, retryable = classify_error("", "")
        self.assertEqual(readable, "UNKNOWN_ERROR")
        self.assertIsInstance(steps, list)
        self.assertFalse(retryable)


class TestOrderState(unittest.TestCase):
    """_OrderState 数据类 — 简单属性验证"""

    def test_creation(self):
        now_before = datetime.datetime.now()
        s = _OrderState("123", "000001.SZ", "BUY", 10.0, 500, attempt=1)
        now_after = datetime.datetime.now()
        self.assertEqual(s.order_id, "123")
        self.assertEqual(s.stock_code, "000001.SZ")
        self.assertEqual(s.direction, "BUY")
        self.assertEqual(s.price, 10.0)
        self.assertEqual(s.volume, 500)
        self.assertEqual(s.attempt, 1)
        self.assertEqual(s.status, "PLACED")
        self.assertEqual(s.fill_notified, False)
        self.assertGreaterEqual(s.created_at, now_before)
        self.assertLessEqual(s.created_at, now_after)


class TestOrchestratorLifecycle(unittest.TestCase):
    """TradeFeedbackOrchestrator 的启停 / 开关 / 空运行"""

    def test_disabled_noop(self):
        """enabled=False → 所有方法不抛异常, 状态不变"""
        fb = TradeFeedbackOrchestrator(enabled=False)
        fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("1", 100, 10.0, "FILLED")
        fb.on_trade_failed("000002.SZ", "SELL", error_code="QMT_DISCONNECTED")
        self.assertEqual(fb.get_stats()["total_placed"], 0)
        self.assertEqual(fb.get_stats()["total_filled"], 0)
        self.assertEqual(fb.get_stats()["total_failed"], 0)
        self.assertEqual(len(fb.get_active_orders()), 0)

    def test_no_notifier_pushes_skipped(self):
        """notify_module=ready=False → 不推送, 但状态仍记录"""
        fb = TradeFeedbackOrchestrator(notify_module=_make_disabled_notifier(), enabled=True)
        fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("1", 100, 10.0, "FILLED")
        fb.on_trade_failed("000002.SZ", "SELL", error_code="PRICE_CAGE_BLOCKED")
        # 状态已记录
        self.assertEqual(fb.get_stats()["total_placed"], 1)
        self.assertEqual(fb.get_stats()["total_filled"], 1)
        self.assertEqual(fb.get_stats()["total_failed"], 1)
        # 但推送次数为 0 (notifier 未就绪)
        self.assertEqual(fb.get_stats()["total_push_ok"], 0)

    def test_disabled_notifier_pushes_skipped(self):
        """notify_module.ready=False → 跳过推送"""
        fb = TradeFeedbackOrchestrator(
            notify_module=_make_disabled_notifier(), enabled=True
        )
        fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("1", 100, 10.0, "FILLED")
        self.assertEqual(fb.get_stats()["total_push_ok"], 0)
        self.assertEqual(fb.get_stats()["total_push_fail"], 0)

    def test_success_notifier_records_push_ok(self):
        """notifier.ready=True + push_message 返回 success → total_push_ok 增加"""
        fb = TradeFeedbackOrchestrator(notify_module=_make_mock_notifier(True), enabled=True)
        fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("1", 100, 10.0, "FILLED")
        # FILLED 推送了一次
        self.assertEqual(fb.get_stats()["total_push_ok"], 1)

    def test_module_level_singleton(self):
        """get_orchestrator() 返回同一个实例 (第二次调用不是 None)"""
        from trade_feedback import get_orchestrator
        a = get_orchestrator(notify_module=_make_mock_notifier(True))
        b = get_orchestrator()
        self.assertIs(a, b, "get_orchestrator 应返回同一个单例")


class TestOnOrderPlaced(unittest.TestCase):
    def setUp(self):
        self.notifier = _make_mock_notifier(True)
        self.fb = TradeFeedbackOrchestrator(notify_module=self.notifier, enabled=True)

    def test_single_order(self):
        self.fb.on_order_placed("42", "600519.SH", "BUY", 1800.00, 10, attempt=1)
        orders = self.fb.get_active_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["order_id"], "42")
        self.assertEqual(orders[0]["stock_code"], "600519.SH")
        self.assertEqual(orders[0]["direction"], "BUY")
        self.assertEqual(orders[0]["status"], "PLACED")
        self.assertEqual(self.fb.get_stats()["total_placed"], 1)

    def test_direction_sell(self):
        self.fb.on_order_placed("99", "000002.SZ", "SELL", 5.50, 200, attempt=3)
        orders = self.fb.get_active_orders()
        self.assertEqual(orders[0]["direction"], "SELL")

    def test_multiple_orders(self):
        for i in range(5):
            self.fb.on_order_placed(str(i), f"00000{i}.SZ", "BUY", 10.0, 100)
        self.assertEqual(self.fb.get_stats()["total_placed"], 5)
        self.assertEqual(len(self.fb.get_active_orders()), 5)

    def test_extra_dict_preserved(self):
        """extra 参数 (如 lianban/kaiban) 应被传递, 不破坏主流程"""
        self.fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100,
                                extra={"lianban": 3, "kaiban": 1})
        # 只要不报错就算通过 (extra 存在 pending 里, 但 get_active_orders 不暴露)


class TestOnFillConfirmed(unittest.TestCase):
    """成交确认 — FILLED / PARTIAL / 幂等性"""

    def setUp(self):
        self.notifier = _make_mock_notifier(True)
        self.fb = TradeFeedbackOrchestrator(notify_module=self.notifier, enabled=True)

    def test_filled_pushes_p2(self):
        self.fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        self.notifier.push_message.reset_mock()
        self.fb.on_fill_confirmed("1", 100, 10.0, status="FILLED")
        # 应调用了 1 次 push_message
        self.assertEqual(self.notifier.push_message.call_count, 1)
        args, kwargs = self.notifier.push_message.call_args
        # level=P2
        self.assertEqual(kwargs.get("level") or (args[2] if len(args) > 2 else None), "P2")
        self.assertEqual(self.fb.get_stats()["total_filled"], 1)

    def test_partial_pushes_p2_but_status_is_PARTIAL(self):
        self.fb.on_order_placed("2", "000002.SZ", "BUY", 10.0, 200)
        self.notifier.push_message.reset_mock()
        self.fb.on_fill_confirmed("2", 80, 9.98, status="PARTIAL")
        self.assertEqual(self.notifier.push_message.call_count, 1)
        orders = self.fb.get_active_orders()
        order_2 = next(o for o in orders if o["order_id"] == "2")
        self.assertEqual(order_2["status"], "PARTIAL")
        self.assertEqual(order_2["filled_volume"], 80)
        self.assertAlmostEqual(order_2["avg_fill_price"], 9.98)

    def test_idempotent_no_duplicate_push(self):
        """同一 order_id 重复 FILLED → 只推送 1 次"""
        self.fb.on_order_placed("3", "000003.SZ", "BUY", 10.0, 100)
        self.notifier.push_message.reset_mock()
        self.fb.on_fill_confirmed("3", 100, 10.0, "FILLED")
        self.fb.on_fill_confirmed("3", 100, 10.0, "FILLED")  # 重复!
        self.fb.on_fill_confirmed("3", 100, 10.0, "FILLED")  # 再重复!
        self.assertEqual(self.notifier.push_message.call_count, 1,
                         "FILLED 通知应幂等, 重复调用只推送一次")

    def test_fill_before_place_recovers(self):
        """on_fill_confirmed 先于 on_order_placed 到达 (罕见但应能恢复)"""
        # 不先调用 on_order_placed
        self.notifier.push_message.reset_mock()
        self.fb.on_fill_confirmed("orphan", 100, 10.0, "FILLED")
        # 不抛异常 → 通过
        self.assertEqual(self.fb.get_stats()["total_filled"], 1)
        self.assertEqual(self.notifier.push_message.call_count, 1)


class TestOnTradeFailed(unittest.TestCase):
    """失败入口 — 错误分级 / retry_count / 不抛异常"""

    def setUp(self):
        self.notifier = _make_mock_notifier(True)
        self.fb = TradeFeedbackOrchestrator(notify_module=self.notifier, enabled=True)

    def test_price_cage_p1_push(self):
        self.notifier.push_message.reset_mock()
        self.fb.on_trade_failed(
            "001299.SZ", "BUY", order_id=None, price=9.99, volume=500,
            error_code="PRICE_CAGE_BLOCKED", error_msg="limit up", retry_count=0,
        )
        self.assertEqual(self.notifier.push_message.call_count, 1)
        args, kwargs = self.notifier.push_message.call_args
        self.assertEqual(kwargs.get("level") or (args[2] if len(args) > 2 else None), "P1")
        # title 应包含可读名
        title = args[0] if args else kwargs.get("title", "")
        self.assertIn("价格笼子拦截", title)

    def test_qmt_disconnected_p0(self):
        self.notifier.push_message.reset_mock()
        self.fb.on_trade_failed(
            "*", "BUY", error_code="QMT_DISCONNECTED", error_msg="IPC lost",
        )
        self.assertEqual(self.notifier.push_message.call_count, 1)
        args, kwargs = self.notifier.push_message.call_args
        level = kwargs.get("level") or (args[2] if len(args) > 2 else None)
        self.assertEqual(level, "P0")

    def test_retry_count_zero_goes_through(self):
        """retry_count=0 不代表"没失败" — 价格笼子拦截就是 retry_count=0 也应推送"""
        self.notifier.push_message.reset_mock()
        self.fb.on_trade_failed("001299.SZ", "BUY", error_code="PRICE_CAGE_BLOCKED", retry_count=0)
        self.assertEqual(self.notifier.push_message.call_count, 1)

    def test_retry_count_three(self):
        self.notifier.push_message.reset_mock()
        self.fb.on_trade_failed("000001.SZ", "BUY", order_id=-1,
                                error_code="ORDER_ID_INVALID", retry_count=3)
        self.assertEqual(self.notifier.push_message.call_count, 1)
        # 统计 total_failed 应增加
        self.assertGreaterEqual(self.fb.get_stats()["total_failed"], 1)

    def test_direction_sell_failure(self):
        self.notifier.push_message.reset_mock()
        self.fb.on_trade_failed("600610.SH", "SELL", error_code="ORDER_JUNK")
        args, _ = self.notifier.push_message.call_args
        content = args[1] if len(args) > 1 else ""
        # 消息里应包含 "卖出"
        self.assertIn("卖出", content)


class TestQMTCallbacks(unittest.TestCase):
    """模拟 QMT 回调对象 — on_stock_trade / on_order_error"""

    def setUp(self):
        self.notifier = _make_mock_notifier(True)
        self.fb = TradeFeedbackOrchestrator(notify_module=self.notifier, enabled=True)

    def _make_trade(self, order_id, stock_code, volume, price_quadrupled=True):
        """构造类似 xttype.Trade 的魔法对象

        QMT 真实行为: price 可能是 float, 也可能是 ×10000 的 int
        这里测试两种格式
        """
        trade = MagicMock()
        trade.m_nOrderID = order_id
        trade.m_strStockCode = stock_code
        trade.m_nTradedVolume = volume
        # price_quadrupled=True 模拟 ×100 int, False 模拟 float
        if price_quadrupled:
            trade.m_dTradedPrice = int(10.50 * 100)  # 1050 → 应识别为 ×100
        else:
            trade.m_dTradedPrice = 10.50
        return trade

    def test_qmt_trade_callback_full_fill(self):
        """先 order_placed, 再 QMT trade callback → 应置 FILLED 并推送"""
        self.fb.on_order_placed("tc1", "000001.SZ", "BUY", 10.50, 100)
        self.notifier.push_message.reset_mock()
        trade = self._make_trade("tc1", "000001.SZ", 100, price_quadrupled=False)
        self.fb.on_qmt_trade_callback(trade)
        # 100/100 → 全成 → 推送
        self.assertEqual(self.notifier.push_message.call_count, 1)
        orders = self.fb.get_active_orders()
        order = next(o for o in orders if o["order_id"] == "tc1")
        self.assertEqual(order["status"], "FILLED")

    def test_qmt_trade_callback_partial_then_full(self):
        """先成交 40/100 → PARTIAL; 再成交 60/100 → FILLED"""
        self.fb.on_order_placed("tc2", "000002.SZ", "BUY", 10.50, 100)
        self.notifier.push_message.reset_mock()

        trade1 = self._make_trade("tc2", "000002.SZ", 40, price_quadrupled=False)
        self.fb.on_qmt_trade_callback(trade1)
        orders = self.fb.get_active_orders()
        order = next(o for o in orders if o["order_id"] == "tc2")
        self.assertEqual(order["status"], "PARTIAL")
        self.assertEqual(order["filled_volume"], 40)
        # PARTIAL 未达全成, 不推送
        self.assertEqual(self.notifier.push_message.call_count, 0)

        trade2 = self._make_trade("tc2", "000002.SZ", 60, price_quadrupled=False)
        self.fb.on_qmt_trade_callback(trade2)
        order = next(o for o in self.fb.get_active_orders() if o["order_id"] == "tc2")
        self.assertEqual(order["status"], "FILLED")
        self.assertEqual(order["filled_volume"], 100)
        # 全成 → 推送 1 次
        self.assertEqual(self.notifier.push_message.call_count, 1)

    def test_qmt_trade_callback_weighted_avg_price(self):
        """两次不同价格成交 → 加权均价计算正确"""
        self.fb.on_order_placed("tc3", "000003.SZ", "BUY", 10.50, 100)
        self.fb.on_qmt_trade_callback(self._make_trade("tc3", "000003.SZ", 40, price_quadrupled=False))
        trade2 = MagicMock()
        trade2.m_nOrderID = "tc3"
        trade2.m_strStockCode = "000003.SZ"
        trade2.m_nTradedVolume = 60
        trade2.m_dTradedPrice = 11.00  # 第二次价更高
        self.fb.on_qmt_trade_callback(trade2)
        order = next(o for o in self.fb.get_active_orders() if o["order_id"] == "tc3")
        # 加权均价 = (10.50*40 + 11.00*60) / 100 = (420 + 660) / 100 = 10.80
        self.assertAlmostEqual(order["avg_fill_price"], 10.80, places=2)

    def test_qmt_trade_callback_price_int_conversion(self):
        """QMT 可能返回 price=int × 100 (如 1050 表示 10.50) — 应自动识别转换"""
        self.fb.on_order_placed("tc4", "000004.SZ", "BUY", 10.50, 100)
        # price_quadrupled=True → m_dTradedPrice = 1050 (int)
        self.fb.on_qmt_trade_callback(
            self._make_trade("tc4", "000004.SZ", 100, price_quadrupled=True)
        )
        order = next(o for o in self.fb.get_active_orders() if o["order_id"] == "tc4")
        # 内部转换: 1050 > 1000 → 1050/100 = 10.50
        self.assertAlmostEqual(order["avg_fill_price"], 10.50, places=2)

    def test_qmt_trade_callback_before_placed_safe(self):
        """QMT trade callback 先到 (on_order_placed 还没) → 不抛异常, 等 confirm_order_filled 处理"""
        trade = self._make_trade("orphan", "000005.SZ", 100, price_quadrupled=False)
        # 不应抛异常
        self.fb.on_qmt_trade_callback(trade)
        # orphan 订单不在 active_orders 里 — 回调静默忽略
        self.assertEqual(len(self.fb.get_active_orders()), 0)

    def test_qmt_order_error_callback_propagates(self):
        """on_order_error → 应触发 on_trade_failed"""
        self.notifier.push_message.reset_mock()
        err = MagicMock()
        err.m_nOrderID = "err1"
        err.m_strStockCode = "000001.SZ"
        err.error_msg = "insufficient funds"
        self.fb.on_qmt_order_error_callback(err)
        self.assertEqual(self.notifier.push_message.call_count, 1)
        args, _ = self.notifier.push_message.call_args
        content = args[1] if len(args) > 1 else ""
        self.assertIn("insufficient funds", content)


class TestJsonlPersistence(unittest.TestCase):
    """每次推送都应归档到 JSONL"""

    def test_fill_creates_jsonl_entry(self):
        notifier = _make_mock_notifier(True)
        fb = TradeFeedbackOrchestrator(notify_module=notifier, enabled=True)
        fb.on_order_placed("j1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("j1", 100, 10.0, "FILLED")
        # 读 JSONL
        log_dir = os.path.join(PROJECT_ROOT, "logs")
        today = datetime.datetime.now().strftime("%Y%m%d")
        log_path = os.path.join(log_dir, f"trade_feedback_{today}.jsonl")
        self.assertTrue(os.path.exists(log_path), f"JSONL 不存在: {log_path}")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        fill_entries = [l for l in lines if l.get("event") == "FILL_NOTIFIED" and l.get("order_id") == "j1"]
        self.assertTrue(len(fill_entries) >= 1, f"FILLED 归档条目缺失. 全部条目: {lines}")
        entry = fill_entries[0]
        self.assertEqual(entry["status"], "FILLED")
        self.assertEqual(entry["symbol"], "000001.SZ")
        self.assertTrue(entry["push_ok"])

    def test_fail_creates_jsonl_entry(self):
        notifier = _make_mock_notifier(True)
        fb = TradeFeedbackOrchestrator(notify_module=notifier, enabled=True)
        fb.on_trade_failed("600610.SH", "SELL", error_code="PRICE_CAGE_BLOCKED", retry_count=2)
        log_dir = os.path.join(PROJECT_ROOT, "logs")
        today = datetime.datetime.now().strftime("%Y%m%d")
        log_path = os.path.join(log_dir, f"trade_feedback_{today}.jsonl")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        fail_entries = [l for l in lines if l.get("event") == "FAIL_NOTIFIED" and l.get("symbol") == "600610.SH"]
        self.assertTrue(len(fail_entries) >= 1, f"FAIL 归档条目缺失")
        entry = fail_entries[0]
        self.assertEqual(entry["level"], "P1")
        self.assertEqual(entry["error_code"], "PRICE_CAGE_BLOCKED")
        self.assertTrue(entry["auto_retry"])


class TestStatsAccumulation(unittest.TestCase):
    """统计字典的累加正确性"""

    def test_stats_reset_between_instances(self):
        a = TradeFeedbackOrchestrator(enabled=True)
        b = TradeFeedbackOrchestrator(enabled=True)
        self.assertEqual(a.get_stats(), b.get_stats())
        a.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        b_stats_before = dict(b.get_stats())
        # b 是独立实例, 不应被 a 的操作影响
        self.assertEqual(b.get_stats(), b_stats_before)

    def test_stats_correct_increment(self):
        fb = TradeFeedbackOrchestrator(notify_module=_make_mock_notifier(True), enabled=True)
        fb.on_order_placed("1", "000001.SZ", "BUY", 10.0, 100)
        fb.on_fill_confirmed("1", 100, 10.0, "FILLED")       # filled +=1
        fb.on_order_placed("2", "000002.SZ", "SELL", 20.0, 50)
        fb.on_fill_confirmed("2", 50, 20.0, "FILLED")       # filled +=1  (共 2)
        fb.on_trade_failed("000003.SZ", "BUY", error_code="ORDER_ID_INVALID")  # failed +=1

        s = fb.get_stats()
        self.assertEqual(s["total_placed"], 2)
        self.assertEqual(s["total_filled"], 2)
        self.assertEqual(s["total_failed"], 1)
        # 2 次 FILLED push + 1 次 FAIL push
        self.assertGreaterEqual(s["total_push_ok"], 3)


# ======================================================================
# 主入口
# ======================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
