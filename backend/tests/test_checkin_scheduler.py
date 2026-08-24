import asyncio
import threading
from datetime import UTC, datetime
from typing import Callable

import pytest

import app.services.checkin_scheduler as scheduler_module
from app.config.vault import SecretVault
from app.services.checkin_scheduler import CheckinScheduler


class FakeCheckinService:
    """记录调度器调用并允许测试控制同步签到执行。"""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        delay: int = 3600,
    ) -> None:
        self.loop = loop
        self.delay = delay
        self.run_calls: list[datetime] = []
        self.delay_calls: list[datetime] = []
        self.called = asyncio.Event()
        self.run_entered = asyncio.Event()
        self.delay_entered = asyncio.Event()
        self.release_run: threading.Event | None = None
        self.release_delay: threading.Event | None = None
        self.run_error: Exception | None = None

    def run_due(self, now: datetime) -> bool:
        self.run_calls.append(now)
        self.loop.call_soon_threadsafe(self.run_entered.set)
        if self.release_run is not None:
            self.release_run.wait()
        if self.run_error is not None:
            error, self.run_error = self.run_error, None
            raise error
        return False

    def seconds_until_next(self, now: datetime) -> int:
        self.delay_calls.append(now)
        self.loop.call_soon_threadsafe(self.called.set)
        self.loop.call_soon_threadsafe(self.delay_entered.set)
        if self.release_delay is not None:
            self.release_delay.wait()
        return self.delay


async def _wait_for_count(values: list[object], count: int) -> None:
    """等待调用次数达到预期，避免依赖固定睡眠时长。"""
    async with asyncio.timeout(1):
        while len(values) < count:
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_start_runs_due_with_aware_utc_now() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    scheduler = CheckinScheduler(lambda: service, lambda: True)

    scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await scheduler.stop()

    assert service.run_calls[0].tzinfo is UTC
    assert service.delay_calls[0].tzinfo is UTC
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_locked_scheduler_waits_without_constructing_service() -> None:
    factory_called = asyncio.Event()

    def factory() -> FakeCheckinService:
        factory_called.set()
        raise AssertionError("锁定时不得构造签到模块")

    scheduler = CheckinScheduler(factory, lambda: False)

    scheduler.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await scheduler.stop()

    assert factory_called.is_set() is False


@pytest.mark.asyncio
async def test_wake_runs_after_vault_becomes_unlocked() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    unlocked = False
    scheduler = CheckinScheduler(lambda: service, lambda: unlocked)
    scheduler.start()
    await asyncio.sleep(0)

    unlocked = True
    scheduler.wake()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await scheduler.stop()

    assert len(service.run_calls) == 1


@pytest.mark.asyncio
async def test_configured_delay_prevents_immediate_rerun() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop, delay=3600)
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(service.run_calls) == 1

    await scheduler.stop()


@pytest.mark.asyncio
async def test_wake_interrupts_configured_delay() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop, delay=3600)
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)

    waking_thread = threading.Thread(target=scheduler.wake)
    waking_thread.start()
    waking_thread.join()
    await _wait_for_count(service.run_calls, 2)
    await scheduler.stop()


@pytest.mark.asyncio
async def test_wake_during_synchronous_run_is_not_lost() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    service.release_run = threading.Event()
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    await asyncio.wait_for(service.run_entered.wait(), timeout=1)

    scheduler.wake()
    service.release_run.set()
    await _wait_for_count(service.run_calls, 2)
    await scheduler.stop()


@pytest.mark.asyncio
async def test_wake_during_delay_calculation_is_not_lost() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    service.release_delay = threading.Event()
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    try:
        await asyncio.wait_for(service.delay_entered.wait(), timeout=1)

        waking_thread = threading.Thread(target=scheduler.wake)
        waking_thread.start()
        waking_thread.join()
        await asyncio.sleep(0)
        service.release_delay.set()

        await _wait_for_count(service.run_calls, 2)
    finally:
        service.release_delay.set()
        await scheduler.stop()


@pytest.mark.asyncio
async def test_wake_interrupts_exception_fallback_wait(monkeypatch, caplog) -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    service.run_error = RuntimeError("credential-value")
    fallback_waiting = asyncio.Event()
    original_wait_for = asyncio.wait_for

    async def observe_wait(awaitable, timeout):
        if timeout == 3600:
            fallback_waiting.set()
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(scheduler_module.asyncio, "wait_for", observe_wait)
    scheduler = CheckinScheduler(lambda: service, lambda: True, fallback_delay=3600)
    scheduler.start()
    try:
        async with asyncio.timeout(1):
            await fallback_waiting.wait()

        waking_thread = threading.Thread(target=scheduler.wake)
        waking_thread.start()
        waking_thread.join()
        await _wait_for_count(service.run_calls, 2)
    finally:
        await scheduler.stop()

    assert scheduler.is_running is False
    assert "RuntimeError" in caplog.text
    assert "credential-value" not in caplog.text


@pytest.mark.asyncio
async def test_factory_exception_is_redacted_and_wake_retries(
    monkeypatch,
    caplog,
) -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    fallback_waiting = asyncio.Event()
    original_wait_for = asyncio.wait_for
    factory_calls = 0

    def factory() -> FakeCheckinService:
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            raise RuntimeError("secret-detail")
        return service

    async def observe_wait(awaitable, timeout):
        if timeout == 3600:
            fallback_waiting.set()
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(scheduler_module.asyncio, "wait_for", observe_wait)
    scheduler = CheckinScheduler(factory, lambda: True, fallback_delay=3600)
    scheduler.start()
    try:
        async with asyncio.timeout(1):
            await fallback_waiting.wait()

        waking_thread = threading.Thread(target=scheduler.wake)
        waking_thread.start()
        waking_thread.join()
        await asyncio.wait_for(service.run_entered.wait(), timeout=1)
    finally:
        await scheduler.stop()

    assert factory_calls == 2
    assert "RuntimeError" in caplog.text
    assert "secret-detail" not in caplog.text


@pytest.mark.asyncio
async def test_nonpositive_service_delay_is_clamped(monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop, delay=0)
    timeout_seen = asyncio.Event()
    observed_timeouts: list[float] = []
    original_wait_for = asyncio.wait_for

    async def observe_wait(awaitable, timeout):
        observed_timeouts.append(timeout)
        timeout_seen.set()
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(scheduler_module.asyncio, "wait_for", observe_wait)
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    try:
        async with asyncio.timeout(1):
            await timeout_seen.wait()
        assert observed_timeouts == [1]
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_repeated_start_creates_one_runner() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    scheduler = CheckinScheduler(lambda: service, lambda: True)

    scheduler.start()
    scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await asyncio.sleep(0)
    await scheduler.stop()

    assert len(service.run_calls) == 1


@pytest.mark.asyncio
async def test_stop_waits_for_in_flight_synchronous_run() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    service.release_run = threading.Event()
    scheduler = CheckinScheduler(lambda: service, lambda: True)
    scheduler.start()
    await asyncio.wait_for(service.run_entered.wait(), timeout=1)

    stopping = asyncio.create_task(scheduler.stop())
    await asyncio.sleep(0)
    assert stopping.done() is False

    service.release_run.set()
    await asyncio.wait_for(stopping, timeout=1)
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_wake_before_start_is_retained() -> None:
    loop = asyncio.get_running_loop()
    service = FakeCheckinService(loop)
    unlock_checks = iter((False, True))
    scheduler = CheckinScheduler(lambda: service, lambda: next(unlock_checks))

    waking_thread = threading.Thread(target=scheduler.wake)
    waking_thread.start()
    waking_thread.join()
    scheduler.start()
    await asyncio.wait_for(service.called.wait(), timeout=1)
    await scheduler.stop()


def test_vault_unlock_notifies_unique_listeners() -> None:
    vault = SecretVault()
    notifications: list[bool] = []

    def listener() -> None:
        notifications.append(vault.is_unlocked)

    vault.add_unlock_listener(listener)
    vault.add_unlock_listener(listener)
    vault.unlock("password")

    assert notifications == [True]


def test_vault_listener_exception_is_isolated(caplog) -> None:
    vault = SecretVault()
    called = False

    def failing_listener() -> None:
        raise RuntimeError("credential-value")

    def successful_listener() -> None:
        nonlocal called
        called = True

    vault.add_unlock_listener(failing_listener)
    vault.add_unlock_listener(successful_listener)
    vault.unlock("password")

    assert vault.is_unlocked is True
    assert called is True
    assert "RuntimeError" in caplog.text
    assert "credential-value" not in caplog.text
