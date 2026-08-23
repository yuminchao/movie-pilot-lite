import hashlib
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Protocol

from sqlalchemy import select

from app.db.models import DownloadRecord
from app.db.session import Database
from app.integrations.qbittorrent import QbittorrentError, TorrentTask
from app.services.tokens import SourceTokenCodec


class DownloadSource(Protocol):
    """提供临时下载地址的站点端口。"""

    def get_download_url(self, source_id: str) -> str: ...


class DownloadClient(Protocol):
    """提交和查询下载任务的客户端端口。"""

    def add_torrent(
        self,
        url: str,
        category: str,
        save_path: str,
        paused: bool,
    ) -> str | None: ...

    def list_torrents(self) -> list[TorrentTask]: ...


class DownloadService:
    """协调短期来源标识、站点下载地址和 qBittorrent。"""

    def __init__(
        self,
        database: Database,
        token_codec: SourceTokenCodec,
        source: DownloadSource,
        client: DownloadClient,
    ) -> None:
        self._database = database
        self._token_codec = token_codec
        self._source = source
        self._client = client

    def add(
        self,
        source_token: str,
        category: str,
        save_path: str,
        start: bool,
    ) -> tuple[dict[str, Any], bool]:
        """幂等地生成下载地址并提交 qBittorrent。"""
        if not self._is_absolute_path(save_path):
            raise ValueError("保存路径必须是绝对路径")
        if not category or len(category) > 100:
            raise ValueError("qBittorrent 分类无效")
        source_data = self._token_codec.decode(source_token)
        source_id = source_data["source_id"]
        idempotency_key = hashlib.sha256(
            f"{source_id}\0{category}\0{save_path}".encode("utf-8")
        ).hexdigest()
        with self._database.session_factory() as session:
            existing = session.scalar(
                select(DownloadRecord).where(
                    DownloadRecord.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                return self._record_to_dict(existing), False

        download_url = self._source.get_download_url(source_id)
        torrent_hash = self._client.add_torrent(
            download_url,
            category=category,
            save_path=save_path,
            paused=not start,
        )
        record = DownloadRecord(
            title=source_data["title"],
            source_id=source_id,
            source_url=None,
            qb_hash=torrent_hash,
            idempotency_key=idempotency_key,
            category=category,
            save_path=save_path,
            status="queued",
        )
        with self._database.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._record_to_dict(record), True

    def list(self) -> dict[str, Any]:
        """合并本地下载记录和 qBittorrent 实时状态。"""
        with self._database.session_factory() as session:
            records = list(
                session.scalars(
                    select(DownloadRecord).order_by(DownloadRecord.ctime.desc())
                )
            )
        stale = False
        tasks_by_hash: dict[str, TorrentTask] = {}
        try:
            tasks_by_hash = {
                task.torrent_hash.lower(): task for task in self._client.list_torrents()
            }
        except QbittorrentError:
            stale = True
        items = []
        for record in records:
            item = self._record_to_dict(record)
            task = tasks_by_hash.get((record.qb_hash or "").lower())
            if task:
                item.update(
                    {
                        "status": task.status,
                        "progress": task.progress,
                        "download_speed": task.download_speed,
                        "eta": task.eta,
                        "save_path": task.save_path or record.save_path,
                    }
                )
            else:
                item.update({"progress": None, "download_speed": None, "eta": None})
            items.append(item)
        return {
            "items": items,
            "stale": stale,
            "refreshed_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _is_absolute_path(value: str) -> bool:
        return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()

    @staticmethod
    def _record_to_dict(record: DownloadRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "title": record.title,
            "source_id": record.source_id,
            "qb_hash": record.qb_hash,
            "category": record.category,
            "save_path": record.save_path,
            "status": record.status,
            "error_message": record.error_message,
            "created_at": record.ctime.isoformat(),
        }

