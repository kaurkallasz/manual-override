// Run weapon_upgrade_settings_fixture.py first; never contacts the live venue.
const assert = require('node:assert/strict'), fs = require('node:fs');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:' + fs.readFileSync('/tmp/weapon-upgrade-settings-port', 'utf8');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors = [];
  try {
    const settings = await browser.newPage({viewport:{width:1400,height:1000}});
    settings.on('pageerror', e => errors.push(e.message));
    await settings.goto(origin + '/s/gamemaster/p/photon-game/settings');
    await settings.waitForSelector('#save:not([disabled])');
    for (const [level,value] of [[2,'30'],[3,'40'],[4,'50']])
      assert.equal(await settings.inputValue('#weapon_upgrade_l'+level+'_percent'), value);
    assert.equal(await settings.inputValue('#l4_turrets_per_socket'), '2');
    await settings.locator('#weaponUpgrades').screenshot({path:'/tmp/weapon-upgrade-settings.png'});
    const score = await browser.newPage();
    score.on('pageerror', e => errors.push(e.message));
    await score.goto(origin + '/s/green/p/ltz-score/');
    await score.waitForFunction(() => document.querySelector('.ltzCard')?.innerText.includes('+30%'));
    assert.match(await score.locator('.ltzLevel3').first().innerText(), /\+40%/);
    assert.match(await score.locator('.ltzLevel4').first().innerText(), /\+50%.*Double turrets/);
    assert.match(await score.locator('.ltzCompanions').innerText(), /28 total/);
    for (const [level,value] of [[2,'35'],[3,'45'],[4,'65']])
      await settings.fill('#weapon_upgrade_l'+level+'_percent', value);
    await settings.selectOption('#l4_turrets_per_socket', '1');
    await settings.click('#save');
    await settings.waitForFunction(() => document.querySelector('#status').textContent.includes('saved'));
    await settings.reload();
    await settings.waitForSelector('#save:not([disabled])');
    assert.equal(await settings.inputValue('#weapon_upgrade_l4_percent'), '65');
    assert.equal(await settings.inputValue('#l4_turrets_per_socket'), '1');
    await settings.fill('#levelPresetName', 'Upgrade browser test');
    await settings.click('#saveLevelPreset');
    await settings.waitForFunction(() => document.querySelector('#levelPresetStatus').textContent.includes('Upgrade browser test'));
    await score.reload();
    await score.waitForFunction(() => document.querySelector('.ltzLevel4')?.innerText.includes('+65%'));
    assert.match(await score.locator('.ltzCompanions').innerText(), /single turrets/);
    const mobile = await browser.newPage({viewport:{width:844,height:390}});
    mobile.on('pageerror', e => errors.push(e.message));
    await mobile.addInitScript(() => localStorage.setItem('mobile-ltz:stopped','yes'));
    await mobile.goto(origin + '/s/green/p/mobile-ltz/');
    await mobile.locator('#levelsOpen').click();
    await mobile.locator('#openPlayers').click();
    await mobile.locator('#journeyToggle').click();
    await mobile.waitForFunction(() => document.querySelector('.ltzLevel4')?.innerText.includes('+65%'));
    assert.match(await mobile.locator('.ltzCompanions').innerText(), /single turrets/);
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: defaults, draft reload, saved tier tuning, score and mobile shop descriptions.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode=1;});
