import math
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from threading import RLock
from typing import Any, Protocol

from app.config.repository import ConfigKey, ConfigRepository


_DEFAULT_EXECUTION_TIME = "09:00"
_RETRY_DELAY = timedelta(minutes=30)
_DISABLED_WAIT_SECONDS = 24 * 60 * 60
_state_lock = RLock()


class _CheckinClient(Protocol):
    def check_in(self) -> None:
        """执行一次第三方签到。

        Raises:
            Exception: 第三方签到失败。
        """
        ...


class CheckinService:
    """管理每日签到配置、执行资格、重试和持久化状态。"""

    def __init__(
        self,
        repository: ConfigRepository,
        client_factory: Callable[[dict[str, Any]], _CheckinClient],
        timezone: tzinfo,
    ) -> None:
        self._repository = repository
        self._client_factory = client_factory
        self._timezone = timezone

    def read_settings(self) -> dict[str, Any]:
        """返回归一化后的公开签到设置与运行状态。

        Returns:
            不包含内部重试字段的签到设置与运行状态。

        Raises:
            ValueError: 已有加密配置无效。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        return self._public_view(self._load())

    def save_settings(self, enabled: bool, execution_time: time) -> dict[str, Any]:
        """保存签到开关和执行时间，并保留已有运行状态。

        Args:
            enabled: 是否启用每日签到。
            execution_time: 应用时区内的每日执行时间。

        Returns:
            保存后的公开签到设置与运行状态。

        Raises:
            ValueError: 已有加密配置无效。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读写失败。
        """
        with _state_lock:
            value = self._load()
            value["enabled"] = enabled
            value["execution_time"] = execution_time.strftime("%H:%M")
            self._repository.set_secret(ConfigKey.MTEAM_CHECKIN, value)
            return self._public_view(value)

    def run_due(self, now: datetime) -> bool:
        """在满足每日执行和重试约束时尝试一次签到。

        Args:
            now: 带时区的当前时间。

        Returns:
            本次是否实际消耗了一次签到尝试。

        Raises:
            ValueError: 当前时间不带时区或已有加密配置无效。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读写失败。
        """
        with _state_lock:
            local_now = self._local_time(now)
            value = self._load()
            local_date = local_now.date().isoformat()
            if not self._is_due(value, local_now, local_date):
                return False

            attempts = self._attempts_for(value, local_date) + 1
            value.update(
                {
                    "last_attempt_at": local_now.isoformat(timespec="seconds"),
                    "attempt_date": local_date,
                    "attempts_on_date": attempts,
                }
            )
            connection = self._repository.get_secret(ConfigKey.MTEAM_CONNECTION)
            if connection is None:
                value.update(success=False, message="站点尚未配置")
            else:
                try:
                    self._client_factory(connection).check_in()
                except Exception:
                    value.update(success=False, message="签到失败")
                else:
                    value.update(
                        last_success_date=local_date,
                        success=True,
                        message="签到成功",
                    )
            self._repository.set_secret(ConfigKey.MTEAM_CHECKIN, value)
            return True

    def seconds_until_next(self, now: datetime) -> int:
        """计算到下一次可能执行签到的有限等待秒数。

        Args:
            now: 带时区的当前时间。

        Returns:
            不小于一秒的等待时长；禁用时返回二十四小时。

        Raises:
            ValueError: 当前时间不带时区或已有加密配置无效。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        local_now = self._local_time(now)
        value = self._load()
        if not value["enabled"]:
            return _DISABLED_WAIT_SECONDS

        local_date = local_now.date().isoformat()
        scheduled = self._scheduled_at(local_now.date(), value["execution_time"])
        next_scheduled = self._scheduled_at(
            local_now.date() + timedelta(days=1),
            value["execution_time"],
        )
        if self._instant(local_now) < self._instant(scheduled):
            return self._seconds_between(local_now, scheduled)
        if value["last_success_date"] == local_date:
            return self._seconds_between(local_now, next_scheduled)

        attempts = self._attempts_for(value, local_date)
        if attempts == 0:
            return 1
        if attempts == 1:
            last_attempt = self._parse_attempt(value["last_attempt_at"])
            if last_attempt is None:
                return 1
            retry_at = self._instant(last_attempt) + _RETRY_DELAY
            retry_local_date = retry_at.astimezone(self._timezone).date()
            if retry_local_date != local_now.date():
                return self._seconds_between(local_now, next_scheduled)
            return self._seconds_between(local_now, retry_at)
        return self._seconds_between(local_now, next_scheduled)

    def _is_due(
        self,
        value: dict[str, Any],
        local_now: datetime,
        local_date: str,
    ) -> bool:
        """判断当前时刻是否允许消耗一次签到尝试。

        Args:
            value: 已归一化的签到配置和状态。
            local_now: 转换到应用时区的当前时间。
            local_date: 当前本地日期的 ISO 字符串。

        Returns:
            当前时刻允许尝试时返回 True。
        """
        if not value["enabled"]:
            return False
        scheduled = self._scheduled_at(local_now.date(), value["execution_time"])
        if (
            self._instant(local_now) < self._instant(scheduled)
            or value["last_success_date"] == local_date
        ):
            return False
        attempts = self._attempts_for(value, local_date)
        if attempts >= 2:
            return False
        if attempts == 0:
            return True
        last_attempt = self._parse_attempt(value["last_attempt_at"])
        return last_attempt is None or self._instant(local_now) >= (
            self._instant(last_attempt) + _RETRY_DELAY
        )

    def _load(self) -> dict[str, Any]:
        """读取并归一化旧版或缺字段的签到配置。

        Returns:
            包含公开设置和内部重试字段的完整配置。

        Raises:
            ValueError: 加密配置无法解密或结构无效。
            sqlalchemy.exc.SQLAlchemyError: 配置仓库读取失败。
        """
        stored = self._repository.get_secret(ConfigKey.MTEAM_CHECKIN)
        if stored is None:
            stored = {}
        value = dict(stored)
        value["enabled"] = stored.get("enabled", False) is True
        value["execution_time"] = self._normalize_execution_time(
            stored.get("execution_time")
        )
        value["last_attempt_at"] = stored.get("last_attempt_at")
        value["last_success_date"] = stored.get("last_success_date")
        value["attempt_date"] = stored.get("attempt_date")
        value["attempts_on_date"] = self._normalize_attempts(
            stored.get("attempts_on_date")
        )
        value["success"] = stored.get("success")
        value["message"] = stored.get("message")
        return value

    def _local_time(self, now: datetime) -> datetime:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("当前时间必须包含时区")
        return now.astimezone(self._timezone)

    @staticmethod
    def _normalize_execution_time(raw: object) -> str:
        if not isinstance(raw, str):
            return _DEFAULT_EXECUTION_TIME
        try:
            parsed = time.fromisoformat(raw)
        except ValueError:
            return _DEFAULT_EXECUTION_TIME
        return parsed.strftime("%H:%M")

    @staticmethod
    def _normalize_attempts(raw: object) -> int:
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            return 0
        return raw

    @staticmethod
    def _attempts_for(value: dict[str, Any], local_date: str) -> int:
        if value["attempt_date"] != local_date:
            return 0
        return value["attempts_on_date"]

    @staticmethod
    def _parse_attempt(raw: object) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    def _scheduled_at(self, local_date: date, execution_time: str) -> datetime:
        """构造每日执行时刻，歧义或不存在的本地时间固定选择 fold=0。

        Args:
            local_date: 应用时区内的执行日期。
            execution_time: 已归一化为 HH:MM 的执行时间。

        Returns:
            带应用时区且 fold 固定为 0 的执行时刻。
        """
        scheduled = datetime.combine(
            local_date,
            time.fromisoformat(execution_time),
            self._timezone,
        )
        return scheduled.replace(fold=0)

    @staticmethod
    def _instant(value: datetime) -> datetime:
        return value.astimezone(UTC)

    @staticmethod
    def _seconds_between(now: datetime, target: datetime) -> int:
        elapsed = target.astimezone(UTC) - now.astimezone(UTC)
        return max(1, math.ceil(elapsed.total_seconds()))

    @staticmethod
    def _public_view(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": value["enabled"],
            "execution_time": value["execution_time"],
            "last_attempt_at": value["last_attempt_at"],
            "last_success_date": value["last_success_date"],
            "success": value["success"],
            "message": value["message"],
        }
