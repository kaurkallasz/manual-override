// Start virtual_upgrades_fixture.py first. This uses its isolated Game, never hardware.
// NODE_PATH=<installed Playwright modules> node tests/atom_buff_browser.cjs <output-dir>
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {chromium} = require('playwright');
const origin = process.env.ATOM_BUFF_FIXTURE_URL || 'http://127.0.0.1:' + fs.readFileSync('/tmp/virtual-upgrades-port', 'utf8').trim();
const output = path.resolve(process.argv[2] || '/tmp/atom-buff-browser');
fs.mkdirSync(output, {recursive: true});
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors = [];
  try {
    const page = await browser.newPage({viewport: {width: 1800, height: 1200}});
    const screen = await browser.newPage({viewport: {width: 1696, height: 960}});
    for (const p of [page, screen]) p.on('pageerror', error => errors.push(error.message));
    await page.goto(origin + '/s/gamemaster/p/laser-tag-y/game');
    await page.waitForFunction(() => ui.state?.status === 'ready');
    await page.evaluate(async () => {
      await command({action: 'reset'});
      await command({action: 'set_virtual', virtual_play: true});
    });
    await page.click('#maxTestUnlocks');
    await page.waitForFunction(() => ui.state.virtual_test_loadout?.forcefield === 4);
    await screen.goto(origin + '/s/gamemaster/p/laser-tag-y/screen');
    await screen.waitForFunction(() => latestState?.status === 'ready');
    await page.evaluate(() => command({action: 'place', atom_tag_id: 100, socket_id: 'socket_01'}));
    await screen.waitForFunction(() => latestState.towers.some(t => t.socket_id === 'socket_01' && !t.operational && t.atom_buff_state === 'active'));
    assert.deepEqual(await screen.evaluate(() => {
      const t = latestState.towers.find(t => t.socket_id === 'socket_01');
      return TowerDefenceView.geometry.towerHealthBarMetrics(t, latestState.sim_time).barFractions;
    }), [1, 1]);
    await screen.screenshot({path: path.join(output, 'screen-deploying.png')});
    await page.evaluate(async () => {
      for (const [i, socket] of ui.state.level.sockets.entries())
        await command({action: 'place', atom_tag_id: 100 + i % 4, socket_id: socket.socket_id});
    });
    await page.waitForFunction(() => ui.state.companions?.length === 12 && ui.state.companions.every(t => t.operational));
    await screen.waitForFunction(() => latestState?.towers?.length === 16);
    await page.evaluate(async () => {
      ui.selectedAtom = 100;
      await place('socket_01');
      renderControls();
    });
    await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'active');
    await screen.waitForFunction(() => latestState.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'active');
    await page.waitForTimeout(1200); // Persistent cue, well past deployment/replenish flashes.
    const active = await page.evaluate(() => {
      const t = ui.state.towers.find(t => t.socket_id === 'socket_01');
      const c = ui.state.companions.find(t => t.socket_id === 'socket_01');
      return {tower: t, companion: c, details: document.querySelector('#aimHealthText').textContent};
    });
    assert.equal(active.tower.max_hp, active.tower.normal_max_hp * 2);
    assert.equal(active.tower.atom_damage_multiplier, 2);
    assert.equal(active.companion.atom_damage_multiplier, 2);
    assert.match(active.details, /Health ×2 · Damage ×2/);
    await page.locator('#stage').screenshot({path: path.join(output, 'operator-active.png')});
    await screen.screenshot({path: path.join(output, 'screen-active.png')});
    await page.click('#removeAtom');
    await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'inactive');
    await screen.waitForFunction(() => latestState.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'inactive');
    const lifted = await page.evaluate(() => ui.state.towers.find(t => t.socket_id === 'socket_01'));
    assert.equal(lifted.max_hp, lifted.normal_max_hp);
    assert.equal(lifted.atom_damage_multiplier, 1);
    await screen.screenshot({path: path.join(output, 'screen-power-down.png')});
    await screen.waitForTimeout(650);
    await screen.screenshot({path: path.join(output, 'screen-removed.png')});
    await page.evaluate(() => place('socket_01'));
    await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'active');
    const returned = await page.evaluate(() => ui.state.towers.find(t => t.socket_id === 'socket_01'));
    assert.equal(returned.hp, returned.max_hp);
    await screen.reload();
    await screen.waitForFunction(() => latestState?.towers?.find(t => t.socket_id === 'socket_01')?.atom_damage_multiplier === 2);
    await page.evaluate(() => place('socket_03'));
    await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01')?.atom_buff_state === 'inactive');
    assert.equal(await page.evaluate(() => ui.state.towers.length), 16);
    assert.equal(await page.evaluate(() => ui.state.companions.length), 12);
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({passed: true, checks: [
      '16 primaries and 12 companions', 'both displays receive active and removed state',
      'persistent green glow screenshots', 'full doubled health during deployment', 'power-down screenshots', 'health and damage details',
      'virtual lift button', 'return restores full doubled health', 'screen reconnect', 'buff transfer'
    ], errors}, null, 2));
    console.log('Atom buff browser checks passed; screenshots: ' + output);
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
