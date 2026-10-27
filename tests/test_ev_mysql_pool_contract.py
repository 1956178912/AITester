"""EV 轮锁：连接池的构造参数必须被**真实依赖**接受，而不是只被 mock 接受。

缺陷：`MySQLClient.__init__` 把 `timeout` 与 `idle_timeout` 传给 `PooledDB`，
但 DBUtils 3.1.2 的 `PooledDB.__init__` 没有这两个形参——多出的关键字参数按
文档会转发给 creator（`pymysql.connect`），而 PyMySQL 也没有这两个形参 ⇒
真实构造/取连接必抛 `TypeError`。既有测试把 `PooledDB` 整体 mock 掉，只断言
mock 收到了 `idle_timeout`，等于给不可执行的构造契约发证书。

本文件的判据分三层：
1. 静态契约：生产 kwargs ⊆ `PooledDB.__init__` 形参 ∪ `pymysql.connect` 形参
   （负对照证明该判据能识别已知不支持的名字）；
2. 真实链路：真 PooledDB + 真 PyMySQL，闭合端口上取连接必须是驱动的
   `OperationalError`（而不是 `TypeError`）——证明构造真的走到了驱动；
3. 配置兑现：`MYSQL_POOL_TIMEOUT` 落到驱动支持的 `connect_timeout`，死连接
   探测落到 PooledDB 支持的 `ping`。

环境说明：测试用 127.0.0.1 上一个刚释放的端口，不需要真实 MySQL 实例；
`_POOL_MIN_CACHED=0` 让构造期不建连，坏参数在取连接时暴露，定位更干净。
"""

from __future__ import annotations

import inspect
import socket

import pymysql
import pytest
from dbutils.pooled_db import PooledDB

from src.db import mysql_client as mysql_client_module
from src.db.mysql_client import MySQLClient

#: PooledDB 自身消费的形参（`*args/**kwargs` 是转发给 creator 的通道，不是形参）。
_POOL_PARAMS = frozenset(inspect.signature(PooledDB.__init__).parameters) - {"self", "args", "kwargs"}
#: 驱动（pymysql.connect）真实接受的形参。
_DRIVER_PARAMS = frozenset(inspect.signature(pymysql.connect).parameters)


def _unsupported_pool_kwargs(kwargs: dict[str, object]) -> set[str]:
    """返回既不是 PooledDB 形参、也不是驱动形参的关键字名（空集 = 契约成立）。"""
    return set(kwargs) - _POOL_PARAMS - _DRIVER_PARAMS


def _closed_port() -> int:
    """取一个刚释放的本机端口：连接它应得到 ECONNREFUSED，不必真起 MySQL。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


@pytest.fixture(autouse=True)
def _isolated_client() -> None:
    MySQLClient._instance = None
    MySQLClient._pool = None
    yield
    MySQLClient._instance = None
    MySQLClient._pool = None


def _capture_pool_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """截获生产构造传给 PooledDB 的 kwargs（只截获，不参与真实性判定）。"""
    captured: dict[str, object] = {}

    def _recorder(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(mysql_client_module, "PooledDB", _recorder)
    MySQLClient()
    return captured


class TestConstructorContract:
    """构造参数与真实依赖签名的契约。"""

    def test_pool_kwargs_are_supported_by_real_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """生产 kwargs 必须全部能被 PooledDB 或驱动接住（当前 timeout/idle_timeout 不是）。"""
        kwargs = _capture_pool_kwargs(monkeypatch)
        assert _unsupported_pool_kwargs(kwargs) == set()

    def test_contract_checker_flags_known_unsupported_kwarg(self) -> None:
        """负对照：判据必须能识别已知不支持的名字（否则上一条是空转）。"""
        assert _unsupported_pool_kwargs({"idle_timeout": 600, "host": "localhost"}) == {"idle_timeout"}
        assert _unsupported_pool_kwargs({"timeout": 30, "connect_timeout": 30}) == {"timeout"}

    def test_pool_knobs_map_to_supported_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """四个 MYSQL_POOL_* 配置必须落到真实形参上，超时走驱动的 connect_timeout。"""
        kwargs = _capture_pool_kwargs(monkeypatch)
        assert kwargs["mincached"] == mysql_client_module._POOL_MIN_CACHED
        assert kwargs["maxcached"] == mysql_client_module._POOL_MAX_CACHED
        assert kwargs["maxconnections"] == mysql_client_module._POOL_MAX_CONNECTIONS
        assert kwargs["connect_timeout"] == mysql_client_module._POOL_CONNECTION_TIMEOUT
        assert "timeout" not in kwargs
        assert "idle_timeout" not in kwargs

    def test_dead_connection_probe_is_wired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """服务端 wait_timeout 断开的空闲连接用 PooledDB 支持的 ping 探测（取连接时）。"""
        kwargs = _capture_pool_kwargs(monkeypatch)
        assert kwargs["ping"] == 1


class TestRealPoolLifecycle:
    """真实 PooledDB + 真实 PyMySQL：构造与取连接必须走到驱动层。"""

    def test_real_pooleddb_construction_reaches_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """闭合端口上取连接应报驱动错误；若报 TypeError，说明构造参数仍被转发错层。"""
        monkeypatch.setattr(mysql_client_module, "_POOL_MIN_CACHED", 0)
        monkeypatch.setattr(mysql_client_module, "_POOL_CONNECTION_TIMEOUT", 1)
        monkeypatch.setattr(mysql_client_module, "MYSQL_HOST", "127.0.0.1")
        monkeypatch.setattr(mysql_client_module, "MYSQL_PORT", _closed_port())

        client = MySQLClient()
        assert MySQLClient.get_pool() is not None

        with pytest.raises(pymysql.err.OperationalError), client.cursor():
            pass
