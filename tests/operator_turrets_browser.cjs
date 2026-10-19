// Run operator_turret_fixture.py first. Synthetic camera/occupancy, no hardware.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:' + fs.readFileSync('/tmp/operator-turrets-port', 'utf8').trim();
const output = path.resolve(process.argv[2] || '/tmp/operator-turrets-browser');
fs.mkdirSync(output, {recursive: true});
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors = [];
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1080}});
    const screen = await browser.newPage({viewport: {width: 1200, height: 800}});
    for (const p of [page, screen]) p.on('pageerror', error => errors.push(error.message));
    await page.goto(origin + '/s/gamemaster/p/laser-tag-y/game');
    await page.waitForFunction(() => ui.state?.turret_controls?.sockets?.length === 16);
    await page.evaluate(() => command({action: 'reset', virtual_play: true}));
    async function setCamera(patch) {
      await page.request.post(origin + '/fixture/camera', {data: patch});
      const layout = await (await page.request.get(origin + '/fixture/camera-layout')).json();
      const image = await page.evaluate(({width,height,tags}) => {
        const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
        const ctx=canvas.getContext('2d');ctx.fillStyle='#24372f';ctx.fillRect(0,0,width,height);
        ctx.strokeStyle='#94a487';ctx.lineWidth=5;ctx.strokeRect(45,45,width-90,height-90);
        ctx.fillStyle='#627259';ctx.fillRect(80,height/2-35,width-160,70);
        for(const tag of tags){
          const x=tag.camera[0]*width,y=tag.camera[1]*height;
          ctx.fillStyle='white';ctx.fillRect(x-18,y-18,36,36);ctx.fillStyle='black';ctx.fillRect(x-15,y-15,30,30);
          ctx.fillStyle='white';for(let r=0;r<4;r++)for(let c=0;c<4;c++)if((tag.id+r*7+c*11)%3)ctx.fillRect(x-10+c*5,y-10+r*5,4,4);
        }
        return canvas.toDataURL('image/jpeg').split(',')[1];
      },layout);
      await page.request.post(origin + '/fixture/camera', {data: {image}});
    }
    await setCamera({enabled: true, width: 1280, height: 720, dx: 0, dy: 0});
    assert(await page.locator('#turretOverlay').isHidden());
    assert.equal(await page.locator('#socketTags > button.tag-chip').count(), 16);
    assert.equal(await page.locator('#socketTags [data-turret-atom]').count(), 0);
    assert.equal(await page.locator('[data-activation]').count(), 0);
    // The original below-field virtual placement chips still work.
    await page.locator('#atomTags [data-atom="101"]').click();
    await page.locator('#socketTags [data-socket="socket_01"]').click();
    await page.waitForFunction(() => ui.state.towers.length === 1);
    await page.locator('#atomTags [data-atom="102"]').click();
    await page.locator('#socketTags [data-socket="socket_03"]').click();
    await page.waitForFunction(() => ui.state.towers.length === 2);
    await page.request.post(origin + '/fixture/physical', {data: {tag: null}});
    await page.waitForFunction(() => !document.getElementById('turretOverlay').hidden && document.querySelectorAll('.turret-overlay-target').length === 17);
    await screen.goto(origin + '/s/gamemaster/p/laser-tag-y/screen');
    await screen.waitForFunction(() => latestState?.towers?.length === 2);
    assert.equal(await screen.locator('#turretOverlay').count(), 0);
    const target = page.locator('#turretOverlay [data-turret-socket="socket_01"]');
    const atom = id => target.locator(`[data-turret-atom="${id}"]`);
    const destroy = target.locator('[data-destroy-turret]');
    async function activate(id) {
      const before = await page.evaluate(() => ui.state.events.at(-1)?.sequence || 0);
      await atom(id).click();
      await page.waitForFunction(({id, before}) => ui.state.events.some(event => event.sequence > before
        && event.kind === 'operator_atom_selected' && event.atom_tag_id === id && event.socket_id === 'socket_01'), {id, before});
      const tower = await page.evaluate(() => ui.state.towers.find(t => t.socket_id === 'socket_01'));
      assert(!tower.destroyed && tower.hp > 0);
      assert.equal(tower.occupying_atom_id, null);
      assert.notEqual(tower.atom_buff_state, 'active');
      assert.equal(tower.atom_health_multiplier, 1);
      assert.equal(tower.atom_damage_multiplier, 1);
      assert.equal(tower.max_hp, tower.normal_max_hp);
      assert.equal(await target.locator('[data-turret-atom][aria-pressed="true"]').count(), 0);
      return tower;
    }
    const coreTarget = page.locator('#turretOverlay [data-turret-socket="core_38"]');
    const coreAtom = id => coreTarget.locator(`[data-turret-atom="${id}"]`);
    const coreX = coreTarget.locator('[data-destroy-turret]');
    assert.equal(await coreTarget.locator('button').count(), 5);
    assert(await coreAtom(100).isDisabled(), 'Core waits for a running game and completed ring');
    async function assertPosition() {
      const result = await page.evaluate(() => {
        const stage = document.getElementById('stage').getBoundingClientRect();
        const code = document.querySelector('#arucoOverlay [data-marker="40"]').getBoundingClientRect();
        const item = document.querySelector('[data-turret-socket="socket_01"]');
        const atoms = item.querySelector('.turret-overlay-atoms').getBoundingClientRect();
        const x = item.querySelector('[data-destroy-turret]').getBoundingClientRect();
        return {left: Math.abs(code.left - atoms.right - 7), right: Math.abs(x.left - code.right - 7),
          aligned: Math.abs((x.top + x.bottom - code.top - code.bottom) / 2),
          inside: [atoms,x].every(r => r.left >= stage.left && r.right <= stage.right && r.top >= stage.top && r.bottom <= stage.bottom)};
      });
      assert(result.left < 2 && result.right < 2 && result.aligned < 2 && result.inside, JSON.stringify(result));
    }
    await assertPosition();
    assert.equal(await target.locator('button').count(), 5);
    assert.equal(await destroy.evaluate(node => getComputedStyle(node).color), 'rgb(0, 0, 0)');
    await activate(100);
    await destroy.click();
    await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01').destroyed);
    await screen.waitForFunction(() => latestState.towers.find(t => t.socket_id === 'socket_01').destroyed);
    const dead = await page.evaluate(() => ui.state.towers.find(t => t.socket_id === 'socket_01'));
    assert.equal(dead.hp, 0); assert.equal(dead.deactivated, false); assert.equal(dead.operational, false);
    assert.equal(await destroy.evaluate(node => getComputedStyle(node).color), 'rgb(255, 255, 255)');
    assert.match(await page.locator('#socketTags [data-socket="socket_01"]').textContent(), /DOWN/);
    await page.request.post(origin + '/fixture/physical', {data: {tag: 103}});
    await page.waitForFunction(() => ui.state.turret_controls.sockets[0].atom_source === 'physical');
    assert.equal(await atom(103).getAttribute('aria-pressed'), 'true');
    assert(await atom(100).isDisabled());
    assert(await page.locator('[data-turret-socket="socket_03"] [data-turret-atom="103"]').isDisabled());
    const rejected = await page.request.post(origin + '/s/gamemaster/p/laser-tag-y/api/command',
      {data: {action: 'operator_atom', socket_id: 'socket_01', atom_tag_id: 100}});
    assert.equal(rejected.status(), 400);
    assert.match((await rejected.json()).error, /Physical Atom/);
    await page.locator('#stage').screenshot({path: path.join(output, 'gamefield-desktop.png')});
    await page.locator('#socketTags').screenshot({path: path.join(output, 'restored-panel.png')});
    const before = await atom(103).boundingBox();
    await setCamera({dx: .03});
    await page.waitForFunction(() => ui.aruco.tags.find(t => t.id === 40)?.camera[0] > .03);
    await page.waitForTimeout(700);
    const after = await atom(103).boundingBox();
    assert(after.x - before.x > 20, 'Controls follow changed coordinates of the same ArUco ID');
    await assertPosition();
    await page.setViewportSize({width: 390, height: 844});
    await page.waitForTimeout(100);
    await assertPosition();
    await page.locator('.stage-shell').screenshot({path: path.join(output, 'gamefield-phone.png')});
    assert(await page.locator('.stage-shell').evaluate(node => node.scrollWidth > node.clientWidth), 'Narrow field scrolls instead of overlapping its controls');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.reload();
    await page.waitForFunction(() => !document.getElementById('turretOverlay').hidden && ui.state?.turret_controls?.sockets[0].atom_source === 'physical');
    assert.equal(await atom(103).getAttribute('aria-pressed'), 'true');
    await page.request.post(origin + '/fixture/physical', {data: {tag: 103, state: 'departed'}});
    await page.waitForFunction(() => ui.state.turret_controls.sockets[0].atom_id === null);
    assert.equal(await atom(100).getAttribute('aria-pressed'), 'false');
    await activate(101);
    await activate(101);
    await page.evaluate(() => { disconnectGameEvents(); turretControls.disconnected(); renderControls(); });
    assert(await atom(100).isDisabled());
    await page.evaluate(() => connectGameEvents());
    await page.waitForFunction(() => !document.querySelector('[data-turret-socket="socket_01"] [data-turret-atom="100"]').disabled);
    await page.request.post(origin + '/fixture/camera', {data: {enabled: false}});
    await page.waitForFunction(() => document.getElementById('turretOverlay').hidden);
    await page.request.post(origin + '/fixture/camera', {data: {enabled: true}});
    await page.waitForFunction(() => !document.getElementById('turretOverlay').hidden);
    await page.evaluate(() => { disconnectGameEvents(); applyState({...ui.state, journey: {...ui.state.journey, phase: 'calibration'}}); });
    assert(await page.locator('#turretOverlay').isHidden());
    await page.evaluate(() => connectGameEvents());
    await page.waitForFunction(() => ui.state.journey?.phase !== 'calibration');
    await page.evaluate(() => command({action: 'reset', virtual_play: true}));
    await page.waitForFunction(() => ui.state.towers.length === 0);
    assert(await page.locator('#turretOverlay').isHidden());
    // Regression: clicks must change gameplay during a run, including scored
    // mode, rather than merely changing a setup occupancy highlight.
    await page.setViewportSize({width: 1500, height: 1080});
    for (const scored of [false, true]) {
      await page.evaluate(() => command({action: 'reset', virtual_play: false}));
      const started = await page.request.post(origin + '/fixture/start', {data: {scored}});
      assert(started.ok());
      await page.waitForFunction(scored => ui.state.phase === 'running' && ui.state.progress.reward_enabled === scored
        && !ui.state.virtual_play && !document.getElementById('turretOverlay').hidden, scored);
      assert(await atom(103).isEnabled(), `Atom control enabled during ${scored ? 'scored' : 'practice'} play`);
      const installed = await activate(103);
      assert.equal(installed.tower_type, 'tesla_coil');
      assert.equal(installed.owner, 'purple');
      await screen.waitForFunction(() => latestState.towers.some(t => t.socket_id === 'socket_01'
        && t.tower_type === 'tesla_coil' && t.occupying_atom_id === null && t.atom_damage_multiplier === 1 && !t.destroyed));
      await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01').operational);
      await destroy.click();
      await page.waitForFunction(() => ui.state.towers.find(t => t.socket_id === 'socket_01').destroyed);
      await activate(103); // The same number rebuilds after X without a boost.
      const replenished = await activate(100);
      assert.equal(replenished.tower_type, 'tesla_coil');
      assert.equal(replenished.owner, 'purple');
      await activate(100); // A repeated number activates again; it is not a toggle.
      await activate(101);
      await page.request.post(origin + '/fixture/physical', {data: {tag: 102}});
      await page.waitForFunction(() => ui.state.turret_controls.sockets[0].atom_source === 'physical'
        && ui.state.turret_controls.sockets[0].atom_id === 102);
      assert(await atom(100).isDisabled());
      const conflict = await page.request.post(origin + '/s/gamemaster/p/laser-tag-y/api/command',
        {data: {action: 'operator_atom', socket_id: 'socket_01', atom_tag_id: 100}});
      assert.equal(conflict.status(), 400);
      assert.match((await conflict.json()).error, /Physical Atom/);
      if (scored) await page.locator('#stage').screenshot({path: path.join(output, 'gamefield-running-scored.png')});
    }
    for (const {first, same, second, scored} of [
      {first: 100, same: 101, second: 103, scored: false},
      {first: 102, same: 103, second: 100, scored: true},
    ]) {
      const prepared = await page.request.post(origin + '/fixture/core-ring', {data: {scored}});
      assert(prepared.ok());
      await page.waitForFunction(scored => ui.state.phase === 'running' && ui.state.progress.reward_enabled === scored
        && ui.state.core_sequence.stage === 'ring_ready', scored);
      assert(await coreAtom(first).isEnabled());
      const aligned = await page.evaluate(() => {
        const code = document.querySelector('#arucoOverlay [data-marker="38"]').getBoundingClientRect();
        const controls = document.querySelector('[data-turret-socket="core_38"]');
        const ids = controls.querySelector('.turret-overlay-atoms').getBoundingClientRect();
        const x = controls.querySelector('[data-destroy-turret]').getBoundingClientRect();
        return Math.abs(code.left - ids.right - 7) < 2 && Math.abs(x.left - code.right - 7) < 2;
      });
      assert(aligned, 'Core controls sit beside detected ArUco 38');
      await coreAtom(first).click();
      await page.waitForFunction(first => ui.state.core_sequence.stage === 'first_tag'
        && ui.state.core_sequence.first_atom_tag_id === first, first);
      assert.equal(await coreAtom(first).getAttribute('aria-pressed'), 'true');
      await coreAtom(same).click();
      await page.waitForFunction(() => document.getElementById('turretControlStatus').textContent.includes('opposing team'));
      assert.equal(await page.evaluate(() => ui.state.core_sequence.stage), 'first_tag');
      assert.equal(await coreAtom(same).getAttribute('aria-pressed'), 'false');
      await coreX.click();
      await page.waitForFunction(() => ui.state.core_sequence.stage === 'ring_ready' && ui.state.core_sequence.first_atom_tag_id === null);
      assert.equal(await coreAtom(first).getAttribute('aria-pressed'), 'false');
      await coreAtom(first).click();
      await page.waitForFunction(first => ui.state.core_sequence.first_atom_tag_id === first, first);
      await page.reload();
      await page.waitForFunction(first => ui.state?.core_sequence?.first_atom_tag_id === first
        && !document.getElementById('turretOverlay').hidden, first);
      assert.equal(await coreAtom(first).getAttribute('aria-pressed'), 'true');
      if (scored) await page.locator('#stage').screenshot({path: path.join(output, 'core-first-layer.png')});
      await coreAtom(second).click();
      await page.waitForFunction(second => ['detonating', 'complete'].includes(ui.state.core_sequence.stage)
        && ui.state.core_sequence.second_atom_tag_id === second, second);
      assert.equal(await coreAtom(first).getAttribute('aria-pressed'), 'true');
      assert.equal(await coreAtom(second).getAttribute('aria-pressed'), 'true');
      assert(await coreX.isDisabled());
      await page.waitForFunction(() => ui.state.phase === 'won');
      await screen.waitForFunction(() => latestState.phase === 'won' && latestState.core_sequence.stage === 'complete');
      if (scored) await page.locator('#stage').screenshot({path: path.join(output, 'core-complete.png')});
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({passed: true, errors,
      checks: ['only 4 IDs and X on camera overlay', 'no G/P', 'original panel restored', 'normal turret destruction',
        'external display synchronization', 'physical priority', 'removal', 'momentary number activation',
        'zoom and letterbox alignment', 'marker movement', '390px resize', 'camera loss', 'calibration', 'reload', 'reset',
        'running practice and scored number activation', 'no manual Atom boost', 'rebuild after X', 'retained weapon and owner',
        'running physical priority', 'ArUco 38 placement', 'core ring prerequisite', 'first layer',
        'same-color core rejection', 'core X/reset', 'core reload', 'opposing colors complete in either order',
        'core victory on external display']}, null, 2));
    console.log('Operator overlay checks passed: ' + output);
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
