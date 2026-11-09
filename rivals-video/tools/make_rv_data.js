// Erzeugt rv_data.json für Rivals Video aus Rivals Coach: Gruppen und genaue Todesursachen pro Rolle (wie in der Notiz) und die Helden mit Rolle.
// Aufruf: node tools/make_rv_data.js PFAD/zu/rivals-coach.html  (gebaute App; braucht Playwright)
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const src = path.resolve(process.argv[2] || '../docs/marvel-rivals/artifact/rivals-coach.html');
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + src);
  const d = await p.evaluate(() => {
    const roles = {};
    ROLES.forEach(r => {
      const all = [...new Set(DEATH_BY_ROLE[r].concat(DEATH_MORE_ROLE[r] || [], DEATH_MORE).map(o => o[0]))];
      roles[r] = QN_CATS.map(c => ({ group: c, causes: all.filter(l => l !== c && deathCat(l) === c) }));
    });
    const heroes = Object.keys(PROF).filter(h => heroRole(h) && heroRole(h) !== '?').sort((a, c) => a.localeCompare(c)).map(h => ({ name: h, role: heroRole(h) }));
    return { made: new Date().toISOString().slice(0, 10), groups: QN_CATS, ultGroup: QN_CATS.find(c => /Ult/.test(c)), roles, heroes };
  });
  await b.close();
  fs.writeFileSync(path.join(__dirname, '..', 'rv_data.json'), JSON.stringify(d, null, 1));
  console.log('rv_data.json:', d.groups.length, 'Gruppen,', Object.keys(d.roles).map(r => r + ' ' + d.roles[r].reduce((a, g) => a + g.causes.length, 0)).join(', '), 'Ursachen,', d.heroes.length, 'Helden');
})();
