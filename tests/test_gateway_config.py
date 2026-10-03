from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_gateway_config import validate


class GatewayConfigTest(unittest.TestCase):
    def config(self, address):
        return {
            'services': {'caddy': {
                'image': 'registry.example.com/infra/caddy@sha256:' + 'a' * 64,
                'environment': {'ECHOOO_ADDRESS': address, 'ACME_EMAIL': 'admin@example.com'},
            }},
            'volumes': {'caddy_data': {'name': 'gateway_data'}},
        }

    def test_plain_and_legacy_http_addresses_remain_valid(self):
        for address in ['echooo.example.com', 'http://echooo.example.com', 'http-tools.example.com']:
            with self.subTest(address=address):
                config = self.config(address)
                self.assertIs(validate(config), config)
                self.assertEqual(config['services']['caddy']['environment']['ECHOOO_ADDRESS'], address)

    def test_only_one_leading_http_prefix_is_removed(self):
        for address in ['https://echooo.example.com', 'http://http://echooo.example.com',
                        'echooo.http://example.com']:
            with self.subTest(address=address):
                with self.assertRaisesRegex(ValueError, 'plain hostnames'):
                    validate(self.config(address))

    def test_legacy_prefix_does_not_hide_conflicting_domains(self):
        config = self.config('http://shared.example.com')
        config['services']['caddy']['environment']['SHADOWTABLE_DOMAIN'] = 'SHARED.example.com'
        with self.assertRaisesRegex(ValueError, 'own hostname'):
            validate(config)


if __name__ == '__main__':
    unittest.main()
