import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build
import splash


class SplashTests(unittest.TestCase):
    def setUp(self):
        self.manifest = splash.load_manifest(ROOT / 'config/splash.json')
        self.entries = self.manifest['entries']

    def matches(self, url):
        return [e['id'] for e in self.entries if re.search(splash.pattern(e), url)]

    def test_every_endpoint_matches_only_its_bounded_host_and_path(self):
        for entry in self.entries:
            with self.subTest(entry=entry['id']):
                path = entry['path'].replace('{version}', '4')
                prefix = 'https://' + entry['host']
                query = '?' + entry['query'] if entry.get('query') else ''
                extra = '&device=ios' if query else '?device=ios'
                self.assertIn(entry['id'], self.matches(prefix + path + query))
                self.assertIn(entry['id'], self.matches(prefix + path + query + extra))
                self.assertNotIn(entry['id'], self.matches('https://' + entry['host'] + '.evil.test' + path + query))
                self.assertNotIn(entry['id'], self.matches('https://other.example' + path + query))
                self.assertNotIn(entry['id'], self.matches(prefix + '/account/login'))
                if entry['match'] == 'exact':
                    self.assertNotIn(entry['id'], self.matches(prefix + path + 'History' + query))
                    self.assertNotIn(entry['id'], self.matches(prefix + path + '/account' + query))
                else:
                    self.assertIn(entry['id'], self.matches(prefix + path + 'image.jpg'))

    def test_meitu_matches_both_endpoint_and_asset_subtree(self):
        self.assertEqual(self.matches('https://mea.meitudata.com/kaiping'), ['meitu-endpoint'])
        self.assertEqual(self.matches('https://mea.meitudata.com/kaiping/banner.jpg'), ['meitu'])
        self.assertEqual(self.matches('https://mea.meitudata.com/kaipingSettings'), [])

    def test_query_selected_routes_do_not_block_other_proxy_operations(self):
        self.assertEqual(self.matches('https://client.qunar.com/pitcher-proxy?qrt=p_splashAd&device=ios'), ['qunar'])
        self.assertEqual(self.matches('https://weibointl.api.weibo.cn/portal.php?a=get_coopen_ads'), ['weibo-intl'])
        for url in [
            'https://client.qunar.com/pitcher-proxy',
            'https://client.qunar.com/pitcher-proxy?qrt=hotelBooking',
            'https://client.qunar.com/pitcher-proxy?qrt=p_splashAdHistory',
            'https://weibointl.api.weibo.cn/portal.php?a=user_center',
            'https://weibointl.api.weibo.cn/portal.php?a=login&next=a=get_coopen_ads',
        ]:
            self.assertEqual(self.matches(url), [])

    def test_normal_app_traffic_and_reviewed_problem_endpoints_are_untouched(self):
        for url in [
            'https://r.inews.qq.com/getNewsRemoteConfig',
            'https://helper.2bulu.com/proSpecial/allData',
            'https://api.mcd.cn/bff/portal/richpop',
            'https://mapi.dianping.com/mapi/operating/indexopsmodules',
            'https://api.internetofcity.cn/api/resource/anon/popups/getList',
            'https://capi.mwee.cn/app-api/V12/app/ad',
            'https://switch.jumpvg.com/jump/recommend/ad_conf',
            'https://magev6.if.qidian.com/argus/api/v1/bookshelf/refresh',
            'https://myusmile.online/user/version/requestFirmwareUpdate/',
            'https://api.xueqiu.com/ucprofile/api/user/batchGetUserBasicInfo.json',
            'https://api.alipan.com/adrive/v1/file/getTopFolders',
            'https://weixin110.qq.com/cgi-bin/mmspamsupport-bin/newredirectconfirmcgi?x=1',
            'https://unrelated.example/music/common/upload/t_splash_info/ad.jpg',
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.matches(url), [])

    def test_version_wildcard_is_numeric_and_cannot_cross_path_boundaries(self):
        self.assertEqual(self.matches('https://magev6.if.qidian.com/argus/api/v12/client/getsplashscreen'), ['qidian-v6'])
        for version in ['anything', '1/account', '1.5']:
            self.assertEqual(self.matches(f'https://magev6.if.qidian.com/argus/api/v{version}/client/getsplashscreen'), [])

    def test_existing_domain_blocks_remove_redundant_url_and_mitm_hosts(self):
        blocked = [build.Rule('DOMAIN', 'api.mcd.cn'), build.Rule('DOMAIN-SUFFIX', 'qidian.com')]
        selected = splash.select_entries(self.manifest, blocked)
        self.assertFalse({'mcd', 'qidian', 'qidian-v6'} & {e['id'] for e in selected})
        self.assertNotIn('api.mcd.cn', splash.render_sections(selected))
        self.assertIn('api.pinduoduo.com', splash.render_sections(selected))

    def test_shared_api_hosts_are_never_promoted_to_domain_blocks(self):
        output = splash.render_sections(self.entries)
        self.assertNotIn('[Rule]', output)
        self.assertNotIn('DOMAIN', output)
        self.assertNotIn('[Script]', output)
        self.assertNotIn('[Map Local]', output)
        self.assertNotIn('script-path', output)
        self.assertNotIn('data=', output)
        self.assertNotIn('ca-p12', output)
        host_line = output.split('hostname = %APPEND% ')[1].strip()
        self.assertEqual(host_line.split(','), sorted({e['host'] for e in self.entries}))
        self.assertNotIn('*', host_line)

    def test_rejects_unreviewable_hosts_paths_duplicates_and_injection(self):
        for key, value in [
            ('host', '*.example.com'), ('host', '127.0.0.1'), ('host', 'api.example.bad-'),
            ('host', 'api.example.' + 'a' * 64), ('host', 'api.example.com\n[Script]'),
            ('path', '/.*splash'), ('path', '/account'), ('path', '/'),
            ('path', '/splash/{anything}'), ('path', '/splash/../account'),
            ('match', 'regex'), ('query', 'x=.*'), ('query', ''), ('id', 'x\n[Script]'), ('source_line', 0),
        ]:
            entries = copy.deepcopy(self.entries[:1])
            entries[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                splash.validate_entries(entries)
        with self.assertRaises(ValueError):
            splash.validate_entries(self.entries + self.entries[:1])
        entries = copy.deepcopy(self.entries[:1])
        entries[0]['script'] = 'remote.js'
        with self.assertRaises(ValueError):
            splash.validate_entries(entries)

    def test_subtree_overlaps_are_rejected(self):
        parent = dict(self.entries[0], path='/splash/', match='subtree')
        child = dict(parent, id='other', path='/splash/child', match='exact')
        with self.assertRaises(ValueError):
            splash.validate_entries([parent, child])

    def test_rendering_deterministic_and_empty_selection_has_no_mitm(self):
        self.assertEqual(splash.render_sections(self.entries), splash.render_sections(list(reversed(self.entries))))
        self.assertEqual(splash.render_sections([]), '')

    def test_manifest_fails_closed_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'splash.json'
            path.write_text('{"schema_version": 1, "entries": []}')
            with self.assertRaises(ValueError):
                splash.load_manifest(path)


if __name__ == '__main__':
    unittest.main()
