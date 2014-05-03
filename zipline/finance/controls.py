#
# Copyright 2014 Quantopian, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import abc

from six import with_metaclass

from zipline.errors import TradingControlViolation

class TradingControl(with_metaclass(abc.ABCMeta)):
    """
    Abstract base class representing a fail-safe control on the behavior of any
    algorithm.
    """

    @abc.abstractmethod
    def validate(self,
                 sid,
                 amount,
                 portfolio,
                 algo_datetime,
                 algo_current_data):
        """
        Before any order is executed by TradingAlgorithm, this method should be
        called *exactly once* on each registered TradingControl object.

        If the specified sid and amount do not violate this TradingControl's
        restraint given the information in `portfolio`, this method should
        return None and have no externally-visible side-effects.

        If the desired order violates this TradingControl's contraint, this
        method should call self.fail(sid, amount).
        """
        raise NotImplementedError

    def fail(self, sid, amount):
        """
        Raise a TradingControlViolation with information about the failure.
        """
        raise TradingControlViolation(sid=sid,
                                      amount=amount,
                                      constraint=repr(self))


class MaxOrderCount(TradingControl):
    """
    TradingControl representing a limit on the number of orders that can be
    placed in a given trading day.
    """

    def __init__(self, max_count):
        self.orders_placed = 0
        self.max_count = max_count
        self.current_date = None

    def validate(self,
                 sid,
                 amount,
                 _portfolio,
                 algo_datetime,
                 _algo_current_data):
        algo_date = algo_datetime.date()

        # Reset order count if it's a new day.
        if self.current_date and self.current_date != algo_date:
            self.orders_placed = 0
        self.current_date = algo_date

        if self.orders_placed >= self.max_count:
            self.fail(sid, amount)
        self.orders_placed += 1


class MaxOrderSize(TradingControl):
    """
    TradingControl representing a limit on the magnitude of any single order
    placed with the given security.  Can be specified by share or by dollar
    value.
    """

    def __init__(self, sid, max_shares=None, max_notional=None):
        self.sid = sid
        self.max_shares = max_shares
        self.max_notional = max_notional

        if max_shares is None and max_notional is None:
            raise ValueError(
                "Must supply at least one of max_shares and max_notional"
            )

        if max_shares and max_shares < 0:
            raise ValueError(
                "max_shares cannot be negative."
            )

        if max_notional and max_notional < 0:
            raise ValueError(
                "max_notional must be positive."
            )

    def validate(self,
                 sid,
                 amount,
                 portfolio,
                 _algo_datetime,
                 algo_current_data):

        if sid != self.sid:
            return

        if self.max_shares is not None and amount > self.max_shares:
            self.fail(sid, amount)

        current_sid_price = algo_current_data[sid].price
        order_price = amount * current_sid_price

        if self.max_notional is not None and order_price > self.max_notional:
            self.fail(sid, amount)


class MaxPositionSize(TradingControl):
    """
    TradingControl representing a limit on the maximum position size that can
    be held by an algo for a given security.
    """

    def __init__(self, sid, max_shares=None, max_notional=None):
        self.sid = sid
        self.max_shares = max_shares
        self.max_notional = max_notional

        if max_shares is None and max_notional is None:
            raise ValueError(
                "Must supply at least one of max_shares and max_notional"
            )

        if max_shares and max_shares < 0:
            raise ValueError(
                "max_shares cannot be negative."
            )

        if max_notional and max_notional < 0:
            raise ValueError(
                "max_notional must be positive."
            )

    def validate(self,
                 sid,
                 amount,
                 portfolio,
                 algo_datetime,
                 algo_current_data):

        if sid != self.sid:
            return

        current_share_count = portfolio.positions[sid].amount
        shares_post_order = abs(current_share_count + amount)

        if self.max_shares is not None and shares_post_order > self.max_shares:
            self.fail(sid, amount)

        current_price = algo_current_data[sid].price
        value_post_order = shares_post_order * current_price

        if self.max_notional and abs(value_post_order) > self.max_notional:
            self.fail(sid, amount)


class LongOnly(TradingControl):
    """
    TradingControl representing a prohibition against holding short positions.
    """

    def validate(self,
                 sid,
                 amount,
                 portfolio,
                 _algo_datetime,
                 _algo_current_data):
        """
        Fail if we would hold negative shares of sid after completing this order.
        """
        if portfolio.positions[sid].amount + amount < 0:
            self.fail(sid, amount)
