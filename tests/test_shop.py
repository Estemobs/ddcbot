import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest  # noqa: F401

import unittest

from data.db import Database
from casino_engine import CasinoEngine
from shop_engine import ShopEngine, ShopError, describe_item, stock_label

GUILD = 111
OTHER = 222
PLAYER = 42


def _shop():
    return ShopEngine(Database(path=":memory:"))


class TestItemCreation(unittest.TestCase):
    def setUp(self):
        self.shop = _shop()

    def test_a_ticket_item_points_at_a_game(self):
        self.shop.create_item(GUILD, "ticket-loto", "Ticket de Loto", "ticket", "loto", 5000)
        item = self.shop.get_item(GUILD, "ticket-loto")
        self.assertEqual((item["kind"], item["value"], item["price"]),
                         ("ticket", "loto", 5000))

    def test_slug_is_normalised(self):
        self.shop.create_item(GUILD, "Ticket De Loto", "x", "item", "y", 1)
        self.assertIsNotNone(self.shop.get_item(GUILD, "ticket-de-loto"))

    def test_lookup_is_case_insensitive(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1)
        self.assertIsNotNone(self.shop.get_item(GUILD, "VIP"))

    def test_a_role_item_needs_a_numeric_id(self):
        with self.assertRaises(ShopError):
            self.shop.create_item(GUILD, "vip", "VIP", "role", "pas-un-id", 1)

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ShopError):
            self.shop.create_item(GUILD, "x", "X", "licorne", "y", 1)

    def test_empty_slug_is_refused(self):
        with self.assertRaises(ShopError):
            self.shop.create_item(GUILD, "   ", "X", "item", "y", 1)

    def test_empty_value_is_refused(self):
        with self.assertRaises(ShopError):
            self.shop.create_item(GUILD, "x", "X", "item", "  ", 1)

    def test_negative_price_is_refused(self):
        with self.assertRaises(ShopError):
            self.shop.create_item(GUILD, "x", "X", "item", "y", -5)

    def test_items_are_per_guild(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1)
        self.assertIsNone(self.shop.get_item(OTHER, "vip"))

    def test_recreating_updates_in_place(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1000)
        self.shop.create_item(GUILD, "vip", "VIP+", "role", "888", 2000)
        item = self.shop.get_item(GUILD, "vip")
        self.assertEqual((item["display_name"], item["value"], item["price"]),
                         ("VIP+", "888", 2000))
        self.assertEqual(len(self.shop.list_items(GUILD)), 1)

    def test_disabled_items_are_hidden_from_players(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1)
        item = self.shop.get_item(GUILD, "vip")
        self.shop.update_item(item["id"], enabled=0)
        self.assertEqual(self.shop.list_items(GUILD), [])
        self.assertEqual(len(self.shop.list_items(GUILD, include_disabled=True)), 1)

    def test_unknown_update_field_is_refused(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1)
        item = self.shop.get_item(GUILD, "vip")
        with self.assertRaises(ShopError):
            self.shop.update_item(item["id"], couleur="rouge")

    def test_delete(self):
        self.shop.create_item(GUILD, "vip", "VIP", "role", "777", 1)
        self.assertTrue(self.shop.delete_item(GUILD, "vip"))
        self.assertFalse(self.shop.delete_item(GUILD, "vip"))


class TestPurchaseRules(unittest.TestCase):
    def setUp(self):
        self.shop = _shop()
        self.shop.create_item(GUILD, "ticket-loto", "Ticket", "ticket", "loto", 5000)
        self.item = self.shop.get_item(GUILD, "ticket-loto")

    def _check(self, **kwargs):
        kwargs.setdefault("balance", 10 ** 9)
        quantity = kwargs.pop("quantity", 1)
        item = kwargs.pop("item", self.item)
        return self.shop.check_purchase(item, GUILD, PLAYER, quantity, **kwargs)

    def test_enough_money_allows_the_purchase(self):
        self.assertIsNone(self._check(balance=5000))

    def test_not_enough_money_is_refused(self):
        self.assertIsNotNone(self._check(balance=4999))

    def test_quantity_multiplies_the_price(self):
        self.assertIsNone(self._check(quantity=2, balance=10000))
        self.assertIsNotNone(self._check(quantity=2, balance=9999))

    def test_zero_or_negative_quantity_is_refused(self):
        for quantity in (0, -3):
            with self.subTest(quantity=quantity):
                self.assertIsNotNone(self._check(quantity=quantity))

    def test_disabled_item_cannot_be_bought(self):
        self.shop.update_item(self.item["id"], enabled=0)
        self.assertIsNotNone(self._check(item=self.shop.get_item(GUILD, "ticket-loto")))

    def test_required_role_gates_the_purchase(self):
        self.shop.update_item(self.item["id"], required_role_id=777)
        gated = self.shop.get_item(GUILD, "ticket-loto")
        self.assertIsNotNone(self._check(item=gated, role_ids=[1]))
        self.assertIsNone(self._check(item=gated, role_ids=[777]))

    def test_out_of_stock(self):
        self.shop.update_item(self.item["id"], stock=0)
        self.assertIsNotNone(self._check(item=self.shop.get_item(GUILD, "ticket-loto")))

    def test_cannot_buy_more_than_the_stock(self):
        self.shop.update_item(self.item["id"], stock=2)
        limited = self.shop.get_item(GUILD, "ticket-loto")
        self.assertIsNotNone(self._check(item=limited, quantity=3))
        self.assertIsNone(self._check(item=limited, quantity=2))

    def test_unlimited_stock_is_never_exhausted(self):
        self.assertEqual(self.item["stock"], -1)
        self.assertIsNone(self._check(quantity=1000))

    def test_per_user_limit(self):
        self.shop.update_item(self.item["id"], per_user_limit=2)
        limited = self.shop.get_item(GUILD, "ticket-loto")
        self.shop.record_purchase(GUILD, PLAYER, limited, 2)
        self.assertIsNotNone(self._check(item=limited))
        # La limite est par joueur : un autre membre peut encore acheter.
        self.assertIsNone(
            self.shop.check_purchase(limited, GUILD, 999, 1, balance=10 ** 9)
        )


class TestPurchaseRecording(unittest.TestCase):
    def setUp(self):
        self.shop = _shop()
        self.shop.create_item(GUILD, "boisson", "Boisson", "item", "Canette", 100, stock=3)
        self.item = self.shop.get_item(GUILD, "boisson")

    def test_limited_stock_decreases(self):
        self.shop.record_purchase(GUILD, PLAYER, self.item, 2)
        self.assertEqual(self.shop.get_item(GUILD, "boisson")["stock"], 1)

    def test_stock_never_goes_negative(self):
        self.shop.record_purchase(GUILD, PLAYER, self.item, 10)
        self.assertEqual(self.shop.get_item(GUILD, "boisson")["stock"], 0)

    def test_unlimited_stock_is_untouched(self):
        self.shop.create_item(GUILD, "infini", "Infini", "item", "X", 1)
        item = self.shop.get_item(GUILD, "infini")
        self.shop.record_purchase(GUILD, PLAYER, item, 50)
        self.assertEqual(self.shop.get_item(GUILD, "infini")["stock"], -1)

    def test_total_is_price_times_quantity(self):
        self.assertEqual(self.shop.record_purchase(GUILD, PLAYER, self.item, 3), 300)

    def test_sales_are_aggregated(self):
        self.shop.record_purchase(GUILD, PLAYER, self.item, 2)
        self.shop.record_purchase(GUILD, 999, self.item, 1)
        stats = self.shop.sales_stats(GUILD)
        self.assertEqual((stats["orders"], stats["units"], stats["revenue"]), (2, 3, 300))

    def test_sales_are_per_guild(self):
        self.shop.record_purchase(GUILD, PLAYER, self.item, 1)
        self.assertEqual(self.shop.sales_stats(OTHER)["units"], 0)


class TestTheFullChain(unittest.TestCase):
    """Boutique -> ticket -> jeu reserve aux tickets : c'est ce qui manquait."""

    def setUp(self):
        db = Database(path=":memory:")
        self.shop = ShopEngine(db)
        self.casino = CasinoEngine(db)
        self.casino.create_game(GUILD, "loto", "Loto", price=0,
                                access=[{"kind": "ticket"}])
        self.shop.create_item(GUILD, "ticket-loto", "Ticket", "ticket", "loto", 5000)

    def test_a_ticket_only_game_is_unreachable_without_buying(self):
        game = self.casino.get_game(GUILD, "loto")
        self.assertIsNone(
            self.casino.resolve_access(game, has_ticket=False, balance=10 ** 9)
        )

    def test_buying_the_ticket_opens_the_game(self):
        # Ce que fait ,acheter : deposer l'entree dans l'inventaire.
        self.casino.add_item(GUILD, PLAYER, "loto", "ticket")
        game = self.casino.get_game(GUILD, "loto")
        chosen = self.casino.resolve_access(
            game, has_ticket=self.casino.has_ticket(GUILD, PLAYER, "loto")
        )
        self.assertEqual(chosen["kind"], "ticket")

    def test_the_ticket_is_consumed_once(self):
        self.casino.add_item(GUILD, PLAYER, "loto", "ticket")
        self.assertTrue(self.casino.take_ticket(GUILD, PLAYER, "loto"))
        self.assertFalse(self.casino.has_ticket(GUILD, PLAYER, "loto"))


class TestDescriptions(unittest.TestCase):
    def test_each_kind_is_described(self):
        self.assertIn("loto", describe_item({"kind": "ticket", "value": "loto"}))
        self.assertIn("VIP", describe_item({"kind": "role", "value": "777"},
                                           role_names={777: "VIP"}))
        self.assertIn("Canette", describe_item({"kind": "item", "value": "Canette"}))

    def test_an_unknown_role_falls_back_to_its_id(self):
        self.assertIn("777", describe_item({"kind": "role", "value": "777"}))

    def test_stock_label(self):
        self.assertEqual(stock_label({"stock": -1}), "∞")
        self.assertEqual(stock_label({"stock": 5}), "5")


class TestCommandNaming(unittest.TestCase):
    """`,shop` listait des jeux sans rien vendre : le nom part a la boutique."""

    def setUp(self):
        from cogs.diagnostics import EXPECTED_COMMANDS
        self.expected = EXPECTED_COMMANDS

    def test_the_catalogue_is_now_jeux(self):
        self.assertIn("jeux", self.expected)

    def test_shop_is_no_longer_the_catalogue(self):
        self.assertNotIn("shop", self.expected)

    def test_the_shop_commands_exist(self):
        for name in ("boutique", "acheter", "shopadd", "shopdel", "shopstats"):
            with self.subTest(command=name):
                self.assertIn(name, self.expected)

    def test_shop_stays_reachable_as_an_alias_of_boutique(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parent.parent / "cogs" / "boutique.py").read_text()
        self.assertIn('aliases=["shop"]', source)

    def test_shop_admin_commands_are_gated(self):
        from admin import ADMIN_COMMANDS
        for name in ("shopadd", "shopdel", "shopstats"):
            with self.subTest(command=name):
                self.assertIn(name, ADMIN_COMMANDS)

    def test_buying_is_open_to_everyone(self):
        from admin import ADMIN_COMMANDS
        self.assertNotIn("acheter", ADMIN_COMMANDS)
        self.assertNotIn("boutique", ADMIN_COMMANDS)


if __name__ == "__main__":
    unittest.main()
