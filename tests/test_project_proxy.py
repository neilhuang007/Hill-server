"""Both public services require Cloudflare peers and authenticated origin pulls."""
import importlib.util
import ipaddress
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('project_proxy', Path(__file__).resolve().parents[1] / 'ops/configure-project-proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class ProjectProxyTest(unittest.TestCase):
    def config(self):
        return {'HILL175_AUTH_MODE': 'development', 'HILL175_BEDROCK_ENABLED': 'true',
                'HILL175_GALLERY_PUBLIC_URL': 'https://builds.example.org',
                'HILL175_BEDROCK_PUBLIC_URL': 'https://bedrock.example.org'}

    def test_services_require_origin_auth_and_cloudflare(self):
        content = proxy.render(self.config(), [ipaddress.ip_network('173.245.48.0/20')])
        self.assertEqual(2, content.count('ssl_verify_client on;'))
        self.assertEqual(2, content.count('if ($hill175_project_cloudflare = 0)'))
        self.assertIn('geo $realip_remote_addr', content)
        self.assertIn('proxy_pass http://127.0.0.1:8788;', content)
        self.assertIn('proxy_pass http://127.0.0.1:19132;', content)
        self.assertIn('location /v1/join', content)
        self.assertIn('access_log off;', content)
        self.assertIn('proxy_cache off;', content)

    def test_rejects_injection_and_ambiguous_hosts(self):
        for url in ('http://example.org', 'https://example.org/path', 'https://user@example.org',
                    'https://example.org:19132', 'https://bad;host.org'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                proxy.sites(self.config() | {'HILL175_BEDROCK_PUBLIC_URL': url})
        with self.assertRaises(ValueError):
            proxy.sites(self.config() | {'HILL175_BEDROCK_PUBLIC_URL': 'https://builds.example.org'})


if __name__ == '__main__':
    unittest.main()
