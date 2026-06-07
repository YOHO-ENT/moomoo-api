# -*- coding: utf-8 -*-
"""Safety helpers for example scripts."""

import os

import moomoo as ft


ALLOW_REAL_TRADING_ENV = 'MOOMOO_ALLOW_REAL_TRADING'
TRADE_UNLOCK_PASSWORD_ENV = 'MOOMOO_TRADE_UNLOCK_PASSWORD'
INIT_RSA_FILE_ENV = 'MOOMOO_INIT_RSA_FILE'


def configure_security_from_env():
    rsa_file = os.environ.get(INIT_RSA_FILE_ENV)
    if rsa_file:
        ft.SysConfig.set_init_rsa_file(rsa_file)
    return rsa_file


def is_real_trading_allowed():
    return os.environ.get(ALLOW_REAL_TRADING_ENV) == '1'


def require_real_trading_enabled():
    if not is_real_trading_allowed():
        raise RuntimeError(
            "Real trading is disabled for examples. Set {}=1 only after "
            "reviewing the example and accepting the risk.".format(ALLOW_REAL_TRADING_ENV)
        )


def get_trade_unlock_password(required=False):
    password = os.environ.get(TRADE_UNLOCK_PASSWORD_ENV)
    if required and not password:
        raise RuntimeError(
            "Missing trading unlock password. Set {} for real trading examples.".format(
                TRADE_UNLOCK_PASSWORD_ENV
            )
        )
    return password


def guarded_unlock_trade(trade_ctx, trd_env):
    if trd_env != ft.TrdEnv.REAL:
        return ft.RET_OK, "Paper trading does not require unlock_trade."

    require_real_trading_enabled()
    return trade_ctx.unlock_trade(get_trade_unlock_password(required=True))


def ensure_trading_env_allowed(trd_env):
    if trd_env == ft.TrdEnv.REAL:
        require_real_trading_enabled()
