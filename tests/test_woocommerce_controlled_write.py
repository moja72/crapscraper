from __future__ import annotations

import json
import unittest

from app.integrations.woocommerce import WooCommerceClient
from app.integrations.woocommerce_version import (
    WooCommerceVersionWriter, VersionConfirmationError, controlled_product_patch,
)
from app.integrations.wordpress import IntegrationError


class ControlledWooWriteTests(unittest.TestCase):
    @staticmethod
    def product(value="28.4.1.1", meta_id=5942764):
        return {"id": 94567, "meta_data": [{"id": meta_id, "key": "pt_versao", "value": value}]}

    def writer_case(self, put_body, get_body, status=200):
        responses = [self.product(), get_body]
        class Woo:
            def get_product(self, _id): return responses.pop(0)
        evidence = {"http_status": status, "response_body_present": put_body is not None,
                    "product_id": put_body.get("id") if put_body else None,
                    "put_pt_versao": (put_body.get("meta_data") or [{}])[0].get("value") if put_body and put_body.get("meta_data") else None,
                    "put_meta_id": (put_body.get("meta_data") or [{}])[0].get("id") if put_body and put_body.get("meta_data") else None,
                    "confirmation_status": "pending_get"}
        writer = WooCommerceVersionWriter(Woo(), write_enabled=True,
                                           patch=lambda *_: dict(evidence))
        plan = writer.prepare(94567, "28.4.1.1", "28.5.7")
        return writer, plan

    def test_apply_put_and_get_confirmation_matrix(self):
        correct = self.product("28.5.7")
        writer, plan = self.writer_case(correct, correct)
        self.assertEqual(writer.apply_and_confirm(plan)["confirmation_status"], "confirmed")
        for put, get in ((correct, self.product()), ({"id": 94567, "meta_data": []}, correct),
                         (self.product("28.4.1.1"), correct)):
            with self.subTest(put=put, get=get):
                writer, plan = self.writer_case(put, get)
                with self.assertRaises(VersionConfirmationError): writer.apply_and_confirm(plan)

    def test_confirmation_and_prepare_prefer_cache_busted_product_reads(self):
        calls = []
        class Woo:
            def get_product(self, _id):
                raise AssertionError("critical version reads must not use the cacheable URL")
            def get_product_fresh(self, _id):
                calls.append(_id)
                return self.product
        woo = Woo()
        woo.product = self.product()
        writer = WooCommerceVersionWriter(
            woo, write_enabled=True,
            patch=lambda *_: {
                "http_status": 200, "response_body_present": True,
                "product_id": 94567, "put_pt_versao": "28.5.7",
                "put_meta_id": 5942764, "confirmation_status": "pending_get",
            },
        )
        plan = writer.prepare(94567, "28.4.1.1", "28.5.7")
        woo.product = self.product("28.5.7")
        evidence = writer.apply_and_confirm(plan)
        self.assertEqual(calls, [94567, 94567])
        self.assertTrue(evidence["get_cache_busted"])

    def test_fresh_product_get_uses_unique_cache_buster_and_remains_read_only(self):
        requests = []
        def transport(request, _timeout):
            requests.append(request)
            return 200, {"X-LiteSpeed-Cache": "miss"}, b'{"id":94567,"meta_data":[]}'
        woo = WooCommerceClient("https://example.test", "ck", "cs", transport=transport)
        woo.get_product_fresh(94567)
        woo.get_product_fresh(94567)
        self.assertEqual([request.method for request in requests], ["GET", "GET"])
        self.assertNotEqual(requests[0].full_url, requests[1].full_url)
        self.assertTrue(all("_crapscraper_fresh=" in request.full_url for request in requests))

    def test_put_204_without_body_allows_confirming_get(self):
        writer, plan = self.writer_case(None, self.product("28.5.7"), status=204)
        self.assertEqual(writer.apply_and_confirm(plan)["confirmation_status"], "confirmed")

    def test_controlled_patch_rejects_all_http_errors(self):
        payload = {"meta_data": [{"id": 1, "key": "pt_versao", "value": "2"}]}
        for status in (400, 401, 403, 500):
            woo = WooCommerceClient("https://example.test", "ck", "cs",
                                    transport=lambda *_args, status=status: (status, {}, b'{}'))
            with self.subTest(status=status), self.assertRaisesRegex(IntegrationError, str(status)):
                controlled_product_patch(woo, 94567, payload)

    def test_prepare_uses_current_meta_id_and_blocks_changed_value(self):
        class Woo:
            def __init__(self, value): self.value = value
            def get_product(self, _id): return self.product
        woo = Woo("28.4.1.1"); woo.product = self.product(meta_id=5942764)
        plan = WooCommerceVersionWriter(woo).prepare(94567, "28.4.1.1", "28.5.7")
        self.assertEqual(plan.meta_id, 5942764)
        woo.product = self.product("changed", meta_id=999)
        with self.assertRaises(IntegrationError):
            WooCommerceVersionWriter(woo).prepare(94567, "28.4.1.1", "28.5.7")

    def test_rollback_is_confirmed_by_get(self):
        original, updated = self.product(), self.product("28.5.7")
        responses = [original, original]
        class Woo:
            def get_product(self, _id): return responses.pop(0)
        writer = WooCommerceVersionWriter(Woo(), write_enabled=True,
            patch=lambda *_: {"http_status":200,"response_body_present":True,"product_id":94567,
                              "put_pt_versao":"28.4.1.1","put_meta_id":5942764,
                              "confirmation_status":"pending_get"})
        plan = writer.prepare(94567, "28.4.1.1", "28.5.7")
        self.assertEqual(writer.apply_and_confirm(plan, rollback=True)["confirmation_status"], "confirmed")
    def test_put_uses_consolidated_auth_and_exact_pt_versao_payload(self):
        captured = {}
        def transport(request, _timeout):
            captured.update(method=request.method, url=request.full_url,
                            authorization=request.headers.get("Authorization"),
                            payload=json.loads(request.data))
            return 200, {}, b'{"id":94567}'
        woo = WooCommerceClient("https://example.test", "ck", "cs", transport=transport)
        payload = {"meta_data": [{"id": 5940076, "key": "pt_versao", "value": "28.5.7"}]}
        controlled_product_patch(woo, 94567, payload)
        self.assertEqual(captured["method"], "PUT")
        self.assertTrue(captured["url"].endswith("/wp-json/wc/v3/products/94567"))
        self.assertEqual(captured["authorization"], woo._authorization())
        self.assertEqual(captured["payload"], payload)

    def test_payload_cannot_create_or_modify_any_other_field(self):
        woo = WooCommerceClient("https://example.test", "ck", "cs",
                                transport=lambda *_: (200, {}, b"{}"))
        bad = ({"name": "changed"},
               {"meta_data": [{"key": "pt_versao", "value": "2"}]},
               {"meta_data": [{"id": 1, "key": "other", "value": "2"}]})
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(IntegrationError):
                controlled_product_patch(woo, 94567, payload)

    def test_writer_preserves_original_meta_id_key_and_value_for_rollback(self):
        class Woo:
            def get_product(self, _id):
                return {"id": 94567, "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "28.4.1.1"}]}
        writer = WooCommerceVersionWriter(Woo())
        plan = writer.prepare(94567, "28.4.1.1", "28.5.7")
        self.assertEqual(plan.rollback_payload(), {
            "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "28.4.1.1"}]
        })

    def test_writer_rejects_missing_or_duplicate_pt_versao(self):
        for metadata in ([], [{"id": 1, "key": "pt_versao", "value": "1"},
                               {"id": 2, "key": "pt_versao", "value": "1"}]):
            class Woo:
                def get_product(self, _id): return {"meta_data": metadata}
            with self.subTest(metadata=metadata), self.assertRaises(IntegrationError):
                WooCommerceVersionWriter(Woo()).prepare(94567, "1", "2")


if __name__ == "__main__": unittest.main()
