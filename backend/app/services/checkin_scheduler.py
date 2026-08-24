import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol


logger = logging.getLogger(__name__)


class _ScheduledCheckin(Protocol):
    def run_due(self, now: datetime) -> bool:
        """执行当前到期的签到。

        Args:
            now: 带时区的当前时间。

        Returns:
            实际发起签到时返回 True。
        """
        ...

    def seconds_until_next(self, now: datetime) -> int:
        """返回下一次检查前的等待秒数。

        Args:
            now: 带时区的当前时间。

        Returns:
            下一次检查前的等待秒数。
        """
        ...


class CheckinScheduler:
    """在单一异步任务中调度同步签到模块。"""

    def __init__(
        self,
        service_factory: Callable[[], _ScheduledCheckin],
        unlocked: Callable[[], bool],
        fallback_delay: float = 60,
    ) -> None:
        """初始化调度器及其线程安全唤醒 seam。

        Args:
            service_factory: 解锁后惰性获取签到模块的工厂。
            unlocked: 判断敏感配置保险库是否已解锁的函数。
            fallback_delay: 意外异常后的重试等待秒数。

        Raises:
            ValueError: 回退等待时间不是正数。
        """
        if fallback_delay <= 0:
            raise ValueError("回退等待时间必须为正数")
        self._service_factory = service_factory
        self._unlocked = unlocked
        self._fallback_delay = fallback_delay
        self._state_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake_event: asyncio.Event | None = None
        self._stop_event: asyncio.Event | None = None
        self._runner: asyncio.Task[None] | None = None
        self._wake_generation = 0

    @property
    def is_running(self) -> bool:
        """判断调度任务是否正在运行。"""
        with self._state_lock:
            return self._runner is not None and not self._runner.done()

    def start(self) -> None:
        """在当前事件循环启动唯一调度任务，重复调用保持幂等。

        Raises:
            RuntimeError: 当前线程没有正在运行的事件循环。
        """
        loop = asyncio.get_running_loop()
        with self._state_lock:
            if self._runner is not None and not self._runner.done():
                return
            self._loop = loop
            self._wake_event = asyncio.Event()
            self._stop_event = asyncio.Event()
            self._runner = loop.create_task(
                self._run(),
                name="checkin-scheduler",
            )

    async def stop(self) -> None:
        """请求停止并等待同步签到完成及调度任务退出。"""
        with self._state_lock:
            runner = self._runner
            stop_event = self._stop_event
            wake_event = self._wake_event
        if runner is None:
            return
        if stop_event is not None:
            stop_event.set()
        if wake_event is not None:
            wake_event.set()
        await runner
        with self._state_lock:
            if self._runner is runner:
                self._runner = None
                self._loop = None
                self._wake_event = None
                self._stop_event = None

    def wake(self) -> None:
        """线程安全地唤醒调度任务，启动前的信号也会保留。"""
        with self._state_lock:
            self._wake_generation += 1
            loop = self._loop
            wake_event = self._wake_event
            if loop is None or wake_event is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(wake_event.set)

    async def _run(self) -> None:
        """持续执行到期签到并根据配置或异常安排下一轮。"""
        seen_generation = 0
        while not self._is_stopping():
            delay: float | None = None
            try:
                if self._unlocked():
                    service = self._service_factory()
                    now = datetime.now(UTC)
                    await asyncio.to_thread(service.run_due, now)
                    if self._is_stopping():
                        break
                    delay = max(
                        1,
                        await asyncio.to_thread(
                            service.seconds_until_next,
                            datetime.now(UTC),
                        ),
                    )
            except Exception as error:
                logger.warning("自动签到调度异常类型: %s", type(error).__name__)
                delay = self._fallback_delay
            if self._is_stopping():
                break
            seen_generation = await self._wait(delay, seen_generation)

    async def _wait(self, delay: float | None, seen_generation: int) -> int:
        """等待超时、停止或新唤醒代次，同时封闭丢失唤醒窗口。

        Args:
            delay: 等待秒数；None 表示仅等待显式信号。
            seen_generation: 调度任务已处理的唤醒代次。

        Returns:
            等待结束时观察到的最新唤醒代次。
        """
        with self._state_lock:
            current_generation = self._wake_generation
            wake_event = self._wake_event
            if current_generation != seen_generation:
                return current_generation
            if wake_event is None:
                return current_generation
            wake_event.clear()
        try:
            if delay is None:
                await wake_event.wait()
            else:
                await asyncio.wait_for(wake_event.wait(), timeout=delay)
        except TimeoutError:
            pass
        with self._state_lock:
            return self._wake_generation

    def _is_stopping(self) -> bool:
        """判断当前运行代次是否已收到停止请求。"""
        stop_event = self._stop_event
        return stop_event is not None and stop_event.is_set()
