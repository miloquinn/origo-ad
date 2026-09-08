import copy
import base64
import json
import re
import shutil
import subprocess
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

    def test_shared_bilibili_api_remains_available_with_path_level_ad_filtering(self):
        host = 'app.biliapi.net'
        blocked, _ = build.merge_rules(
            [build.Rule('DOMAIN', host), build.Rule('DOMAIN', 'ads.example')],
            build.parse_allowlist(ROOT / 'config/allowlist.txt'),
        )
        self.assertEqual(blocked, [build.Rule('DOMAIN', 'ads.example')])
        selected = splash.select_entries(self.manifest, blocked)
        self.assertEqual(len([e for e in selected if e['host'] == host]), 4)
        self.assertEqual(self.matches('https://' + host + '/x/v2/feed/index'), [])

    def test_shared_api_hosts_are_never_promoted_to_domain_blocks(self):
        output = splash.render_sections(self.entries)
        self.assertNotIn('[Rule]', output)
        self.assertNotIn('DOMAIN', output)
        self.assertNotIn('[Script]', output)
        self.assertNotIn('script-path', output)
        self.assertNotIn('data=https', output)
        self.assertNotIn('ca-p12', output)
        host_line = output.split('hostname = %APPEND% ')[1].strip()
        self.assertEqual(host_line.split(','), sorted({e['host'] for e in self.entries if not e.get('rewrite')}))
        self.assertNotIn('*', host_line)

    def test_local_responses_are_inline_and_equal_between_clients(self):
        native_maps = {e['match']: e for e in splash.native_sections(self.entries)['map_locals']}
        surge = splash.render_sections(self.entries)
        for entry in self.entries:
            if 'response' not in entry or entry['response'] == 'reject':
                continue
            pattern = splash.pattern(entry)
            body, content_type = splash.RESPONSES[entry['response']]
            self.assertEqual(native_maps[pattern], {
                'match': pattern, 'status_code': 200,
                'headers': {'Content-Type': content_type}, 'body': body,
            })
            encoded = base64.b64encode(body.encode()).decode()
            self.assertIn(f'{pattern} data-type=base64 data="{encoded}" status-code=200 header="Content-Type:{content_type}"', surge)

    def test_native_json_filters_never_become_surge_request_rejections(self):
        entries = [e for e in self.entries if e.get('rewrite')]
        self.assertEqual(splash.render_sections(entries), '')
        native = splash.native_sections(entries)
        self.assertEqual(set(native), {'body_rewrites', 'mitm'})
        self.assertEqual(len(native['body_rewrites']), len(entries))
        self.assertEqual(native['mitm']['hostnames']['includes'], sorted({e['host'] for e in entries}))

    def test_dispatcher_query_can_move_but_must_be_unambiguous(self):
        for params in ['functionId=start', 'client=apple&functionId=start',
                       'client=apple&functionId=start&version=15', 'functionId=start&client=apple']:
            self.assertEqual(self.matches('https://api.m.jd.com/client.action?' + params), ['jd-start'])
        for params in ['functionId=welcomeHome', 'functionId=startHome',
                       'functionId=login&next=functionId=start', 'otherfunctionId=start',
                       'functionId=start&functionId=login', 'functionId=login&functionId=start',
                       'functionId=start&functionId=start', 'functionId=start#fragment']:
            self.assertEqual(self.matches('https://api.m.jd.com/client.action?' + params), [])

    def test_popular_app_rules_preserve_normal_features(self):
        for url in [
            'https://api.m.jd.com/client.action?functionId=welcomeHome',
            'https://api.m.jd.com/client.action?functionId=login',
            'https://acs.m.goofish.com/gw/mtop.taobao.idle.item.detail/1.0/',
            'https://acs.m.goofish.com/gw/mtop.taobao.idlecommerce.splash.adsHistory/1.0/',
            'https://app.bilibili.com/x/v2/feed/index',
            'https://app.bilibili.com/x/v2/splash/event/list2History',
            'https://api.zhihu.com/topstory/recommend',
            'https://api.zhihu.com/commercial_api/launch_v2_config',
            'https://edith.xiaohongshu.com/api/sns/v1/note/feed',
            'https://wmapi.meituan.com/api/v7/order/detail',
            'https://wmapi.meituan.com/api/v7/loadInfo/other',
            'https://guide-acs.m.taobao.com/gw/mtop.taobao.wireless.home.splash.awesome.get/1.0/',
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.matches(url), [])

    @unittest.skipUnless(shutil.which('jq'), 'jq is only needed for native filter execution tests')
    def test_native_filters_remove_only_ad_fields_and_preserve_unknown_shapes(self):
        def run_filter(name, value):
            result = subprocess.run(['jq', '-c', splash.BODY_REWRITES[name]], input=json.dumps(value),
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        bili = {'code': 0, 'data': {'show': [{'ad': 1}], 'event_list': ['ad'], 'preload': ['ad'],
                                 'list': ['other'], 'account': {'vip': 0}}, 'message': 'ok'}
        self.assertEqual(run_filter('bilibili-preload', bili), {
            'code': 0, 'data': {'list': ['other'], 'account': {'vip': 0}}, 'message': 'ok',
        })
        jd = {'images': ['ad'], 'showTimesDaily': 3, 'config': {'login': True}, 'user': {'vip': False}}
        self.assertEqual(run_filter('jd-start', jd), dict(jd, images=[], showTimesDaily=0))
        xhs = {'code': 0, 'data': {'ads_groups': [
            {'group_id': 'keep', 'start_time': 1, 'end_time': 2,
             'ads': [{'creative_id': 'keep', 'start_time': 1, 'end_time': 2}, None]},
            'unexpected',
        ], 'settings': {'keep': True}}}
        updated = copy.deepcopy(xhs)
        for item in [updated['data']['ads_groups'][0], updated['data']['ads_groups'][0]['ads'][0]]:
            item.update(start_time=3818332800, end_time=3818419199)
        self.assertEqual(run_filter('xhs-splash', xhs), updated)
        for name in splash.BODY_REWRITES:
            for value in [None, [], 'unknown', 3, {}, {'data': None}, {'data': []},
                          {'data': {'ads_groups': None, 'keep': 1}}, {'images': None}]:
                with self.subTest(filter=name, value=value):
                    self.assertEqual(run_filter(name, value), value)
            result = run_filter(name, {'error': 'unauthorized', 'code': 401})
            self.assertEqual(result, {'error': 'unauthorized', 'code': 401})

    def test_response_templates_and_pinned_sources_cannot_inject_code(self):
        for key, value in [('response', 'https://example.com/body'), ('response', {}),
                           ('rewrite', 'remote-script'), ('rewrite', 'jd-start'),
                           ('source_url', 'https://github.com/example/repo/blob/main/rules.js')]:
            entry = dict(self.entries[0], **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                splash.validate_entries([entry])
        jd = next(e for e in self.entries if e['id'] == 'jd-start')
        for changes in [{'path': '/splash'}, {'query': 'functionId=welcomeHome'},
                        {'host': 'other.example'}, {'response': 'empty-json'}]:
            with self.assertRaises(ValueError):
                splash.validate_entries([dict(jd, **changes)])

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
