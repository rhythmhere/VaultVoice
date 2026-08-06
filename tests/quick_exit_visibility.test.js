import test from 'node:test';
import assert from 'node:assert/strict';

const appRoot = {innerHTML: ''};
globalThis.document = {
  body: {},
  querySelector: selector => selector === '#app' ? appRoot : null,
  addEventListener: () => {},
};
globalThis.MutationObserver = class { observe() {} };
globalThis.window = {
  innerWidth: 1440,
  location: {pathname: '/'},
  scrollTo: () => {},
};
globalThis.location = globalThis.window.location;
globalThis.sessionStorage = {clear: () => {}};

const {header, initialScreenForPath, state} = await import('../app.js');

const survivorPages = [
  ['landing', '/', false],
  ['pre-clarification', '/report', false],
  ['mid-clarification', '/chat', true],
  ['dashboard', '/dashboard', true],
  ['evidence', '/evidence', true],
  ['error/404', '/404', false],
];

for (const viewport of [1440, 375]) {
  test(`Quick Exit is visible on every survivor page at ${viewport}px`, () => {
    window.innerWidth = viewport;
    window.location.pathname = '/';
    for (const [, pathname, authenticated] of survivorPages) {
      window.location.pathname = pathname;
      state.isAuthenticated = authenticated;
      assert.match(header(), /data-action="exit"/);
      assert.match(header(), /Quick Exit/);
    }
  });
}

test('Quick Exit remains hidden on NGO and admin routes', () => {
  state.isAuthenticated = false;
  for (const pathname of ['/ngo', '/ngo/dashboard', '/admin', '/admin/cases']) {
    window.location.pathname = pathname;
    assert.doesNotMatch(header(), /data-action="exit"/);
  }
});

test('NGO registration remains available at the base NGO route', () => {
  assert.equal(initialScreenForPath('/ngo'), 'ngoPortal');
  assert.equal(initialScreenForPath('/ngo/'), 'ngoPortal');
  assert.equal(initialScreenForPath('/ngo/dashboard'), 'ngoDashboardPortal');
});
